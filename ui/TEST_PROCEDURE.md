# UI Manual Test Procedure: LLM Gateway & Profiler Demo

## 1. Basic Chat Flow

- Enter: `How do I bake a cake?` in the "User Sent" text area.
- Press **Send**.
- Expect:
  - "Gateway Received (PII Redacted)" shows the same message (no PII, so no redaction).
  - "Execution Trace" panel updates with step-by-step trace (e.g., PII check, cache miss/hit, provider call).
  - "Metrics Dashboard" updates with nonzero values.

## 2. PII Redaction

- Enter: `My email is test@example.com` in the "User Sent" text area.
- Press **Send**.
- Expect:
  - "Gateway Received (PII Redacted)" shows: `My email is <EMAIL>`
  - "PII Blocked" badge/info appears.
  - Trace panel shows PII redaction step.

## 3. Chaos Mode (Failover)

- In sidebar, set **Simulate Failure** to `OpenAI`.
- Enter: `Tell me a joke.`
- Press **Send**.
- Expect:
  - Trace panel shows simulated OpenAI failure and fallback to Anthropic.
  - No error shown to user; response is still returned.

## 4. Rate Limiting

- (Optional: Lower rate limit in backend for test)
- Rapidly press **Send** 10+ times.
- Expect:
  - Warning: `429: Too many requests. Slow down.`
  - No new responses until rate limit resets.

## 5. Cache Invalidation

- Press **Invalidate Cache** in sidebar Admin Panel.
- Enter: `How do I bake a cake?` and press **Send**.
- Expect:
  - Trace panel shows cache miss and new LLM call (not a cache hit).

## 6. Theme Switcher

- In sidebar, toggle **Theme** between Light, Dark, and System.
- Expect:
  - UI colors update accordingly.

---

Repeat tests for different routing policies (Penny Pincher, Speed Demon, High Fidelity) to verify policy selection is reflected in trace and metrics.
