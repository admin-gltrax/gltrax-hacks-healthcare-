"""First thing to run once you have a Meta Model API key:

    python scripts/smoke_meta.py

Checks, in order: auth + model list, plain chat, tool-call round trip (Chat
Completions format), structured output, and the exact model IDs this repo uses.
Each check prints PASS/FAIL so you know precisely which assumption broke.
Nothing here has been run against the live API yet; this is how you find out.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import ROLE_DEFAULTS, role_cfg  # noqa: E402
from src.llm import MetaLLM  # noqa: E402

TOOL = [{
    "type": "function",
    "function": {
        "name": "record_outcome",
        "description": "Record a fact.",
        "parameters": {
            "type": "object",
            "properties": {"field": {"type": "string", "enum": ["accepts_plan"]}, "value": {"type": "string", "enum": ["yes", "no", "unsure"]}},
            "required": ["field", "value"],
        },
    },
}]
SCHEMA = {"type": "json_schema", "json_schema": {"name": "t", "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}}}


def report(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


async def main() -> None:
    if not os.getenv("MODEL_API_KEY"):
        sys.exit("MODEL_API_KEY is not set (see .env.example).")

    cfg = role_cfg("worker")
    llm = MetaLLM(cfg)

    try:
        models = [m.id async for m in llm.client.models.list()]
        report("auth + models.list", True, f"{len(models)} models")
        for role in ROLE_DEFAULTS:
            mid = role_cfg(role).model
            if role_cfg(role).base_url == cfg.base_url:
                report(f"model id for {role}: {mid}", mid in models, "" if mid in models else f"not listed; available: {models}")
    except Exception as e:
        report("auth + models.list", False, f"{type(e).__name__}: {e}")

    try:
        r = await llm.chat([{"role": "user", "content": "Reply with the single word: pong"}], max_tokens=64)
        report("plain chat", "pong" in r.content.lower(), repr(r.content[:60]))
    except Exception as e:
        report("plain chat", False, f"{type(e).__name__}: {e}")

    try:
        msgs = [{"role": "user", "content": "The office said yes, they accept the plan. Record that."}]
        r = await llm.chat(msgs, tools=TOOL)
        ok = bool(r.tool_calls) and r.tool_calls[0].arguments.get("value") == "yes"
        report("tool call emitted", ok, json.dumps([t.arguments for t in r.tool_calls]))
        if r.tool_calls:
            msgs.append(r.assistant_message())
            msgs.append({"role": "tool", "tool_call_id": r.tool_calls[0].id, "content": json.dumps({"ok": True})})
            r2 = await llm.chat(msgs, tools=TOOL)
            report("tool result round trip", True, repr(r2.content[:60]))
    except Exception as e:
        report("tool call / round trip", False, f"{type(e).__name__}: {e}")

    try:
        r = await llm.chat([{"role": "user", "content": 'Return {"ok": true}'}], response_format=SCHEMA)
        report("structured output", json.loads(r.content).get("ok") is True, r.content[:60])
    except Exception as e:
        report("structured output", False, f"{type(e).__name__}: {e}")

    # Planner model (Muse Wonder is preview; failure here is non-fatal for the build)
    try:
        r = await MetaLLM(role_cfg("planner")).chat([{"role": "user", "content": "Reply with the single word: pong"}], max_tokens=64)
        report(f"planner model ({role_cfg('planner').model})", "pong" in r.content.lower(), repr(r.content[:60]))
    except Exception as e:
        report(f"planner model ({role_cfg('planner').model})", False, f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
