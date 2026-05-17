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
from products.models import Product

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

        pi = resp.parsed_intent

        # conv_obj MUST be fetched before use — do not reference it before this block
        try:
            conv_obj = Conversation.objects.get(session_id=session_id)
            cart     = conv_obj.get_cart()
        except Conversation.DoesNotExist:
            cart = {"state": "BROWSING", "items": [], "order_id": None}

        return Response({
            "answer":             resp.answer,
            "intent":             resp.intent,
            "session_id":         session_id,
            "retrieved_products": resp.retrieved_product_ids,
            "latency_ms":         resp.latency_ms,
            "tradeoff":           pi.tradeoff if pi else None,
            "filters_applied": {
                "max_price": pi.max_price if pi else None,
                "min_price": pi.min_price if pi else None,
                "colors":    pi.preferred_colors if pi else [],
                "sizes":     pi.preferred_sizes  if pi else [],
            },
            "cart": {
                "state":    cart.get("state", "BROWSING"),
                "items":    cart.get("items", []),
                "order_id": cart.get("order_id"),
                "total":    round(sum(i["price"] for i in cart.get("items", [])), 2),
            },
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
        try:
            conv = Conversation.objects.get(session_id=session_id)
            conv.messages.all().delete()
            # Clear cart state too — otherwise it bleeds into the new session
            conv.metadata = {}
            conv.save(update_fields=["metadata", "updated_at"])
        except Conversation.DoesNotExist:
            pass
        return Response({"session_id": session_id, "cleared": True})
# ── API: GET/DELETE /api/cart/ ────────────────────────────────────────────────

class CartView(APIView):
    """
    Read-only cart endpoint for the frontend to render the cart sidebar.
    Cart mutation happens exclusively through the chat API — keeping a single
    write path prevents the cart state from going out of sync.
    """

    def get(self, request):
        session_id = _validated_session(request.query_params.get("session_id"))
        try:
            conv = Conversation.objects.get(session_id=session_id)
            cart = conv.get_cart()
        except Conversation.DoesNotExist:
            cart = {"state": "BROWSING", "items": [], "order_id": None}

        items = cart.get("items", [])
        return Response({
            "session_id": session_id,
            "cart_state": cart.get("state", "BROWSING"),
            "order_id":   cart.get("order_id"),
            "items":      items,
            "item_count": len(items),
            "total":      round(sum(i["price"] for i in items), 2),
        })

    def delete(self, request):
        """Hard-clears the cart (e.g., user clicks 'Empty Cart' button)."""
        session_id = _validated_session(request.query_params.get("session_id"))
        try:
            conv = Conversation.objects.get(session_id=session_id)
            conv.save_cart({"state": "BROWSING", "items": [], "order_id": None})
        except Conversation.DoesNotExist:
            pass
        return Response({"session_id": session_id, "cart_state": "BROWSING", "items": [], "total": 0.0})
