from django.contrib import admin
from .models import Product, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display   = ["name", "sku", "category", "effective_price", "stock", "gender", "is_active", "embedding_updated_at"]
    list_filter    = ["is_active", "gender", "category"]
    search_fields  = ["name", "sku", "tags"]
    list_editable  = ["is_active", "stock"]
    readonly_fields = ["embedding_id", "embedding_updated_at", "created_at", "updated_at"]

    fieldsets = (
        ("Core",      {"fields": ("name", "sku", "brand", "category", "gender", "description")}),
        ("Pricing",   {"fields": ("price", "sale_price")}),
        ("Inventory", {"fields": ("stock", "sizes_available", "colors", "is_active")}),
        ("Discovery", {"fields": ("tags", "image_url")}),
        ("RAG",       {"fields": ("embedding_id", "embedding_updated_at"), "classes": ("collapse",)}),
        ("Timestamps",{"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = ["rebuild_product_embeddings"]

    @admin.action(description="Rebuild FAISS embeddings (all active products)")
    def rebuild_product_embeddings(self, request, queryset):
        from chatbot.indexing import IndexManager
        IndexManager().rebuild_products()
        self.message_user(request, "Product FAISS index rebuilt successfully.")
