"""Speech-to-text accuracy where phone calls fail: names, dates of birth and
reference numbers. Word error rate after light normalization, plus an exact
entity check (did the caller hear the right name, date, reference?)."""
from __future__ import annotations

import random
import re
from datetime import date, timedelta

from ..sim.gym import _FIRST, _LAST

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def norm(text: str) -> list[str]:
    t = text.lower().replace("-", " ")
    t = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return t.split()


def wer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def heard_name(name: str, hyp: str) -> bool:
    want, got = norm(name), norm(hyp)
    return any(got[i:i + len(want)] == want for i in range(len(got)))


def heard_dob(dob: str, hyp: str) -> bool:
    d = date.fromisoformat(dob)
    t = " ".join(norm(hyp))
    m = re.search(r"(" + "|".join(MONTHS) + r") (\d{1,2}) (\d{4})", t)
    if m:
        return (MONTHS.index(m.group(1)) + 1, int(m.group(2)), int(m.group(3))) == (d.month, d.day, d.year)
    m = re.search(r"\b(\d{1,2}) (\d{1,2}) (\d{4})\b", t)  # 08/05/1941 read as numbers
    return bool(m) and (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (d.month, d.day, d.year)


def heard_ref(ref: str, hyp: str) -> bool:
    digits = re.sub(r"\D", "", ref)
    m = re.search(r"\b(?:r|are|our|or)\b[\s.\-]*((?:\d[\s.\-]*){5})", hyp.lower())
    got = re.sub(r"\D", "", m.group(1)) if m else re.sub(r"\D", "", hyp)[-5:]
    return got == digits


def utterances(n: int, seed: int = 5) -> list[dict]:
    """n office lines, a third each: a name read back, a date of birth, a reference number (some spelled out)."""
    out = []
    for i in range(n):
        rng = random.Random(f"{seed}:{i}")
        kind = ["name", "dob", "reference"][i % 3]
        name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        dob = (date(1938, 1, 1) + timedelta(days=rng.randrange(365 * 80))).isoformat()
        ref = f"R-{rng.randint(10000, 99999)}"
        d = date.fromisoformat(dob)
        spoken_dob = f"{MONTHS[d.month - 1].capitalize()} {d.day}, {d.year}"
        text = {"name": f"Okay, I have {name} here. Is that right?",
                "dob": f"And the date of birth is {spoken_dob}?",
                "reference": (f"Your reference number is {'-'.join(ref)}." if i % 2 else f"Your reference number is {ref}.")
                .replace("R---", "R-")}[kind]
        out.append({"id": f"asr-{seed}-{i:03d}", "kind": kind, "text": text, "name": name, "dob": dob, "reference": ref,
                    "speed": [1.0, 1.0, 1.3][rng.randrange(3)], "voice": i % 4})
    return out


def check(u: dict, hyp: str) -> bool:
    return {"name": heard_name(u["name"], hyp), "dob": heard_dob(u["dob"], hyp), "reference": heard_ref(u["reference"], hyp)}[u["kind"]]
