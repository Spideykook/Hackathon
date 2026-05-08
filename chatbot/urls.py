from django.urls import path
from .views import HomePageView, ChatPageView, ChatView, ConversationHistoryView, ConversationResetView

urlpatterns = [
    # Pages
    path("",      HomePageView.as_view(), name="home"),
    path("chat/", ChatPageView.as_view(), name="chat-page"),

    # REST API
    path("api/chat/",         ChatView.as_view(),               name="api-chat"),
    path("api/chat/history/", ConversationHistoryView.as_view(), name="api-chat-history"),
    path("api/chat/reset/",   ConversationResetView.as_view(),   name="api-chat-reset"),
]
