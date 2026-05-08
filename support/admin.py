from django.contrib import admin
from .models import SupportDocument, SupportCategory


@admin.register(SupportCategory)
class SupportCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "priority"]
    ordering     = ["-priority"]


@admin.register(SupportDocument)
class SupportDocumentAdmin(admin.ModelAdmin):
    list_display   = ["title", "doc_type", "category", "is_active", "embedding_updated_at"]
    list_filter    = ["doc_type", "is_active", "category"]
    search_fields  = ["title", "question", "content", "keywords"]
    list_editable  = ["is_active"]
    readonly_fields = ["embedding_id", "embedding_updated_at", "created_at", "updated_at"]

    fieldsets = (
        ("Content",   {"fields": ("title", "doc_type", "category", "question", "content", "keywords")}),
        ("Status",    {"fields": ("is_active",)}),
        ("RAG",       {"fields": ("embedding_id", "embedding_updated_at"), "classes": ("collapse",)}),
        ("Timestamps",{"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = ["rebuild_support_embeddings"]

    @admin.action(description="Rebuild FAISS embeddings (all active support docs)")
    def rebuild_support_embeddings(self, request, queryset):
        from chatbot.indexing import IndexManager
        IndexManager().rebuild_support()
        self.message_user(request, "Support FAISS index rebuilt successfully.")
