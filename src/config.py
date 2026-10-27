"""Per-role model configuration. Everything is read from the environment at call
time so tests can monkeypatch it."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

META_BASE_URL_DEFAULT = "https://api.meta.ai/v1"

# role -> (default model, default reasoning effort)
ROLE_DEFAULTS: dict[str, tuple[str, str | None]] = {
    "planner": ("muse-wonder-1.0", "medium"),  # long-horizon agentic work
    "worker": ("muse-spark-1.3", "low"),  # the caller: fast, tool-calling
    "office": ("muse-spark-1.3", "minimal"),  # simulated receptionists
    "judge": ("muse-spark-1.3", "medium"),
    "critic": ("muse-wonder-1.0", "high"),  # proposes prompt patches
}


@dataclass(frozen=True)
class RoleCfg:
    role: str
    model: str
    base_url: str
    api_key_env: str
    reasoning_effort: str | None


def role_cfg(role: str) -> RoleCfg:
    model, effort = ROLE_DEFAULTS[role]
    p = role.upper()
    raw_effort = os.getenv(f"{p}_REASONING", effort or "")
    if raw_effort.strip().lower() in ("", "off", "none", "default"):
        raw_effort = None  # Meta rejects "none"; omit the field instead
    return RoleCfg(
        role=role,
        model=os.getenv(f"{p}_MODEL", model),
        base_url=os.getenv(f"{p}_BASE_URL", os.getenv("META_BASE_URL", META_BASE_URL_DEFAULT)),
        api_key_env=os.getenv(f"{p}_API_KEY_ENV", "MODEL_API_KEY"),
        reasoning_effort=raw_effort,
    )


def mock_enabled() -> bool:
    return os.getenv("MOCK_LLM", "0") == "1"


def hold_scale() -> float:
    try:
        return float(os.getenv("HOLD_SCALE", "0.02"))
    except ValueError:
        return 0.02
