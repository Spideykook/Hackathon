# Contribution Note — Kasparro AI Shopping Agent

**Track 1: AI Shopping Agent** · Solo Submission
**Participant:** Bedaanntica Paul

---

## Time Allocation

Total time invested: approximately 15–18 hours over one week.

| Area                                | Approximate Split | Estimated Time |
| ----------------------------------- | ----------------- | -------------- |
| Product Thinking & Feature Planning | 40%               | ~6–7 hrs       |
| Technical Implementation & Testing  | 60%               | ~9–11 hrs      |

I built the system incrementally, starting with the core “price vs. quality” shopping flow and then layering retrieval, checkout logic, fallback handling, and frontend improvements on top of it.

---

## Product Thinking & Scope Decisions

### Problem Framing

Most shopping assistants rely heavily on keyword matching and simple filtering, which breaks down when users express competing preferences like “cheap but high quality” or “stylish but comfortable.” I wanted the assistant to recognize these tradeoffs explicitly instead of treating them as unrelated keywords.

This led to the tradeoff parser becoming one of the core architectural decisions early in development.

---

### Defining the AI vs Deterministic Boundary

One of the biggest decisions was separating what the LLM should do from what deterministic Python logic should handle.

I used Llama 3 primarily for:

* extracting user intent,
* identifying filters,
* and understanding conversational context.

However, all critical operations such as:

* price filtering,
* cart state management,
* inventory checks,
* and checkout confirmation

were handled deterministically in Python.

This reduced the chances of incorrect filtering or inconsistent checkout behavior caused by hallucinated responses.

---

### Checkout Flow Design

I implemented a simple deterministic checkout state machine:

```text
BROWSING → COMPARING → CHECKOUT_CONFIRM
```

The confirmation layer was intentionally added so the assistant could not accidentally place or confirm items based on ambiguous user replies.

---

### Scope Control Decisions

I intentionally avoided integrating a live Shopify API during the prototype stage. Instead, I used synthetic/local product data to keep the focus on:

* retrieval quality,
* fallback reliability,
* and conversational shopping behavior.

This also helped reduce debugging complexity and removed dependency on external rate limits or unstable API responses.

---

## Technical Execution

### Backend Architecture

The backend was built using Django with a modular `ChatEngine` pipeline responsible for:

* retrieval,
* intent parsing,
* prompt building,
* and response orchestration.

Conversation state and cart data were stored using a lightweight JSONField approach instead of building a full relational cart schema, which kept iteration faster during prototyping.

---

### Tradeoff Parsing & Fallback Handling

I implemented a `TradeoffParser` layer that attempts structured JSON extraction first using Llama 3 with low-temperature prompting.

If:

* the Ollama endpoint fails,
* the model returns malformed JSON,
* or the response cannot be parsed,

the system falls back to a regex/keyword-based parser implemented entirely in Python.

This ensures the assistant can still respond gracefully even when the LLM output is unreliable.

---

### Retrieval & Filtering

FAISS was used for retrieval, but filtering was intentionally handled outside the LLM.

Instead of asking the model to enforce constraints like:

* maximum price,
* size,
* or color,

the retrieved products were filtered directly in Python before being added to the prompt context.

This kept filtering deterministic and reduced irrelevant context being sent to the model.

---

### Frontend Decisions

The frontend was implemented using Vanilla JavaScript with asynchronous Fetch requests instead of heavier frontend frameworks.

Key frontend decisions included:

* separating JavaScript into static files,
* asynchronous chat updates,
* lightweight markdown rendering,
* dynamic cart state updates,
* and frontend-side error handling.

I chose this approach to keep the prototype lightweight while still maintaining a responsive conversational interface.

---

## Key Technical Decisions

### Structured JSON Output

Initially, I considered using free-form LLM responses for filters and product constraints. I later switched to enforcing strict JSON-style extraction with deterministic keys like:

* `max_price`
* `tradeoff`
* `preferred_sizes`

This made downstream filtering logic significantly safer and easier to validate.

---

### Deterministic Validation Layers

A major focus during development was minimizing hallucinated product information.

To improve reliability:

* product filtering was handled in Python,
* checkout actions required deterministic confirmation,
* and retrieval context was validated before response generation.

This created a clearer separation between conversational reasoning and system-critical logic.

---

### Async Fetch Instead of WebSockets

For cart and chat updates, I considered using WebSockets through Django Channels but decided against it for the hackathon scope.

Using asynchronous Fetch requests provided:

* simpler infrastructure,
* easier debugging,
* and enough responsiveness for the prototype stage.

---

## Reflection

This project helped me better understand where LLMs are genuinely useful versus where deterministic systems are still necessary. One of the biggest takeaways was that building reliable AI applications often depends less on the model itself and more on the surrounding validation, retrieval, fallback, and state-management architecture.
