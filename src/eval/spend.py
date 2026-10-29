"""What model calls cost: token usage by model, priced per 1M tokens.

Prices (USD per 1M tokens, input / output; output includes reasoning tokens):
  muse-spark-1.3 (Meta)            1.25 / 4.25   Meta docs, Oct 27
  muse-wonder-1.0 (Meta)           4.00 / 20.00  Meta docs, Oct 27
  Muse Spark Open on Baseten       1.25 / 4.25   Baseten /v1/models pricing, Oct 29
  Muse Spark Open on Fireworks     1.25 / 4.25   aggregator listings, Oct 29 (Fireworks' own page wasn't reachable)
Override any model with SPEND_PRICE_<NAME>="in,out" if a bill disagrees.
"""
from __future__ import annotations

import os
import re
import threading
from collections import defaultdict

PRICES = {"muse-spark-1.3": (1.25, 4.25), "muse-spark-1.2": (1.25, 4.25), "muse-wonder-1.0": (4.0, 20.0),
          "meta-models/muse-spark-open": (1.25, 4.25), "meta-models/muse-spark-open-1026": (1.25, 4.25), "accounts/fireworks/models/muse-spark-open": (1.25, 4.25)}


def price(model: str) -> tuple[float, float]:
    env = os.getenv("SPEND_PRICE_" + re.sub(r"[^A-Z0-9]", "_", model.upper()))
    if env:
        a, b = env.split(",")
        return float(a), float(b)
    if model in PRICES:
        return PRICES[model]
    return (1.25, 4.25) if "spark" in model else (4.0, 20.0)  # unknown: assume the dearer side


def provider(model: str) -> str:
    return "baseten" if model.startswith("meta-models/") else "fireworks" if model.startswith("accounts/fireworks/") else "meta"


class Tally:
    """Thread-safe usage totals by model."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_model: dict[str, dict] = defaultdict(lambda: {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0})

    def add(self, model: str, usage: dict) -> None:
        with self._lock:
            m = self.by_model[model]
            m["requests"] += 1
            m["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            m["completion_tokens"] += int(usage.get("completion_tokens") or 0)

    def cost(self, model: str | None = None) -> float:
        with self._lock:
            items = [(k, v) for k, v in self.by_model.items() if model is None or k == model]
        return round(sum(v["prompt_tokens"] / 1e6 * price(k)[0] + v["completion_tokens"] / 1e6 * price(k)[1] for k, v in items), 6)

    def by_provider(self) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for k in list(self.by_model):
            out[provider(k)] += self.cost(k)
        return {k: round(v, 4) for k, v in out.items()}

    def snapshot(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self.by_model.items()}


USAGE = Tally()  # everything this process spent
