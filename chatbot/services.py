"""
chatbot/services.py  [MODIFIED]

Root cause fixes applied:
  1. TIMEOUT BUG   — stream=False blocks until ALL tokens arrive. Llama3 on CPU
                     generating 512 tokens takes 90-150s, blowing past 60s limit.
                     Fixed with stream=True + iter_lines(): reads tokens as they
                     come, socket stays alive through generation.
  2. TIMEOUT VALUE — Now a tuple: (5s connect, 180s read). Previously one flat
                     value applied to both, causing premature connect aborts too.
  3. RETRIES       — 2 automatic retries with 1s back-off on transient failures.
  4. HEALTH CHECK  — Fast GET /api/tags before first request. Gives a clear,
                     actionable error instead of a cryptic ConnectTimeout.
  5. FAISS FALLBACK— _retrieve() catches RuntimeError so missing index doesn't
                     crash the response; LLM answers from system prompt alone.
"""

import re
import json
import time
import logging
import requests
from dataclasses import dataclass, field

from django.conf import settings

from .indexing import get_index_manager
from .models import Conversation, Message

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = getattr(settings, "OLLAMA_MODEL",    "llama3")
# Tuple: (connect_timeout_seconds, read_timeout_seconds)
OLLAMA_TIMEOUT  = (
    getattr(settings, "OLLAMA_CONNECT_TIMEOUT", 5),
    getattr(settings, "OLLAMA_READ_TIMEOUT",    180),
)
OLLAMA_RETRIES      = getattr(settings, "OLLAMA_RETRIES",           2)
MAX_PRODUCT_RESULTS = getattr(settings, "RAG_MAX_PRODUCT_RESULTS",  5)
MAX_SUPPORT_RESULTS = getattr(settings, "RAG_MAX_SUPPORT_RESULTS",  3)
MAX_HISTORY_TURNS   = getattr(settings, "RAG_MAX_HISTORY_TURNS",    4)


# ── Data containers ───────────────────────────────────────────────────────────

@dataclass
class RetrievalResult:
    products:     list = field(default_factory=list)
    support_docs: list = field(default_factory=list)
    intent:       str  = "unknown"


@dataclass
class ChatResponse:
    answer:                str
    intent:                str
    retrieved_product_ids: list
    retrieved_support_ids: list
    latency_ms:            int
    parsed_intent:         "ParsedIntent" = None   # surfaced for API response + debugging
@dataclass
class ParsedIntent:
    """Structured result from the tradeoff parser. Always has a valid value — 
    the LLM path fills it from JSON, the fallback path fills it from regexes."""
    raw_intent:       str   = "product"   # product | support | hybrid
    max_price:        float = None        # e.g. 50.0 from "under $50"
    min_price:        float = None        # e.g. 20.0 from "at least $20"
    tradeoff:         str   = None        # "price_vs_quality" | "style_vs_comfort" | None
    preferred_colors: list  = field(default_factory=list)
    preferred_sizes:  list  = field(default_factory=list)
    keywords:         list  = field(default_factory=list)


# ── 1. Query Router ───────────────────────────────────────────────────────────

_PRODUCT_SIGNALS = frozenset([
    "find", "show", "recommend", "suggest", "looking for", "want", "buy", "shop",
    "dress", "shirt", "pants", "jeans", "jacket", "coat", "shoes", "boots",
    "outfit", "wear", "style", "color", "size", "price", "under $", "cheap",
    "affordable", "sale", "discount", "stock", "available", "collection",
    "tops", "bottoms", "skirt", "blazer", "hoodie", "sweater", "leggings",
    "swimwear", "activewear", "formal", "casual", "brand",
])

_SUPPORT_SIGNALS = frozenset([
    "return", "refund", "exchange", "policy", "ship", "shipping", "delivery",
    "track", "tracking", "order", "cancel", "warranty", "receipt",
    "how long", "when will", "damaged", "broken", "missing", "wrong item",
    "contact", "support", "help", "account", "payment", "charge", "invoice",
    "sizing guide", "size chart", "care instruction", "wash", "international",
    "customs", "duty", "store credit", "gift card",
])


