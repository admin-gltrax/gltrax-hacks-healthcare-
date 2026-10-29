"""Run PJ's red-team set live on Muse Spark and print the pass rate.

    python scripts/redteam_pj.py        # needs MODEL_API_KEY; about 30 requests
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.agents import guide  # noqa: E402
from src.eval.pj_redteam import CASES, check  # noqa: E402
from src.patient.demo import build_demo  # noqa: E402
from src.patient.models import HealthRecord, Patient  # noqa: E402


async def main() -> int:
    acct = await build_demo(HealthRecord(patient=Patient(display_name="Alex Rivera")))
    rosa = acct.circle[0].record
    passed = 0
    for case in CASES:
        ans = await guide.ask_live(rosa, case["text"], account="redteam", viewer="Alex Rivera")
        fails = check(case, ans)
        passed += not fails
        print(("PASS" if not fails else "FAIL"), f"[{ans.get('engine')}]", case["text"][:70])
        if fails or "-v" in sys.argv:
            print("     ", fails, "|", ans.get("say", "")[:300].replace("\n", " "), "|", (ans.get("proposal") or {}).get("template"))
    print(f"red team: {passed}/{len(CASES)} ({100 * passed / len(CASES):.0f}%)")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
