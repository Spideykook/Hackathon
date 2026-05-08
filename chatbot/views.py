"""
chatbot/views.py  [MODIFIED]

Endpoints:
  GET  /              → HomePageView    (templates/home.html)
  GET  /chat/         → ChatPageView    (chatbot/templates/chatbot/chat.html)
  POST /api/chat/     → ChatView
  GET  /api/chat/history/
  POST /api/chat/reset/
"""

import uuid
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from django.views.generic import TemplateView

from .services import get_chat_engine
from .models import Conversation, Message

logger = logging.getLogger(__name__)


# ── Rate throttle ─────────────────────────────────────────────────────────────

class ChatRateThrottle(AnonRateThrottle):
    rate = "60/min"


# ── Helper ────────────────────────────────────────────────────────────────────

def _validated_session(raw) -> str:
    if not raw:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(str(raw)))
    except ValueError:
        return str(uuid.uuid4())


# ── Page views ────────────────────────────────────────────────────────────────

class HomePageView(TemplateView):
    """Landing page at /"""
    template_name = "home.html"


class ChatPageView(TemplateView):
    """Chat UI at /chat/"""
    template_name = "chatbot/chat.html"


# ── API: POST /api/chat/ ──────────────────────────────────────────────────────

class ChatView(APIView):
    throttle_classes = [ChatRateThrottle]

    def post(self, request):
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response({"error": "message is required."}, status=status.HTTP_400_BAD_REQUEST)
        if len(message) > 1000:
            return Response({"error": "message too long (max 1000 chars)."}, status=status.HTTP_400_BAD_REQUEST)

        session_id = _validated_session(request.data.get("session_id"))

        try:
            engine = get_chat_engine()
            resp   = engine.respond(message, session_id)
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.exception(f"Unhandled ChatView error: {e}")
            return Response({"error": "Unexpected error. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "answer":                resp.answer,
            "intent":                resp.intent,
            "session_id":            session_id,
            "retrieved_products":    resp.retrieved_product_ids,
            "retrieved_support_ids": resp.retrieved_support_ids,
            "latency_ms":            resp.latency_ms,
        })


# ── API: GET /api/chat/history/ ───────────────────────────────────────────────

class ConversationHistoryView(APIView):
    def get(self, request):
        session_id = _validated_session(request.query_params.get("session_id"))
        try:
            conv = Conversation.objects.get(session_id=session_id)
        except Conversation.DoesNotExist:
            return Response({"session_id": session_id, "messages": []})

        msgs = (
            conv.messages
            .order_by("-created_at")[:20]
            .values("role", "content", "intent", "created_at")
        )
        return Response({"session_id": session_id, "messages": list(reversed(list(msgs)))})


# ── API: POST /api/chat/reset/ ────────────────────────────────────────────────

class ConversationResetView(APIView):
    def post(self, request):
        session_id = _validated_session(request.data.get("session_id"))
        count = 0
        try:
            conv  = Conversation.objects.get(session_id=session_id)
            count, _ = conv.messages.all().delete()
        except Conversation.DoesNotExist:
            pass
        return Response({"session_id": session_id, "messages_deleted": count})
