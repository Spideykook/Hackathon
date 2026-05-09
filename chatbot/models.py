from django.db import models
import uuid


class Conversation(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata   = models.JSONField(default=dict, blank=True)

    # ── Cart state helpers ────────────────────────────────────────────────────
    # We store cart in metadata["cart"] rather than a separate model because
    # cart state is ephemeral per-session. A full CartItem table would need
    # cleanup jobs; this collapses with the conversation naturally.

    def get_cart(self) -> dict:
        """Returns the canonical cart dict, creating it if missing."""
        if "cart" not in self.metadata:
            self.metadata["cart"] = {"state": "BROWSING", "items": [], "order_id": None}
        return self.metadata["cart"]

    def save_cart(self, cart: dict):
        """Persists cart back to metadata and saves the row."""
        self.metadata["cart"] = cart
        # update_fields avoids overwriting metadata keys written by other processes
        self.save(update_fields=["metadata", "updated_at"])

    def __str__(self):
        return f"Conversation {self.session_id}"


class Message(models.Model):
    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant")]
    INTENT_CHOICES = [
        ("product", "Product Search"),
        ("support", "Support/FAQ"),
        ("hybrid", "Hybrid"),
        ("unknown", "Unknown"),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    intent = models.CharField(max_length=10, choices=INTENT_CHOICES, default="unknown")
    retrieved_product_ids = models.JSONField(default=list, blank=True)
    retrieved_support_ids = models.JSONField(default=list, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"
