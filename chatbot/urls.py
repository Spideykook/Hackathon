from django.urls import path
from .views import (
    HomePageView, ChatPageView,
    ChatView, ConversationHistoryView, ConversationResetView,
    CartView,
)

urlpatterns = [
    # Pages
    path("",      HomePageView.as_view(), name="home"),
    path("chat/", ChatPageView.as_view(), name="chat-page"),

    # Chat API
    path("api/chat/",         ChatView.as_view(),               name="api-chat"),
    path("api/chat/history/", ConversationHistoryView.as_view(), name="api-chat-history"),
    path("api/chat/reset/",   ConversationResetView.as_view(),   name="api-chat-reset"),

    # Cart API — read via GET, hard-clear via DELETE
    path("api/cart/",         CartView.as_view(),                name="api-cart"),
]