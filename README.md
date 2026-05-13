# Kasparro — Conversational Shopping Agent
**Track 1: AI Shopping Agent** · Kasparro Agentic Commerce Hackathon

> Replace the browse-filter loop with a single conversation that understands tradeoffs, tracks a cart deterministically, and degrades safely when the LLM fails.

---

## The Problem

Standard e-commerce filter UIs assume the user knows exactly what they want and can express it as checkbox values. They break for complex purchases:

- A user weighing "affordable but good quality running shoes" has a tension, not a filter value.
- Multi-intent queries ("waterproof jacket — also what's the return policy?") hit two backend systems; filter UIs can only route to one.
- Each page load resets context. Changing your mind means starting over.
- The gap between "I like this" and "I bought this" is multiple page transitions with high drop-off.

## The Solution

A single conversational agent handles the full purchase funnel in one session:

1. Understands natural language queries — including tradeoffs like price vs. quality.
2. Retrieves semantically relevant products via FAISS vector search.
3. Applies price/size/color filters in Python (not in the prompt) for exact results.
4. Manages cart state through a deterministic state machine — no LLM involvement in checkout.
5. Guards against hallucinated product names and prices before the answer reaches the user.
6. Degrades safely when Ollama is unreachable: regex-based intent extraction, deterministic cart ops, and template-built product lists all continue working without the LLM.

---

## Architecture

```
User message
    │
    ▼
TradeoffParser       → structured intent + filters (LLM @ temp=0, regex fallback)
    │
    ▼
FAISS retrieval      → top-k products/support docs, Python-filtered by price/size/color
    │
    ▼
CheckoutStateMachine → cart transitions on keyword triggers (pure Python, no LLM)
    │   (if cart event: short-circuit, skip LLM entirely)
    ▼
Llama 3 via Ollama   → answer generation with tradeoff hint injected into prompt
    │
    ▼
HallucinationGuard   → cross-checks prices + product names against retrieval context
    │   (if flagged: deterministic Python fallback, LLM answer discarded)
    ▼
JSON response        → answer, cart state, tradeoff field, filters applied
    │
    ▼
Vanilla JS frontend  → async fetch, markdown render, background cart sync, tradeoff badge
```

**Stack:**

| Layer | Technology |
|---|---|
| Backend framework | Django 4.x + Django REST Framework |
| Vector search | FAISS (`faiss-cpu`) with `all-MiniLM-L6-v2` embeddings |
| LLM | Llama 3 (via Ollama, local inference) |
| Frontend | Vanilla JS — Fetch API, no framework, no build step |
| Database | PostgreSQL (cart state in `Conversation.metadata` JSONField) |

---

## Key Features

### Tradeoff Parser
Detects when a user is weighing competing priorities (`price_vs_quality`, `style_vs_comfort`, `brand_vs_price`) via a structured LLM call at temperature 0. If JSON parsing fails or Ollama is unreachable, a pure-regex fallback runs in <1ms with no user-visible degradation. Price/size/color filters are applied in Python post-retrieval — the LLM cannot override them.

### Deterministic Checkout State Machine
Four states: `BROWSING → AWAITING_CONFIRM → CONFIRMED → CHECKOUT_COMPLETE`. Transitions fire on keyword triggers, never on LLM output. Cart contents are stored in `Conversation.metadata` (PostgreSQL JSONField) — persisted, auditable, and immune to LLM hallucination. Cart operations short-circuit the LLM entirely, dropping response latency from ~5–90s to <5ms for checkout interactions.

### Hallucination Guard
After generation, every price mentioned in the LLM's answer is checked against the retrieval context (±$0.50 tolerance). Capitalised n-grams are checked against known product names via word-overlap ratio. One unverifiable price or suspicious product reference discards the entire LLM answer and replaces it with a Python-built response from the raw product list.

### Asynchronous Frontend
Single-page chat — no page reloads. User message appears in the DOM before the fetch fires. Background cart sync after each response (not awaited; silent on failure). Tradeoff badge rendered above the assistant's bubble when the backend detects a tradeoff. Network errors surface as red message bubbles in the conversation, not as `alert()` or console noise.

---

## Local Setup

**Requirements:** Python 3.10+, PostgreSQL, [Ollama](https://ollama.com/download)

```bash
# 1. Clone and create virtualenv
git clone <repo-url> kasparro
cd kasparro
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
# Note: sentence-transformers (~80MB) downloads the embedding model on first run

# 3. Configure environment
cp .env.example .env               # edit DB credentials if needed
# Defaults: DB=core_db, Ollama=http://localhost:11434, model=llama3

# 4. Set up the database
createdb core_db                   # PostgreSQL must be running
python manage.py migrate

# 5. Seed demo products and build FAISS indices
python manage.py seed_demo
python manage.py rebuild_index

# 6. Start Ollama and pull the model (first run only)
ollama serve &
ollama pull llama3

# 7. Collect static files and run
python manage.py collectstatic --no-input
python manage.py runserver
```

Open `http://127.0.0.1:8000` — the chat interface loads immediately.

**Verify the agent is healthy:**
```bash
curl -s -X POST http://127.0.0.1:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "show me running shoes under $80"}' | python -m json.tool
```

Expected: JSON with `answer`, `cart`, `tradeoff`, and `filters_applied` fields.

**If Ollama is not running:** The `TradeoffParser` will fall back to regex-based intent extraction. The cart state machine and hallucination guard continue operating normally. You'll see a 503 from the main LLM generation step, with a user-visible error bubble in the chat.

---

## Hackathon Documentation

The deeper engineering reasoning lives in three documents at the repo root:

| Document | Contents |
|---|---|
| [`PRODUCT.md`](./PRODUCT.md) | Problem framing, user journey through cart states, scope decisions, tradeoff handling |
| [`TECHNICAL.md`](./TECHNICAL.md) | System architecture, AI/deterministic boundary rationale, failure scenarios, known limitations |
| [`DECISIONS.md`](./DECISIONS.md) | 6 ADR-style entries: why each key design choice was made, what alternatives were considered, what was traded off |

---

## Repository Structure

```
kasparro/
├── chatbot/
│   ├── services.py        # TradeoffParser, CheckoutStateMachine, HallucinationGuard, ChatEngine
│   ├── views.py           # ChatView, CartView, HistoryView, ResetView
│   ├── models.py          # Conversation (+ cart helpers), Message
│   ├── indexing.py        # FAISS dual-index (products + support docs)
│   ├── static/js/chat.js  # Async frontend — fetch, cart sync, tradeoff badge, markdown
│   └── templates/chatbot/chat.html
├── products/
│   └── models.py          # Product model with to_embedding_text()
├── core/
│   └── settings.py        # Ollama URL/model, FAISS paths, embedding model
├── PRODUCT.md
├── TECHNICAL.md
├── DECISIONS.md
└── requirements.txt
```