class QueryRouter:
    """Two-pass intent router: keyword overlap -> embedding tiebreak."""

    def route(self, query: str) -> str:
        q = query.lower()
        tokens = set(re.findall(r"\b\w+\b", q))

        p = len(tokens & _PRODUCT_SIGNALS) + sum(1 for ph in _PRODUCT_SIGNALS if " " in ph and ph in q)
        s = len(tokens & _SUPPORT_SIGNALS) + sum(1 for ph in _SUPPORT_SIGNALS if " " in ph and ph in q)
        conn = bool(re.search(r"\b(and|also|plus|as well|along with)\b", q))

        if p > 0 and s > 0:        return "hybrid"
        if p > 0 and conn:         return "hybrid"
        if s > 0 and conn:         return "hybrid"
        if p >= s and p > 0:       return "product"
        if s > p:                  return "support"
        return self._embedding_tiebreak(query)

    def _embedding_tiebreak(self, query: str) -> str:
        try:
            mgr = get_index_manager()
            pr = mgr.search_products(query, k=1, score_threshold=0.2)
            sr = mgr.search_support(query,   k=1, score_threshold=0.2)
            ps = pr[0]["score"] if pr else 0.0
            ss = sr[0]["score"] if sr else 0.0
            if ps > 0.3 and ss > 0.3: return "hybrid"
            if ps > ss:               return "product"
            if ss > ps:               return "support"
        except Exception as e:
            logger.warning(f"Embedding tiebreak skipped: {e}")
        return "product"
# ── 1b. Tradeoff Parser ───────────────────────────────────────────────────────

# Prompt asking the LLM to return ONLY JSON — no prose, no markdown fences.
# Keeping it terse reduces token count and hallucination surface area.
_INTENT_PARSE_PROMPT = """\
You are a query-understanding module. Extract structured shopping intent from the user query.
Return ONLY a valid JSON object with these exact keys:
  raw_intent        : "product" | "support" | "hybrid"
  max_price         : number or null
  min_price         : number or null
  tradeoff          : "price_vs_quality" | "style_vs_comfort" | "brand_vs_price" | null
  preferred_colors  : list of strings (empty list if none)
  preferred_sizes   : list of strings (empty list if none)
  keywords          : list of 1-4 key product descriptors

User query: {query}
"""

# Known sizes — used by the deterministic fallback so we don't miss e.g. "XL"
_SIZE_TOKENS = {"xs", "s", "m", "l", "xl", "xxl", "2xl", "3xl",
                "6", "7", "8", "9", "10", "11", "12", "28", "30", "32", "34", "36"}
_COLOR_TOKENS = {
    "red", "blue", "green", "black", "white", "grey", "gray", "pink",
    "yellow", "purple", "orange", "brown", "beige", "navy", "cream", "teal",
}
_TRADEOFF_SIGNALS = {
    # Maps a regex pattern to a tradeoff label
    r"\b(cheap|budget|affordable|low.?price)\b.{0,30}\b(quality|good|best|premium)\b": "price_vs_quality",
    r"\b(quality|good|best|premium)\b.{0,30}\b(cheap|budget|affordable|low.?price)\b": "price_vs_quality",
    r"\b(style|stylish|trendy|fashion)\b.{0,30}\b(comfort|comfortable|cozy|soft)\b":   "style_vs_comfort",
    r"\b(comfort|comfortable|cozy|soft)\b.{0,30}\b(style|stylish|trendy|fashion)\b":   "style_vs_comfort",
    r"\b(brand|designer|name.?brand)\b.{0,30}\b(price|cost|budget|cheap)\b":           "brand_vs_price",
    r"\b(price|cost|budget|cheap)\b.{0,30}\b(brand|designer|name.?brand)\b":           "brand_vs_price",
}


