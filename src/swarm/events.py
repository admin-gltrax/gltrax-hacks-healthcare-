"""In-process event bus. The history doubles as the audit log; the dashboard
subscribes over SSE and can replay history on connect."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []
        self._subs: list[asyncio.Queue] = []

    def publish(self, type: str, **data: Any) -> dict:
        ev = {"seq": len(self.history), "ts": round(time.time(), 3), "type": type, **data}
        self.history.append(ev)
        for q in list(self._subs):
            q.put_nowait(ev)
        return ev

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subs:
            self._subs.remove(q)

    def dump(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            for ev in self.history:
                f.write(json.dumps(ev) + "\n")
