import os

os.environ["MOCK_LLM"] = "1"
os.environ["HOLD_SCALE"] = "0"

from src.llm import ChatResult, ToolCall  # noqa: E402


class ScriptedLLM:
    """Plays back a fixed list of ChatResults (for adversarial worker tests)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def chat(self, messages, tools=None, response_format=None, max_tokens=None):
        self.calls += 1
        if self.script:
            return self.script.pop(0)
        return ChatResult(tool_calls=[ToolCall("end", "end_call", {"summary": "script exhausted"})])
