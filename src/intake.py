"""Patient intake: free-text (or transcribed speech) -> structured Constraints.

Uses structured output on the planner model (Muse Wonder). Voice input comes from
Muse Voice Transcribe upstream; this module only sees text."""
from __future__ import annotations

import json

from .llm import LLM, get_llm
from .schemas import Constraints

CONSTRAINTS_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "constraints",
        "schema": {
            "type": "object",
            "properties": {
                "specialty": {"type": "string"},
                "earliest_time": {"type": "string", "description": "HH:MM 24h, earliest acceptable time of day"},
                "earliest_date": {"type": "string", "description": "YYYY-MM-DD"},
                "latest_date": {"type": "string", "description": "YYYY-MM-DD"},
                "max_distance_miles": {"type": "integer"},
            },
            "required": ["specialty", "earliest_time", "earliest_date", "latest_date", "max_distance_miles"],
            "additionalProperties": False,
        },
    },
}

PROMPT = """Extract appointment-scheduling constraints from what the patient said.
Today is {today}. Use a 14-day window starting tomorrow unless the patient says otherwise.
"As soon as possible" means start tomorrow. "Nothing before 9" means earliest_time 09:00. Default earliest_time 08:00 and distance 25 miles."""


async def parse_request(utterance: str, today: str = "2026-11-01", llm: LLM | None = None) -> Constraints:
    llm = llm or get_llm("planner")
    res = await llm.chat(
        [{"role": "system", "content": PROMPT.format(today=today)}, {"role": "user", "content": utterance}],
        response_format=CONSTRAINTS_SCHEMA,
    )
    return Constraints.model_validate(json.loads(res.content))