class TradeoffParser:
    """
    Parses user queries into structured ParsedIntent objects.

    Strategy:
      1. Ask the LLM to return JSON (fast, low-token call — temp=0 for determinism).
      2. If JSON parsing fails for ANY reason, fall through to _keyword_fallback().
         The fallback is pure regex/string logic — it NEVER calls the LLM again,
         so a broken or slow Ollama doesn't block the main response.
    """

    def __init__(self, llm_client: "OllamaClient"):
        # Same client used by ChatEngine — no second connection needed
        self._llm = llm_client

    def parse(self, query: str) -> ParsedIntent:
        try:
            raw = self._llm.generate(
                messages=[{"role": "user", "content": _INTENT_PARSE_PROMPT.format(query=query)}],
                temperature=0.0,   # zero temp = most deterministic JSON output
            )
            return self._parse_json(raw, query)
        except Exception as e:
            # LLM down, timeout, or bad JSON — degrade silently to keyword extraction
            logger.warning(f"TradeoffParser LLM call failed ({type(e).__name__}), using keyword fallback: {e}")
            return self._keyword_fallback(query)

    def _parse_json(self, raw: str, query: str) -> ParsedIntent:
        # Strip markdown code fences the model sometimes adds despite instructions
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()

        # Find the first {...} block — guards against preamble text leaking in
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in LLM output")

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON decode failed: {e}")

        # Validate field types defensively — a hallucinated string for max_price
        # would cause a float() crash later during product filtering.
        def _safe_float(val) -> float:
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        return ParsedIntent(
            raw_intent       = str(data.get("raw_intent", "product")),
            max_price        = _safe_float(data.get("max_price")),
            min_price        = _safe_float(data.get("min_price")),
            tradeoff         = data.get("tradeoff") or None,
            preferred_colors = [str(c).lower() for c in data.get("preferred_colors", []) if c],
            preferred_sizes  = [str(s).upper() for s in data.get("preferred_sizes",  []) if s],
            keywords         = [str(k)         for k in data.get("keywords",         []) if k],
        )

    def _keyword_fallback(self, query: str) -> ParsedIntent:
        """
        Pure deterministic extraction — regex only, no LLM.
        Runs in <1ms. This is the safety net, not the happy path.
        """
        q = query.lower()
        tokens = set(re.findall(r"\b\w+\b", q))

        # Price extraction: "under $50", "below 80", "less than $30", "at least $20"
        max_price = None
        min_price = None
        m = re.search(r"\b(?:under|below|less than|max|maximum|up to)\s*\$?\s*(\d+(?:\.\d+)?)", q)
        if m:
            max_price = float(m.group(1))
        m = re.search(r"\b(?:at least|over|above|min|minimum|more than)\s*\$?\s*(\d+(?:\.\d+)?)", q)
        if m:
            min_price = float(m.group(1))

        # Tradeoff detection: scan the query against known signal pairs
        tradeoff = None
        for pattern, label in _TRADEOFF_SIGNALS.items():
            if re.search(pattern, q):
                tradeoff = label
                break

        colors = sorted(tokens & _COLOR_TOKENS)
        sizes  = sorted({t.upper() for t in tokens if t in _SIZE_TOKENS})

        # Keywords: strip stop words and price/size tokens, take up to 4
        stop = {"a", "an", "the", "i", "me", "my", "want", "need", "looking",
                "for", "find", "show", "get", "some", "any", "please", "can", "you"}
        kw = [t for t in re.findall(r"\b[a-z]{3,}\b", q)
              if t not in stop and t not in _COLOR_TOKENS and t not in _SIZE_TOKENS][:4]

        return ParsedIntent(
            raw_intent       = "product",   # fallback assumes product search
            max_price        = max_price,
            min_price        = min_price,
            tradeoff         = tradeoff,
            preferred_colors = colors,
            preferred_sizes  = sizes,
            keywords         = kw,
        )

# ── 2. Prompt Builder ─────────────────────────────────────────────────────────

