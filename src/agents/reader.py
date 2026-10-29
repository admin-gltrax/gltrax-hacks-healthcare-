"""Reader agent: Muse Spark vision reads the paper the system mails people.

A photo or scan of a denial letter, an itemized bill or an explanation of
benefits (EOB) becomes structured fields the crew can act on. Pasted text works
too. The model reads; code validates: dates must parse, money must be numbers,
categories must be known, and a quote must really appear in pasted text. Fields
that fail are dropped, never guessed. The image itself is not kept.

The money math (what's owed, what's overbilled) is never left to the model:
see match_bill().
"""
from __future__ import annotations

import base64
import re
from datetime import date

from . import ai

MARKER = "PJ READER"
MAX_IMAGE_BYTES = 6_000_000
MAX_TEXT = 8000

REASON_KEYS = ["not_medically_necessary", "missing_info", "out_of_network", "experimental", "not_sure"]

_S = {"type": "string"}
_N = {"type": "number"}
SCHEMAS = {
    "denial_letter": ai.schema("denial_letter", {
        "plan": _S, "member_name": _S, "member_id": _S, "service": _S,
        "denied_on": {"type": "string", "description": "Date of the notice, YYYY-MM-DD"},
        "reason_category": {"type": "string", "enum": REASON_KEYS},
        "reason_quote": {"type": "string", "description": "The plan's stated reason, word for word"},
        "criteria": {"type": "array", "items": _S, "description": "Coverage rules the letter lists, word for word"},
        "appeal_by": {"type": "string", "description": "Appeal deadline printed on the letter, YYYY-MM-DD, or empty"},
        "appeal_days": {"type": "integer", "description": "Days allowed to appeal, if printed, else 0"},
        "appeals_fax": _S, "expedited_available": {"type": "boolean"}, "case_number": _S}),
    "bill": ai.schema("bill", {
        "biller": _S, "patient_name": _S, "service_date": {"type": "string", "description": "YYYY-MM-DD"}, "account": _S,
        "lines": {"type": "array", "items": {"type": "object", "properties": {"code": _S, "description": _S, "amount": _N},
                                             "required": ["code", "description", "amount"]}},
        "amount_due": _N}),
    "eob": ai.schema("eob", {
        "payer": _S, "member_name": _S, "service_date": {"type": "string", "description": "YYYY-MM-DD"}, "claim": _S,
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "code": _S, "description": _S, "billed": _N, "plan_paid": _N, "you_owe": _N},
            "required": ["code", "description", "billed", "plan_paid", "you_owe"]}},
        "total_you_owe": _N}),
}
LABELS = {"denial_letter": "denial letter", "bill": "itemized bill", "eob": "explanation of benefits"}

INSTRUCTIONS = f"""[{MARKER}] You read one document a patient gave their assistant. Extract only what is printed on it.
If a field isn't on the document, use an empty string, 0, false or an empty list. Never guess or fill in.
Copy quotes and listed rules word for word. Dates as YYYY-MM-DD. Money as plain numbers (210.00 -> 210).
Every line item on a bill or EOB is its own entry, even if two lines are identical. Skip total rows."""


class ReadError(Exception):
    pass


def check_image(data_url: str) -> str:
    m = re.fullmatch(r"data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)", data_url or "")
    if not m:
        raise ReadError("That file isn't a PNG, JPEG or WebP image.")
    if len(m.group(2)) * 3 // 4 > MAX_IMAGE_BYTES:
        raise ReadError("That image is too large (6 MB max).")
    base64.b64decode(m.group(2)[:64] + "==", validate=False)
    return data_url


async def read(kind: str, image: str | None = None, text: str | None = None, account: str | None = None) -> dict:
    """Returns the validated fields plus "_dropped" (fields that failed validation). Raises ai.AIUnavailable."""
    if kind not in SCHEMAS:
        raise ReadError(f"PJ can't read a {kind} yet.")
    content: list[dict] = [{"type": "text", "text": f"{INSTRUCTIONS}\nDocument type: {LABELS[kind]} ({kind})."}]
    if image:
        content.append({"type": "image_url", "image_url": {"url": check_image(image)}})
    elif text and text.strip():
        content.append({"type": "text", "text": "DOCUMENT TEXT:\n" + text[:MAX_TEXT]})
    else:
        raise ReadError("Add a photo of the document or paste its text.")
    raw = await ai.chat_json("reader", [{"role": "user", "content": content}], SCHEMAS[kind], account=account)
    return clean(kind, raw, text if not image else None)


