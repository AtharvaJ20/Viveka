# ADR-005: LLM Client Abstraction and Cost Enforcement

**Status:** Accepted
**Date:** 2026-09-23
**Author:** Mayasura
**References:** PRD REQ-034, §10.2, §5.3, ARCH-20260923-001 §7

---

## Context

The system makes LLM API calls for every scheduled job and every deep dive. Three
requirements constrain the design:

1. **REQ-034:** Monthly spend must be tracked, warned at ₹350, and hard-capped at ₹500.
   Breaching ₹500 is a defect.

2. **PRD §10.2:** Model routing is per-task. Scheduled jobs use Haiku 4.5; deep research
   uses Sonnet 4.6. Upgrading any single task's model must be a config change, not a
   code change.

3. **PRD §5.3 note:** "Raising this ceiling is the stated trigger for adopting vision
   and OCR extraction." The cost enforcement system must be auditable — Atharva needs
   to trust the numbers it reports.

The risk if there is no abstraction: LLM calls scattered across the codebase, each with
its own model string and no centralised cost accounting. The cost ceiling cannot be
enforced if the call site is not centralised.

---

## Decision

**All LLM calls go through `LLMClient`. Zero direct Anthropic SDK calls outside this class.**

See ARCH-20260923-001 §7 for the interface definition and model routing config.

**Cost calculation:**

```python
# INR cost from token counts
# Rates as of PRD §10.3 (verify against current pricing before first use)
RATES_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {
        "input_usd":  1.00,
        "output_usd": 5.00,
    },
    "claude-sonnet-4-6": {
        "input_usd":  3.00,
        "output_usd": 15.00,
    },
}
USD_TO_INR = 84.0  # fetched fresh daily from a free FX API; fallback to config value

def estimate_cost_inr(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = RATES_PER_MILLION[model]
    usd = (input_tokens * rates["input_usd"] + output_tokens * rates["output_usd"]) / 1_000_000
    return usd * USD_TO_INR
```

**Ceiling enforcement in `LLMClient.call()`:**

```
1. Query: SELECT SUM(cost_inr) FROM llm_usage WHERE created_at >= first_of_month()
2. If sum + estimated_cost_this_call > 500: raise CostCeilingExceeded
3. If sum > 350 and not warned_this_month: send warning notification
4. Make API call
5. INSERT INTO llm_usage (job_type, model, input_tokens, output_tokens, cost_inr)
6. Return LLMResponse
```

**One deliberate gap:** The ceiling check uses `estimated_cost_this_call` (based on
prompt length + max_tokens config) rather than actual output tokens, because actual
output tokens are unknown before the call. This means the ceiling is checked against
a conservative estimate. The actual spend logged after the call may be slightly lower.
This is the correct behaviour — err on the side of not breaching.

**For scheduled jobs (Haiku):** Cost ceiling check still runs but is unlikely to
trigger. The primary protection is against deep dive volume.

**Batch API routing (future optimization):**
PRD §10.3 tip notes that scheduled jobs are not latency-sensitive and could use the
Batch API at half the token cost. The `LLMClient` accepts a `batch: bool = False`
parameter. When `True`, it routes to the Batch API endpoint. This is a one-line
change at the call site and a few lines in `LLMClient.call()`. Not implemented in v1.0
but designed to be trivially addable.

---

## Consequences

**Easier:**
- Cost tracking is automatic — no call site needs to remember to log usage.
- Model upgrades are one config line in `MODELS` dict.
- The ₹500 ceiling cannot be breached by a single call (assuming honest token estimation).
- WEB-012 (cost dashboard) reads from `llm_usage` — data is already there from day one.
- REQ-034 warning and cap logic lives in one place.

**Harder:**
- Every developer (in this case, only Atharva) must remember: never call `anthropic.messages.create()`
  directly. This is enforced by code review convention, not a technical barrier.
  Mitigation: a `# DO NOT USE DIRECTLY — use LLMClient` comment on the anthropic import
  in `app/llm/client.py` is sufficient for a single-developer project.

**USD/INR rate:** Fetched daily from a free FX API (e.g., `open.er-api.com`). Fallback
to `USD_TO_INR = 84.0` in config if the fetch fails. A ±5% exchange rate drift against
the config value shifts the effective ceiling by ±₹25 — acceptable for this use case.

**Technical debt:**
None introduced. The abstraction is proportional to the requirement — REQ-034 is P1
and must ship before Phase 4.
