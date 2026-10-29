"""Per-role model configuration. Everything is read from the environment at call
time so tests can monkeypatch it."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

META_BASE_URL_DEFAULT = "https://api.meta.ai/v1"

# Partner credits run Muse Spark Open (open weights) for simulators, adversaries
# and judges. THE RULE: the patient-facing crew stays on Meta's Model API.
PROVIDERS: dict[str, tuple[str, str, str]] = {  # name -> (base URL, key env var, Muse Spark Open model id)
    "meta": (META_BASE_URL_DEFAULT, "MODEL_API_KEY", "muse-spark-1.3"),
    "baseten": ("https://inference.baseten.co/v1", "BASETEN_API_KEY", "meta-models/muse-spark-open-1026"),  # the hackathon key is scoped to this dated build
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "accounts/fireworks/models/muse-spark-open"),
}
# Modal: a dedicated endpoint (`modal endpoint create --model ...`), OpenAI-compatible, reached at
# MODAL_ENDPOINT_URL with a workspace proxy token "<id>.<secret>" in MODAL_PROXY_TOKEN.
MODAL_MODEL = "Qwen/Qwen3.6-35B-A3B"
PATIENT_FACING = ("worker", "caller", "reader", "strategist", "writer", "pj")

# role -> (default model, default reasoning effort)
ROLE_DEFAULTS: dict[str, tuple[str, str | None]] = {
    "planner": ("muse-wonder-1.0", "medium"),  # long-horizon agentic work
    "worker": ("muse-spark-1.3", "low"),  # the caller: fast, tool-calling
    "office": ("muse-spark-1.3", "minimal"),  # simulated receptionists
    "judge": ("muse-spark-1.3", "medium"),
    "critic": ("muse-wonder-1.0", "high"),  # proposes prompt patches
    # patient layer (src/agents/ai.py meters every request)
    "caller": ("muse-spark-1.3", "low"),  # phones the doctor's office for the patient
    "reader": ("muse-spark-1.3", "low"),  # vision: denial letters, bills, EOBs
    "strategist": ("muse-wonder-1.0", "medium"),  # maps evidence to a plan's criteria
    "writer": ("muse-spark-1.3", "low"),  # drafts appeal and dispute letters
    "pj": ("muse-spark-1.3", "low"),  # PJ's chat voice
    # partner credits (Muse Spark Open): adversaries and judges, never patient-facing
    "reviewer": (PROVIDERS["baseten"][2], "low"),  # plays the insurer's medical reviewer
    "judge_open": (PROVIDERS["fireworks"][2], "medium"),  # the cross-family judge (same effort as "judge")
    "verifier": (MODAL_MODEL, None),  # checks every claim in a letter against the facts (a guard, not patient-facing)
}
# Roles whose default provider isn't Meta. Override per role with <ROLE>_PROVIDER
# (meta | baseten | fireworks), or fully with <ROLE>_BASE_URL / _API_KEY_ENV / _MODEL.
ROLE_PROVIDER: dict[str, str] = {"reviewer": "baseten", "judge_open": "fireworks", "verifier": "modal"}


@dataclass(frozen=True)
class RoleCfg:
    role: str
    model: str
    base_url: str
    api_key_env: str
    reasoning_effort: str | None


def provider_for(role: str) -> str:
    return os.getenv(f"{role.upper()}_PROVIDER", ROLE_PROVIDER.get(role, "meta")).strip().lower()


def role_cfg(role: str) -> RoleCfg:
    model, effort = ROLE_DEFAULTS[role]
    p = role.upper()
    prov = provider_for(role)
    if prov == "modal":
        return RoleCfg(role=role, model=os.getenv(f"{p}_MODEL", MODAL_MODEL),
                       base_url=os.getenv(f"{p}_BASE_URL", os.getenv("MODAL_ENDPOINT_URL", "").rstrip("/") + "/v1"),
                       api_key_env=os.getenv(f"{p}_API_KEY_ENV", "MODAL_PROXY_TOKEN"),
                       reasoning_effort=_effort(os.getenv(f"{p}_REASONING", effort or "")))
    if prov != "meta" and prov in PROVIDERS:
        base, key_env, open_model = PROVIDERS[prov]
        return RoleCfg(role=role, model=os.getenv(f"{p}_MODEL", open_model), base_url=os.getenv(f"{p}_BASE_URL", base),
                       api_key_env=os.getenv(f"{p}_API_KEY_ENV", key_env),
                       reasoning_effort=_effort(os.getenv(f"{p}_REASONING", effort or "")))
    raw_effort = _effort(os.getenv(f"{p}_REASONING", effort or ""))
    return RoleCfg(
        role=role,
        model=os.getenv(f"{p}_MODEL", model if "/" not in model else PROVIDERS["meta"][2]),
        base_url=os.getenv(f"{p}_BASE_URL", os.getenv("META_BASE_URL", META_BASE_URL_DEFAULT)),
        api_key_env=os.getenv(f"{p}_API_KEY_ENV", "MODEL_API_KEY"),
        reasoning_effort=raw_effort,
    )


def _effort(raw: str) -> str | None:
    return None if raw.strip().lower() in ("", "off", "none", "default") else raw  # Meta rejects "none"; omit it


def mock_enabled() -> bool:
    return os.getenv("MOCK_LLM", "0") == "1"


def hold_scale() -> float:
    try:
        return float(os.getenv("HOLD_SCALE", "0.02"))
    except ValueError:
        return 0.02
