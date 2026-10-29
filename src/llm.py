"""Thin async wrapper over the Meta Model API (OpenAI-compatible Chat Completions).

Notes taken from the Meta docs:
- base_url https://api.meta.ai/v1, key in MODEL_API_KEY (passed explicitly).
- tool_choice only supports "auto", so we never send it.
- On Chat Completions the *full* assistant message (with tool_calls) must be
  echoed back before the matching tool messages.
- Tool arguments are not guaranteed to match the schema: callers must validate.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import RoleCfg, mock_enabled, role_cfg


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    parse_error: str | None = None


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens (reasoning included), when the API says

    def assistant_message(self) -> dict:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        return msg


class LLM(Protocol):
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult: ...


_SEMAPHORES: dict[str, asyncio.Semaphore] = {}


def _sem_for(base_url: str, limit: int) -> asyncio.Semaphore:
    # One semaphore per (event loop, host) is enough for a single-process swarm.
    key = f"{id(asyncio.get_running_loop())}:{base_url}"
    if key not in _SEMAPHORES:
        _SEMAPHORES[key] = asyncio.Semaphore(limit)
    return _SEMAPHORES[key]


class MetaLLM:
    def __init__(self, cfg: RoleCfg, max_in_flight: int = 48):
        from openai import AsyncOpenAI

        key = os.environ.get(cfg.api_key_env)
        if not key:
            raise RuntimeError(
                f"{cfg.api_key_env} is not set. Add the {cfg.role} role's API key to .env "
                "or run with MOCK_LLM=1."
            )
        self.cfg = cfg
        self.max_in_flight = max_in_flight
        self.client = AsyncOpenAI(base_url=cfg.base_url, api_key=key, max_retries=5, timeout=120.0)

    async def chat(self, messages, tools=None, response_format=None, max_tokens=None) -> ChatResult:
        kwargs: dict[str, Any] = {"model": self.cfg.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools  # tool_choice intentionally omitted ("auto" only)
        if response_format:
            kwargs["response_format"] = response_format
        extra: dict[str, Any] = {}
        if self.cfg.reasoning_effort:
            extra["reasoning_effort"] = self.cfg.reasoning_effort
        if max_tokens:
            extra["max_completion_tokens"] = max_tokens
        if extra:
            kwargs["extra_body"] = extra

        async with _sem_for(self.cfg.base_url, self.max_in_flight):
            resp = await self.client.chat.completions.create(**kwargs)
        return parse_completion(resp)


def parse_completion(resp: Any) -> ChatResult:
    msg = resp.choices[0].message
    calls: list[ToolCall] = []
    for tc in getattr(msg, "tool_calls", None) or []:
        err = None
        try:
            args = json.loads(tc.function.arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            args, err = {}, str(e)
        calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args, parse_error=err))
    u = getattr(resp, "usage", None)
    usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0) or 0, "completion_tokens": getattr(u, "completion_tokens", 0) or 0} if u else {}
    return ChatResult(content=msg.content or "", tool_calls=calls, usage=usage)


_CACHE: dict[str, LLM] = {}


def get_llm(role: str) -> LLM:
    """Factory used everywhere. MOCK_LLM=1 returns a scripted offline model."""
    if mock_enabled():
        from .mock import MockLLM

        return MockLLM(role)
    cfg = role_cfg(role)
    key = f"{cfg.role}:{cfg.model}:{cfg.base_url}:{cfg.reasoning_effort}"
    if key not in _CACHE:
        _CACHE[key] = MetaLLM(cfg)
    return _CACHE[key]