class PromptBuilder:
    SYSTEM_PROMPT = (
        "You are a helpful, friendly shopping assistant for a clothing brand. "
        "Answer the customer's question using ONLY the provided context. "
        "For product recommendations, mention name, price, and key details. "
        "If the context does not have enough information, say so honestly — "
        "never invent products or policies. Be concise and warm."
    )

    def build_messages(self, query: str, retrieval: RetrievalResult,
                       history: list, parsed: ParsedIntent = None) -> list:
        msgs = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        for msg in history[-(MAX_HISTORY_TURNS * 2):]:
            msgs.append({"role": msg.role, "content": msg.content})
        ctx = self._build_context(retrieval)
        # Inject tradeoff context so the LLM explicitly acknowledges the user's tension
        # rather than just picking the cheapest or first result.
        tradeoff_hint = ""
        if parsed and parsed.tradeoff:
            labels = {
                "price_vs_quality": "The user is weighing price against quality. Acknowledge this tradeoff and explain your recommendation.",
                "style_vs_comfort": "The user is weighing style against comfort. Address both dimensions.",
                "brand_vs_price":   "The user is deciding between a trusted brand and a lower price. Help them reason through it.",
            }
            hint = labels.get(parsed.tradeoff, "")
            if hint:
                tradeoff_hint = f"\n[TRADEOFF DETECTED: {hint}]"
        msgs.append({"role": "user", "content": f"Context:\n{ctx}{tradeoff_hint}\n\nCustomer question: {query}"})
        return msgs
    def _build_context(self, r: RetrievalResult) -> str:
        sections = []
        if r.products:
            lines = ["[PRODUCTS]"]
            for p in r.products:
                stock  = "In Stock" if p["stock"] > 0 else "Out of Stock"
                colors = ", ".join(p["colors"]) if p["colors"] else "N/A"
                sizes  = ", ".join(p["sizes"])  if p["sizes"]  else "N/A"
                lines.append(f"- {p['name']} | ${p['price']:.2f} | Colors: {colors} | Sizes: {sizes} | {stock} | SKU: {p['sku']}")
            sections.append("\n".join(lines))
        if r.support_docs:
            lines = ["[POLICIES & SUPPORT]"]
            for d in r.support_docs:
                lines.append(f"[{d['doc_type'].upper()}] {d['title']}\n{d['content']}")
            sections.append("\n\n".join(lines))
        return "\n\n".join(sections) if sections else "No relevant context found."


# ── 3. Ollama Client ──────────────────────────────────────────────────────────

class OllamaClient:
    """
    Streaming Ollama wrapper.

    WHY STREAMING FIXES THE TIMEOUT
    --------------------------------
    Non-streaming (stream=False): Django waits for the complete response body
    before reading a single byte. Llama3 generating 512 tokens on CPU takes
    90-150 s — well past the old 60 s flat timeout.

    Streaming (stream=True + iter_lines): Django reads each JSON line the moment
    Ollama emits it. The socket reset timer only fires if there is SILENCE for
    read_timeout seconds. Active token generation keeps the socket alive
    indefinitely, so practical generation time is no longer a timeout risk.
    """

    def __init__(self):
        self.base_url = OLLAMA_BASE_URL.rstrip("/")
        self.model    = OLLAMA_MODEL
        self._ok      = False   # health-check latch

    def generate(self, messages: list, temperature: float = 0.3) -> str:
        self._health_check()
        payload = {
            "model":    self.model,
            "messages": messages,
            "stream":   True,   # ← THE KEY FIX
            "options": {"temperature": temperature, "top_p": 0.9, "num_predict": 512},
        }
        last_exc = None
        for attempt in range(1, OLLAMA_RETRIES + 1):
            try:
                return self._stream(payload)
            except RuntimeError:
                raise
            except Exception as e:
                last_exc = e
                logger.warning(f"Ollama attempt {attempt}/{OLLAMA_RETRIES}: {e}")
                if attempt < OLLAMA_RETRIES:
                    time.sleep(1)
        raise RuntimeError(f"AI model failed after {OLLAMA_RETRIES} attempts. Please try again.")

    def _stream(self, payload: dict) -> str:
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=OLLAMA_TIMEOUT,   # (connect=5s, read=180s)
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.base_url}.\n"
                "Run:  ollama serve\n"
                f"Pull: ollama pull {self.model}"
            )
        except requests.exceptions.ConnectTimeout:
            raise RuntimeError(
                f"Ollama did not respond within {OLLAMA_TIMEOUT[0]}s. Is `ollama serve` running?"
            )

        tokens = []
        try:
            for raw in resp.iter_lines():
                if not raw:
                    continue
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("message", {}).get("content", "")
                if token:
                    tokens.append(token)
                if chunk.get("done", False):
                    break
        except requests.exceptions.ChunkedEncodingError as e:
            if tokens:
                logger.warning(f"Stream ended early — partial response recovered: {e}")
            else:
                raise RuntimeError("Ollama stream cut before any output. Try again.")

        result = "".join(tokens).strip()
        if not result:
            raise RuntimeError("Ollama returned an empty response. Is the model loaded?")
        return result

    def _health_check(self):
        if self._ok:
            return
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=(5, 10))
            r.raise_for_status()
            self._ok = True
            logger.info(f"Ollama reachable at {self.base_url} | model={self.model}")
        except Exception as e:
            raise RuntimeError(
                f"Ollama is not reachable at {self.base_url}.\n"
                f"Steps to fix:\n"
                f"  1. ollama serve\n"
                f"  2. ollama pull {self.model}\n"
                f"Error: {e}"
            )


