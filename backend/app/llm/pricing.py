"""Very small LLM pricing table for estimated-cost tracking (Phase 4).

Prices are USD per 1K tokens as (prompt, completion). The mock model carries a
nominal non-zero price so the cost-tracking feature is demonstrable offline.
Unknown models fall back to 0.
"""
from __future__ import annotations

from typing import Optional

# (prompt_per_1k, completion_per_1k)
PRICING = {
    "mock-model": (0.0005, 0.0015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.005, 0.015),
    "gpt-4.1-mini": (0.0004, 0.0016),
    "claude-3-5-sonnet-latest": (0.003, 0.015),
    "claude-3-5-haiku-latest": (0.0008, 0.004),
}


def estimate_cost(
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> float:
    prompt_rate, completion_rate = PRICING.get(model, (0.0, 0.0))
    cost = (prompt_tokens or 0) / 1000 * prompt_rate
    cost += (completion_tokens or 0) / 1000 * completion_rate
    return round(cost, 6)
