# DECISIONS.md — Architectural Decision Log

A running record of key technical and product decisions made during the build.
Format: **We considered X, chose Y, because Z.**

---

**Decision 1: Cart state storage**

We considered creating a dedicated `CartItem` database model with a foreign key to `Conversation`.

We chose storing cart state in `Conversation.metadata` (an existing JSONField).

Because the cart is ephemeral per-session. A separate `CartItem` table would require a Django migration, a cleanup job for abandoned carts, and additional ORM queries on every message. The JSONField collapses with the conversation naturally — when the session is over, the cart is over. The structure (`{state, items, order_id}`) is simple enough that a relational model adds overhead without adding value at this stage. If cart persistence across sessions becomes a requirement, the migration path is clear: extract `metadata["cart"]` into a proper model.

---

**Decision 2: Checkout state transitions driven by keyword triggers, not the LLM**

We considered asking the LLM to detect checkout intent and manage cart additions within the main generation call.

We chose a deterministic Python state machine with a fixed set of trigger phrases.

Because the LLM has no persistent state between API calls. To have it "manage" the cart, we would need to include the full cart contents in every prompt, which increases token cost per message and introduces the risk of the model mis-stating cart contents or hallucinating items. A Python dict with keyword triggers is O(1), free, and produces a testable, auditable state transition every time. The checkout path — where a user is about to commit money — is exactly the wrong place to rely on stochastic output.

---

**Decision 3: Post-generation hallucination check instead of prompt-only mitigation**

We considered relying solely on the system prompt instruction ("only mention products from the context I provide") to prevent the LLM from inventing products.

We chose adding a post-generation validator (`HallucinationGuard`) that cross-checks prices and product name patterns against the retrieval result after the LLM generates its answer.

Because prompt instructions are best-effort with a 7B model. In testing, Llama 3 7B occasionally referenced products from its training data when the retrieval result was sparse or when the query was phrased in a way that triggered a memorised response. A post-generation check is a hard boundary: if the answer contains a price that doesn't match any retrieved product within a $0.50 tolerance, the entire response is replaced with a Python-generated list built directly from the retrieval result. The user never sees fabricated data, regardless of what the LLM outputs.

---

**Decision 4: Separate lightweight LLM call for intent parsing (TradeoffParser)**

We considered embedding the intent parsing instruction into the main system prompt and asking the LLM to output a JSON block at the top of its answer.

We chose a dedicated low-token LLM call (temp=0) in `TradeoffParser.parse()` that returns only a JSON object, with a full regex-based fallback if the call fails.

Because mixing structured JSON extraction with free-text generation in a single call is unreliable. The model has to switch modes mid-output, and the JSON often gets polluted with prose or markdown. A separate call at temp=0 with a narrow prompt ("return ONLY a valid JSON object") is far more stable. The cost is one extra round trip per message, which is acceptable given that the intent call is low-token. Crucially, the regex fallback means the entire feature degrades gracefully to near-zero latency if Ollama is slow or down — the main generation call is never blocked by a failed intent parse.

---

**Decision 5: First-result candidate selection for cart adds**

We considered building a disambiguation flow — when a user says "add this one" after seeing five products, ask "which of these did you mean?" with numbered options.

We chose picking the first retrieved product as the `pending_item` candidate when the user signals an add-to-cart intent.

Because the confirmation step (`"Add X for $Y? yes/no"`) already gives the user an explicit veto before anything is committed. If the wrong product is selected, the user says "no" and the pending item is cleared — they're back to BROWSING with zero items added. The cost of getting the candidate wrong is a single confirmation round-trip, not a committed purchase. A full disambiguation UI is the right long-term answer, but for a single-session demo where retrieval results are ranked by relevance, first-result selection is correct often enough that the confirmation gate handles the edge cases.
---

**Decision 6: Vanilla JS Fetch API over React, a UI framework, or Django form submission**

We considered three alternatives for the frontend:

- **Standard Django form submission** (`<form method="POST">`): simple, zero JS required, but causes a full page reload on every message. A page reload resets scroll position, flashes the UI, and destroys the "conversation" mental model entirely. Unacceptable for a chat interface.

- **React (or Vue/Svelte)**: component model would be clean, but introduces a build pipeline (Vite/webpack), `node_modules`, and a separate compilation step. For a hackathon with a single chat view, the overhead is disproportionate. Judges reviewing the repo would also see a `package.json` with 800 transitive dependencies, which works against the "pragmatic engineering" signal we want to send.

- **Vanilla JS Fetch API with a static file**: no build step, no dependencies, reviewable in a `git diff`, loads in one HTTP request. The browser's native `fetch()` handles async cleanly with `async/await`. The only patterns we needed — appending DOM nodes, firing background requests, reading JSON — are all first-class in modern JS without a framework.

We chose Vanilla JS because the complexity ceiling of this UI (one message list, one input, one cart counter) never justifies a framework. The constraint also forced cleaner separation: the `renderMarkdown()` function is 30 lines and unit-testable in isolation; a React component doing the same thing would be entangled with hooks and state. The background cart fetch being explicitly "not awaited" is visible and obvious in plain JS in a way that's harder to express cleanly in a React effect.

We considered integrating the live Shopify Admin API, as stated in the document, but chose to use local synthetic data to guarantee uptime, lower latency, and focus strictly on the AI/deterministic boundary.