# ---------------------------------------------------------------- validation

def _str(v, n: int = 300) -> str:
    return " ".join(str(v or "").replace(" (fictional)", "").split())[:n]


def _date(v) -> str:
    try:
        return date.fromisoformat(str(v or "").strip()[:10]).isoformat()
    except ValueError:
        return ""


def _money(v) -> float | None:
    try:
        x = round(float(str(v).replace("$", "").replace(",", "")), 2)
    except (TypeError, ValueError):
        return None
    return x if 0 <= x < 1_000_000 else None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def clean(kind: str, raw: dict, source_text: str | None = None) -> dict:
    out: dict = {}
    dropped: list[str] = []
    if kind == "denial_letter":
        for k in ("plan", "member_name", "member_id", "service", "appeals_fax", "case_number"):
            out[k] = _str(raw.get(k), 160)
        for k in ("denied_on", "appeal_by"):
            out[k] = _date(raw.get(k))
            if raw.get(k) and not out[k]:
                dropped.append(k)
        r = raw.get("reason_category")
        out["reason_category"] = r if r in REASON_KEYS else "not_sure"
        out["reason_quote"] = _str(raw.get("reason_quote"), 600).strip('"')
        if source_text and out["reason_quote"] and _norm(out["reason_quote"]) not in _norm(source_text):
            dropped.append("reason_quote")  # a "quote" that isn't in the text is not a quote
            out["reason_quote"] = ""
        out["criteria"] = [_str(c, 300) for c in (raw.get("criteria") or []) if _str(c)][:8]
        try:
            out["appeal_days"] = max(0, min(365, int(raw.get("appeal_days") or 0)))
        except (TypeError, ValueError):
            out["appeal_days"] = 0
        out["expedited_available"] = bool(raw.get("expedited_available"))
    elif kind in ("bill", "eob"):
        for k in ("biller", "patient_name", "account") if kind == "bill" else ("payer", "member_name", "claim"):
            out[k] = _str(raw.get(k), 160)
        out["service_date"] = _date(raw.get("service_date"))
        money = ("amount",) if kind == "bill" else ("billed", "plan_paid", "you_owe")
        lines = []
        for ln in (raw.get("lines") or [])[:40]:
            if not isinstance(ln, dict):
                continue
            vals = {m: _money(ln.get(m)) for m in money}
            if any(v is None for v in vals.values()):
                dropped.append("a line item")
                continue
            lines.append({"code": _str(ln.get("code"), 12), "description": _str(ln.get("description"), 80), **vals})
        out["lines"] = lines
        total_key = "amount_due" if kind == "bill" else "total_you_owe"
        out[total_key] = _money(raw.get(total_key))
        if out[total_key] is None:
            dropped.append(total_key)
            out[total_key] = round(sum(ln[money[-1]] for ln in lines), 2)
    out["_dropped"] = dropped
    return out


# ---------------------------------------------------------------- bill vs EOB: code does the math

def match_bill(bill: dict, eob: dict) -> dict:
    """Compare the bill's lines with the EOB. Returns problems, billed, owed and the overcharge."""
    problems: list[str] = []
    eob_by_code: dict[str, list[dict]] = {}
    for ln in eob.get("lines", []):
        eob_by_code.setdefault(ln["code"], []).append(ln)
    bill_by_code: dict[str, list[dict]] = {}
    for ln in bill.get("lines", []):
        bill_by_code.setdefault(ln["code"], []).append(ln)
    for code, lines in bill_by_code.items():
        on_eob = len(eob_by_code.get(code, []))
        if on_eob and len(lines) > on_eob:
            problems.append(f"Code {code} ({lines[0]['description']}) is billed {len(lines)} times; the plan processed it "
                            f"{on_eob} time{'s' if on_eob != 1 else ''}.")
        elif not on_eob:
            problems.append(f"Code {code} ({lines[0]['description']}) isn't on the plan's EOB at all.")
    billed = bill.get("amount_due") or round(sum(ln["amount"] for ln in bill.get("lines", [])), 2)
    owed = eob.get("total_you_owe")
    owed = round(sum(ln["you_owe"] for ln in eob.get("lines", [])), 2) if owed is None else owed
    if billed > owed:
        problems.append(f"The bill asks for ${billed:,.2f}; the EOB says the patient owes ${owed:,.2f}. "
                        "For covered in-network care, the office can't bill more than the EOB's \"you owe\".")
    return {"problems": problems, "billed": billed, "owed": owed, "overcharge": round(max(0.0, billed - owed), 2)}
