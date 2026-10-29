"""The patient layer's door to the Meta Model API.

Every model request PJ's crew makes goes through here, so that:
  - it is metered: a daily cap for the whole server and one per account, because
    the demo is public and every request spends real credits;
  - it degrades gracefully: when the API is off, over budget, or errors, callers
    fall back to the deterministic rules and say so on screen ("engine": "rules");
  - structured output is validated: tool and JSON output from a model is a claim,
    never trusted until it parses and passes the caller's checks.

Models by role (src/config.py): the caller and receptionists on Muse Spark, the
reader on Spark vision, the strategist on Muse Wonder, the writer and PJ's chat
on Spark. MOCK_LLM=1 swaps in the scripted offline models (src/mock.py), so the
tests exercise these exact code paths.

Fictional data only (CLAUDE.md invariant 7): no real PHI goes to any model, and
nothing ever goes to a `-contributor` model.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import META_BASE_URL_DEFAULT, PATIENT_FACING, mock_enabled, provider_for, role_cfg
from ..eval.spend import USAGE, price
from ..llm import ChatResult, MetaLLM


class AIUnavailable(Exception):
    """The model can't be used right now; the caller should use its rules path."""


def enabled() -> bool:
    if os.getenv("PJ_AI", "on").lower() in ("off", "0", "false", "rules"):
        return False
    return mock_enabled() or bool(os.getenv("MODEL_API_KEY"))


def model_for(role: str) -> str:
    cfg = role_cfg(role)
    model = cfg.model
    if "contributor" in model:  # Meta trains on these; never send them patient data, even fictional
        raise AIUnavailable(f"{model} is a -contributor model; the patient layer never uses those.")
    meta = os.getenv("META_BASE_URL", META_BASE_URL_DEFAULT).rstrip("/")
    if role in PATIENT_FACING and cfg.base_url.rstrip("/") != meta:  # THE RULE: partner credits never face the patient
        raise AIUnavailable(f"The {role} faces the patient, so it stays on Meta's Model API.")
    return model


def role_ready(role: str) -> bool:
    """This role can be called: the API is on and the role's own provider key is set."""
    if not enabled():
        return False
    return mock_enabled() or bool(os.getenv(role_cfg(role).api_key_env))


def engine_label(role: str) -> str:
    return "mock " + model_for(role) if mock_enabled() else model_for(role)


# ---------------------------------------------------------------- budget

class Budget:
    """Requests per UTC day, for the server and for each account."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = ""
        self._total = 0
        self._by_account: dict[str, int] = {}

    @staticmethod
    def limits() -> tuple[int, int]:
        def num(name: str, default: int) -> int:
            try:
                return max(0, int(os.getenv(name, str(default))))
            except ValueError:
                return default
        return num("PJ_AI_DAILY_REQUESTS", 4000), num("PJ_AI_ACCOUNT_REQUESTS", 250)

    def spend(self, account: str | None, n: int = 1) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        total_cap, account_cap = self.limits()
        with self._lock:
            if day != self._day:
                self._day, self._total, self._by_account = day, 0, {}
            used = self._by_account.get(account or "-", 0)
            if self._total + n > total_cap:
                raise AIUnavailable("PJ's daily model budget for this demo server is used up.")
            if used + n > account_cap:
                raise AIUnavailable("This account has used its model budget for today.")
            self._total += n
            self._by_account[account or "-"] = used + n

    def status(self, account: str | None = None) -> dict:
        total_cap, account_cap = self.limits()
        with self._lock:
            return {"used_today": self._total, "daily_cap": total_cap,
                    "account_used": self._by_account.get(account or "-", 0), "account_cap": account_cap}


BUDGET = Budget()


class Metered:
    """An LLM for one role that spends budget before every request."""

    def __init__(self, role: str, account: str | None):
        if not enabled():
            raise AIUnavailable("The model API is off on this server.")
        self.role, self.account = role, account
        self.model = model_for(role)
        if mock_enabled():
            from ..mock import MockLLM
            self._llm = MockLLM(role)
        else:  # a fresh client per job: each job runs on its own event loop (see run())
            self._llm = MetaLLM(role_cfg(role))
        self.requests = self.prompt_tokens = self.completion_tokens = 0

    async def chat(self, messages, tools=None, response_format=None, max_tokens=None) -> ChatResult:
        BUDGET.spend(self.account)
        self.requests += 1
        try:
            res = await self._llm.chat(messages, tools=tools, response_format=response_format, max_tokens=max_tokens)
        except AIUnavailable:
            raise
        except Exception as e:  # network, 4xx/5xx, timeouts: the rules path takes over
            raise AIUnavailable(f"{type(e).__name__}: {str(e)[:200]}") from e
        self.prompt_tokens += res.usage.get("prompt_tokens", 0)
        self.completion_tokens += res.usage.get("completion_tokens", 0)
        if not mock_enabled():
            USAGE.add(self.model, res.usage)
        return res

    def cost(self) -> float:
        p_in, p_out = price(self.model)
        return round(self.prompt_tokens / 1e6 * p_in + self.completion_tokens / 1e6 * p_out, 6)


def llm(role: str, account: str | None = None) -> Metered:
    return Metered(role, account)


def schema(name: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "schema": {
        "type": "object", "properties": properties, "required": required or list(properties)}}}


async def chat_json(role: str, messages: list[dict], response_format: dict, account: str | None = None,
                    max_tokens: int = 4000) -> dict:
    """One structured request. Raises AIUnavailable if the model is off or its JSON doesn't parse."""
    m = llm(role, account)
    if provider_for(role) != "meta" and response_format.get("type") == "json_schema":
        # open-weights hosts take JSON mode, not strict schemas: put the schema in the prompt, validate after
        spec = json.dumps(response_format["json_schema"]["schema"])
        messages = messages[:-1] + [{**messages[-1], "content": _append(messages[-1]["content"],
                                     "\n\nReply with one JSON object matching this JSON Schema, and nothing else:\n" + spec)}]
        response_format = {"type": "json_object"}
    res = await m.chat(messages, response_format=response_format, max_tokens=max_tokens)
    text = (res.content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        out = json.loads(text)
    except json.JSONDecodeError as e:
        raise AIUnavailable(f"{m.model} returned JSON that didn't parse: {e}") from e
    if not isinstance(out, dict):
        raise AIUnavailable(f"{m.model} returned {type(out).__name__}, not an object")
    return out


def _append(content: Any, text: str) -> Any:
    if isinstance(content, str):
        return content + text
    return list(content) + [{"type": "text", "text": text}]


# ---------------------------------------------------------------- sync bridge

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pj-ai")


def run(coro: Any) -> Any:
    """Run a coroutine from sync code (FastAPI sync routes run in a threadpool with
    no event loop; if one is running, hop to a worker thread)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return _POOL.submit(asyncio.run, coro).result()
