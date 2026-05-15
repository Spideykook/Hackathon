# Contribution Note — Kasparro AI Shopping Agent
**Track 1: AI Shopping Agent** · Solo Submission
**Participant:** Bedaanntica Paul

---

## Time Allocation

Total time invested: approximately 2-3 hours daily across 6-7 days.

|                 Area                 | Approximate Split | Hours  |
---------------------------------------------------------------------
| Product Thinking & Scope Decisions   | 40%               | ~6 hrs |
| Technical Execution & Implementation | 60%               | ~7 hrs |

I took an iterative, vertical-slice approach. Rather than designing the whole system upfront, I mapped out the core "price vs. quality" tradeoff user journey first, built the pipeline to support that specific flow, and then layered on the checkout state machine and UI polish.

---

## Product Thinking & Scope Decisions

- **Problem framing:** Standard browse-and-filter loops fail when users weigh competing attributes. I identified that simply matching keywords isn't enough; the agent needed to explicitly recognize user tension (e.g., "cheap but good quality"). This made the tradeoff detection engine a core requirement, not an edge case.
- **Defining the AI/Deterministic boundary:** LLMs excel at extracting unstructured intent but fail at strict math and state retention. I made a hard rule: the LLM (Llama 3) only extracts intent and parameters (JSON). Pure Python handles the actual price filtering, inventory checks, and cart state to guarantee accuracy.
- **Designing the checkout state machine:** I defined a strict, deterministic state flow (`BROWSING` → `COMPARING` → `CHECKOUT_CONFIRM`). Forcing a confirmation step in Python prevents the system from accidentally adding items to a cart based on an ambiguous or hallucinated LLM affirmative response.
- **Scoping what not to build:** I deliberately chose to use local synthetic product data rather than integrating the live Shopify API. This eliminated network latency and rate-limit variables, allowing me to focus 100% of my time on testing the core AI/Deterministic boundary and ensuring the fallback mechanisms worked.

---

## Technical Execution

- **Django backend & API layer:** Structured the `ChatEngine` to coordinate retrieval, routing, and prompt building. I utilized a Postgres/SQLite JSONField for `Conversation.metadata` to track the cart state efficiently without the overhead of building full relational cart models for a prototype.
- **Python safety layers (fallbacks):** Built the `TradeoffParser` with a strict `try/except` wrapper. If the Ollama endpoint times out or returns malformed JSON, the system silently degrades to a pure regex/keyword fallback `_keyword_fallback()`. This guarantees the user experience never crashes.
- **FAISS retrieval filtering:** Instead of passing all retrieved items to the LLM and asking it to filter them, I implemented Python-level list comprehensions post-retrieval to enforce `max_price` and `size` constraints before the data ever reaches the prompt context window.
- **Asynchronous Vanilla JS frontend:** Implemented a decoupled Vanilla JS Fetch architecture. The chat form submits asynchronously, and the cart UI updates via a secondary background fetch (`/api/cart/`). I wrote a custom, lightweight markdown parser to handle Llama 3's text formatting without relying on heavy external libraries like React or marked.js.

---

## Key Individual Decisions

- **Enforced JSON vs. Free-form Prompting:** I initially considered having the LLM return a formatted text string for filters. I pivoted to enforcing strict JSON output with `temperature=0.0`. This was harder to prompt, but it provided predictable keys (`max_price`, `tradeoff`) that my Python logic could safely consume.
- **Background Fetch vs. WebSockets:** For the dynamic cart updates, I considered using Django Channels and WebSockets. I chose to use a secondary background Fetch API call triggered immediately after the chat response returns. This achieved the desired async UX without introducing the massive infrastructure overhead of maintaining WebSocket connections.