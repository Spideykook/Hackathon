from django.db import models
from django.contrib.postgres.fields import ArrayField


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    GENDER_CHOICES = [("M", "Men"), ("W", "Women"), ("U", "Unisex"), ("K", "Kids")]

    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=100, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default="U")
    sizes_available = ArrayField(models.CharField(max_length=10), default=list)
    colors = ArrayField(models.CharField(max_length=50), default=list)
    tags = ArrayField(models.CharField(max_length=50), default=list)
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, unique=True)
    image_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    # RAG tracking
    embedding_id = models.IntegerField(null=True, blank=True)  # FAISS index position
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def effective_price(self):
        return self.sale_price if self.sale_price else self.price

    def to_embedding_text(self) -> str:
        """Canonical text representation used for embedding generation."""
        parts = [
            f"Product: {self.name}",
            f"Brand: {self.brand}" if self.brand else "",
            f"Category: {self.category.name}" if self.category else "",
            f"Gender: {self.get_gender_display()}",
            f"Price: ${self.effective_price}",
            f"Colors: {', '.join(self.colors)}" if self.colors else "",
            f"Sizes: {', '.join(self.sizes_available)}" if self.sizes_available else "",
            f"Tags: {', '.join(self.tags)}" if self.tags else "",
            f"Description: {self.description}",
            f"In Stock: {'Yes' if self.stock > 0 else 'No'}",
        ]
        return "\n".join(filter(None, parts))

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "stock"]),
            models.Index(fields=["price"]),
            models.Index(fields=["gender"]),
        ]
