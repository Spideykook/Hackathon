"""
chatbot/indexing.py

Dual FAISS index pipeline:
  products_index  → Product catalogue embeddings
  support_index   → FAQ / policy document embeddings

Each index uses IndexFlatIP (inner product on L2-normalised vectors = cosine similarity).
A parallel JSON metadata sidecar keeps lightweight record info aligned by FAISS int ID.

Bootstrap:
    python manage.py rebuild_index

Incremental update (e.g. from a post_save signal or admin action):
    from chatbot.indexing import get_index_manager
    get_index_manager().rebuild_products()
"""

import json
import logging
import numpy as np
import faiss
from pathlib import Path
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

INDEX_DIR       = Path(getattr(settings, "FAISS_INDEX_DIR", str(Path(settings.BASE_DIR) / "faiss_indices")))
EMBEDDING_MODEL = getattr(settings, "EMBEDDING_MODEL", "all-MiniLM-L6-v2")
BATCH_SIZE      = 64

PRODUCT_INDEX_PATH = INDEX_DIR / "products.index"
PRODUCT_META_PATH  = INDEX_DIR / "products_meta.json"
SUPPORT_INDEX_PATH = INDEX_DIR / "support.index"
SUPPORT_META_PATH  = INDEX_DIR / "support_meta.json"

# ── Encoder singleton ─────────────────────────────────────────────────────────

_encoder = None


def get_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _encoder = SentenceTransformer(EMBEDDING_MODEL)
    return _encoder


def embed_texts(texts: list) -> np.ndarray:
    """Returns float32 L2-normalised embeddings, shape (N, dim)."""
    encoder = get_encoder()
    embeddings = encoder.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=len(texts) > BATCH_SIZE,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.astype(np.float32)


# ── Index Manager ─────────────────────────────────────────────────────────────


class IndexManager:
    def __init__(self):
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        self._product_index = None
        self._product_meta  = None
        self._support_index = None
        self._support_meta  = None

    # ─ Build ──────────────────────────────────────────────────────────────────

    def rebuild_all(self):
        self.rebuild_products()
        self.rebuild_support()

    def rebuild_products(self):
        from products.models import Product

        logger.info("Building product FAISS index …")
        records = list(Product.objects.filter(is_active=True).select_related("category"))

        if not records:
            logger.warning("No active products — skipping product index.")
            return

        texts      = [p.to_embedding_text() for p in records]
        embeddings = embed_texts(texts)
        dim        = embeddings.shape[1]

        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        meta = [
            {
                "faiss_id":  i,
                "db_id":     p.id,
                "name":      p.name,
                "price":     float(p.effective_price),
                "category":  p.category.name if p.category else "",
                "sku":       p.sku,
                "colors":    p.colors,
                "sizes":     p.sizes_available,
                "gender":    p.gender,
                "stock":     p.stock,
                "image_url": p.image_url,
            }
            for i, p in enumerate(records)
        ]

        faiss.write_index(index, str(PRODUCT_INDEX_PATH))
        PRODUCT_META_PATH.write_text(json.dumps(meta))

        now = datetime.now(timezone.utc)
        for i, p in enumerate(records):
            Product.objects.filter(pk=p.pk).update(embedding_id=i, embedding_updated_at=now)

        self._product_index = index
        self._product_meta  = meta
        logger.info(f"Product index: {len(records)} vectors, dim={dim}")

    def rebuild_support(self):
        from support.models import SupportDocument

        logger.info("Building support FAISS index …")
        records = list(SupportDocument.objects.filter(is_active=True).select_related("category"))

        if not records:
            logger.warning("No active support docs — skipping support index.")
            return

        texts      = [d.to_embedding_text() for d in records]
        embeddings = embed_texts(texts)
        dim        = embeddings.shape[1]

        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        meta = [
            {
                "faiss_id": i,
                "db_id":    d.id,
                "title":    d.title,
                "doc_type": d.doc_type,
                "category": d.category.name if d.category else "",
                "content":  d.content,
                "question": d.question,
            }
            for i, d in enumerate(records)
        ]

        faiss.write_index(index, str(SUPPORT_INDEX_PATH))
        SUPPORT_META_PATH.write_text(json.dumps(meta))

        now = datetime.now(timezone.utc)
        for i, d in enumerate(records):
            SupportDocument.objects.filter(pk=d.pk).update(embedding_id=i, embedding_updated_at=now)

        self._support_index = index
        self._support_meta  = meta
        logger.info(f"Support index: {len(records)} vectors, dim={dim}")

    # ─ Load ───────────────────────────────────────────────────────────────────

    def _load_product_index(self):
        if self._product_index is None:
            if not PRODUCT_INDEX_PATH.exists():
                raise RuntimeError(
                    "Product FAISS index not found. Run: python manage.py rebuild_index --products"
                )
            self._product_index = faiss.read_index(str(PRODUCT_INDEX_PATH))
            self._product_meta  = json.loads(PRODUCT_META_PATH.read_text())

    def _load_support_index(self):
        if self._support_index is None:
            if not SUPPORT_INDEX_PATH.exists():
                raise RuntimeError(
                    "Support FAISS index not found. Run: python manage.py rebuild_index --support"
                )
            self._support_index = faiss.read_index(str(SUPPORT_INDEX_PATH))
            self._support_meta  = json.loads(SUPPORT_META_PATH.read_text())

    # ─ Search ─────────────────────────────────────────────────────────────────

    def search_products(self, query: str, k: int = 5, score_threshold: float = 0.3) -> list:
        self._load_product_index()
        qvec = embed_texts([query])
        scores, indices = self._product_index.search(qvec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or score < score_threshold:
                continue
            item = dict(self._product_meta[idx])
            item["score"] = float(score)
            results.append(item)
        return results

    def search_support(self, query: str, k: int = 3, score_threshold: float = 0.35) -> list:
        self._load_support_index()
        qvec = embed_texts([query])
        scores, indices = self._support_index.search(qvec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or score < score_threshold:
                continue
            item = dict(self._support_meta[idx])
            item["score"] = float(score)
            results.append(item)
        return results


# ── Module-level singleton ────────────────────────────────────────────────────

_index_manager = None


def get_index_manager() -> IndexManager:
    global _index_manager
    if _index_manager is None:
        _index_manager = IndexManager()
    return _index_manager
