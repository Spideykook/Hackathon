# PRODUCT.md — Kasparro AI Shopping Agent

## The Problem

Standard e-commerce browse-filter loops fail for complex purchases. The underlying assumption — that users know exactly what they want and can express it as a set of checkboxes — breaks down in practice.

Specific failure modes:

- **Filters don't handle tradeoffs.** A user who says "I want good quality boots but I can't spend a lot" has a tension, not a filter value. A price slider and a "sort by rating" dropdown don't resolve it — they just push the decision back to the user.
- **Each page load resets context.** Category → subcategory → filter → product detail is a stateless funnel. If a user changes their mind mid-way (different size, different budget), they restart from zero.
- **Multi-intent queries break routing.** "I need a waterproof jacket for hiking, what's your return policy if it doesn't fit?" hits two different backend systems. A filter UI can't handle this. Most chatbots route to one or the other and drop half the question.
- **Checkout is a cliff edge.** The gap between "I found something I like" and "I placed an order" requires multiple page transitions. Users drop off here at a high rate, especially on mobile.

---

## The User Journey

The conversational state machine changes the experience across four stages:

**Stage 1 — BROWSING**
User describes what they want in natural language. The system parses intent (product vs. support vs. hybrid), extracts structured filters (price range, size, color), detects any tradeoff tension, and retrieves the top-5 matching products from FAISS. The LLM generates a response that explicitly addresses the tradeoff if one was detected.

**Stage 2 — AWAITING_CONFIRM**
When the user signals they want an item ("I'll take this one", "add it to my cart", "yes"), the system identifies the best candidate from the last retrieval result and asks for a single explicit confirmation. This step exists specifically to prevent accidental adds from ambiguous turns like "that sounds good" mid-conversation.

**Stage 3 — CONFIRMED**
Item is committed to the in-session cart. User sees a running total and item count. They can continue browsing (add more items) or proceed to checkout. The LLM stays in the loop for browsing queries; cart state is managed entirely in Python.

**Stage 4 — CHECKOUT_COMPLETE**
Triggered by explicit checkout intent ("checkout", "place order", "pay"). A deterministic order ID is generated. The session is locked. No further cart modifications are possible without starting a new session.

At any point, the user can say "clear my cart" or "start over" to reset to BROWSING.

---

## Scope Decisions

**What we did NOT build, and why:**

- **Persistent user accounts / saved carts.** Cart state lives in `Conversation.metadata` (a session-scoped JSONField). This was a deliberate call: persisting carts across sessions requires auth, which is out of scope for a hackathon demo. The architecture supports upgrading to a proper `Cart` model without breaking the state machine logic.

- **Payment integration.** The checkout step generates an order ID and locks the session. A real payment gateway (Stripe, Razorpay) would slot in at the `_complete_checkout()` transition. We left this as a clear seam rather than mock it with fake flows.

- **LLM-managed cart state.** We explicitly chose NOT to let the LLM track what's in the cart between turns. The LLM has no persistent memory, it can hallucinate SKUs, and prompting it to "remember" the cart adds tokens to every call. Python with a JSON dict is faster, cheaper, and testable.

- **Product image rendering.** The API returns product IDs; the frontend can hydrate from the products endpoint. Building a full product card UI was deprioritised in favour of getting the state machine and safety layers right.

- **Multi-item disambiguation.** When a user says "add this one" and five products were retrieved, we pick the first result. A more complete implementation would ask "which of these did you mean?" but for a single-session demo, first-match is auditable and correct often enough.

---

## Tradeoff Handling

The `TradeoffParser` detects three classes of tension in a user's query:

| Tradeoff | Example query | Detection method |
|---|---|---|
| `price_vs_quality` | "cheap but good quality running shoes" | Regex: price-signal words near quality-signal words within 30 chars |
| `style_vs_comfort` | "stylish but comfortable work boots" | Regex: style-signal words near comfort-signal words |
| `brand_vs_price` | "name brand hoodie but not too expensive" | Regex: brand-signal words near price-signal words |

When a tradeoff is detected, two things happen:

1. **Filtering is adjusted in Python.** Price bounds extracted from the query (`max_price`, `min_price`) are applied to the FAISS retrieval results before the LLM sees them. The LLM cannot override these — if a user said "under $60", products over $60 are removed from context entirely.

2. **The LLM receives an explicit instruction.** A tradeoff hint is injected into the prompt: `"The user is weighing price against quality. Acknowledge this tradeoff and explain your recommendation."` This prevents the LLM from defaulting to the cheapest or first option without comment.

The detection is purely regex-based and runs in the keyword fallback path if the LLM intent parse fails — so tradeoff awareness degrades gracefully even when Ollama is down.

---

## Frontend Experience

The chat UI is a single-page interface — no page reloads, no form submissions. Four specific decisions shape what the user sees:

**Immediate message rendering.** The user's message appears in the DOM the moment they hit Enter, before the fetch has been made. This removes the dead-click feeling of traditional form submission. The "Agent is thinking…" typing indicator (three animated dots) appears simultaneously, giving the user a clear signal that the request is in flight.

**Silent cart updates.** After every chat response, a background `fetch()` call hits `/api/cart/` and updates the cart counter in the header (`🛒 2 · $89.98`). This fires without being awaited — it cannot block or error the chat flow. If the cart fetch fails (network blip, server timeout), the counter simply doesn't update. The user never sees an error for a supplementary UI element.

**The Tradeoff Badge.** When the backend's `TradeoffParser` detects a tradeoff in the user's query, the API response includes a `tradeoff` field (e.g., `"price_vs_quality"`). The frontend renders a small badge directly above the assistant's message bubble:

> ⚖️ Balancing Price vs. Quality

This makes the agent's reasoning visible. The user can see it registered the tension in their request rather than silently picking the cheapest option. The badge is injected via JavaScript — it's not part of the LLM's answer text, so it's always well-formatted and never hallucinated.

**Network error in chat, not in the console.** If the `fetch()` to `/api/chat/` fails (connection drop, server restart), the error surfaces as a red message bubble inside the conversation — the same visual channel the user is already looking at. There's no `alert()`, no silent failure, no redirect to an error page.