# ── 4. Chat Engine ────────────────────────────────────────────────────────────

class ChatEngine:
    def __init__(self):
        self.router         = QueryRouter()
        self.prompt_builder = PromptBuilder()
        self.llm            = OllamaClient()
        # Parser is wired after llm so it can reuse the same client instance
        self.tradeoff_parser = TradeoffParser(self.llm)

    def respond(self, query: str, session_id: str) -> ChatResponse:
        t0 = time.time()
        conv, _  = Conversation.objects.get_or_create(session_id=session_id)
        history  = list(conv.messages.order_by("created_at"))
        intent        = self.router.route(query)
        parsed        = self.tradeoff_parser.parse(query)
        # Prefer the richer LLM-parsed intent when it disagrees with the keyword router,
        # but only for product/hybrid — the keyword router is more reliable for support.
        if parsed.raw_intent in ("product", "hybrid") and intent == "product":
            intent = parsed.raw_intent
        logger.debug(
            f"[{session_id[:8]}] intent={intent} | tradeoff={parsed.tradeoff} "
            f"| price=({parsed.min_price},{parsed.max_price}) | q={query[:60]}"
        )
        retrieval = self._retrieve(query, intent, parsed)
        messages  = self.prompt_builder.build_messages(query, retrieval, history, parsed)
        answer    = self.llm.generate(messages)
        latency   = int((time.time() - t0) * 1000)
        pids = [p["db_id"] for p in retrieval.products]
        sids = [d["db_id"] for d in retrieval.support_docs]
        Message.objects.create(conversation=conv, role="user",      content=query,  intent=intent)
        Message.objects.create(
            conversation=conv, role="assistant", content=answer, intent=intent,
            retrieved_product_ids=pids, retrieved_support_ids=sids, latency_ms=latency,
        )
        logger.info(f"[{session_id[:8]}] {latency}ms | intent={intent}")
        return ChatResponse(answer=answer, intent=intent,
                            retrieved_product_ids=pids, retrieved_support_ids=sids,
                            latency_ms=latency, parsed_intent=parsed)

    def _retrieve(self, query: str, intent: str, parsed: ParsedIntent = None) -> RetrievalResult:
        result = RetrievalResult(intent=intent)
        try:
            mgr = get_index_manager()
            if intent in ("product", "hybrid"):
                products = mgr.search_products(query, k=MAX_PRODUCT_RESULTS)
                # Apply deterministic price/size filters from ParsedIntent.
                # Doing this in Python (not in the prompt) keeps filtering exact and auditable.
                if parsed:
                    if parsed.max_price is not None:
                        products = [p for p in products if p["price"] <= parsed.max_price]
                    if parsed.min_price is not None:
                        products = [p for p in products if p["price"] >= parsed.min_price]
                    if parsed.preferred_sizes:
                        # Soft filter: keep items that have at least one requested size
                        sized = [p for p in products if any(s in p.get("sizes", []) for s in parsed.preferred_sizes)]
                        products = sized if sized else products  # don't hard-fail if no match
                    if parsed.preferred_colors:
                        colored = [p for p in products if any(c in [x.lower() for x in p.get("colors", [])] for c in parsed.preferred_colors)]
                        products = colored if colored else products
                result.products = products
            if intent in ("support", "hybrid"):
                result.support_docs = mgr.search_support(query, k=MAX_SUPPORT_RESULTS)
            if intent == "hybrid" and len(result.products) > 3:
                result.products = result.products[:3]
        except RuntimeError as e:
            logger.warning(f"FAISS unavailable (continuing without retrieval): {e}")
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine = None


def get_chat_engine() -> ChatEngine:
    global _engine
    if _engine is None:
        _engine = ChatEngine()
    return _engine
