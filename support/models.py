from django.db import models


class SupportCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)  # e.g., "Returns", "Shipping", "Sizing"
    priority = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name_plural = "support categories"
        ordering = ["-priority"]

    def __str__(self):
        return self.name


class SupportDocument(models.Model):
    """
    Stores FAQ entries, policy pages, and any business documentation.
    Each record is one logical "chunk" — keep content focused and atomic
    so retrieval is precise. For long policies, split into multiple records.
    """
    DOC_TYPES = [
        ("faq", "FAQ"),
        ("policy", "Policy"),
        ("guide", "Guide"),
        ("shipping", "Shipping Info"),
    ]

    title = models.CharField(max_length=255)
    category = models.ForeignKey(SupportCategory, on_delete=models.SET_NULL, null=True, blank=True)
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES, default="faq")
    question = models.TextField(
        blank=True,
        help_text="For FAQ entries: the triggering question. For policies: leave blank.",
    )
    content = models.TextField(help_text="The answer / policy body. Keep focused — one topic per record.")
    keywords = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma-separated keywords to boost retrieval accuracy.",
    )
    is_active = models.BooleanField(default=True)

    # RAG tracking
    embedding_id = models.IntegerField(null=True, blank=True)
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def to_embedding_text(self) -> str:
        """Canonical text used for embedding. Combines question + content for dense context."""
        parts = []
        if self.question:
            parts.append(f"Q: {self.question}")
        parts.append(f"A: {self.content}")
        if self.keywords:
            parts.append(f"Keywords: {self.keywords}")
        return "\n".join(parts)

    class Meta:
        indexes = [
            models.Index(fields=["doc_type", "is_active"]),
        ]
