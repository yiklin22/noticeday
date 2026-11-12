"""Local-model extraction (Qwen3-4B-Instruct on CPU) with an evidence gate.

The model reads only the passages most likely to hold term facts, answers in
JSON, and must quote the words behind each value. `verify` keeps a value only
if the quote is in the contract and the value can be parsed back out of that
quote. Values that fail are dropped, so a person is asked instead.

Predictions are cached in .cache/model/<split>.jsonl, one line per contract,
so a stopped run resumes.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

from .extract import IMPLICIT_RENEWAL, PERPETUAL
from .gold import same_duration
from .text import Duration, find_dates, find_durations, normalize, sentences

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "model"
MODEL_ID = os.environ.get("NOTICEDAY_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
KEYS = ("effective_date", "end_date", "initial_term", "renewal_term", "auto_renew", "notice_period")

CUES = [
    (re.compile(r"renew|successive|extend", re.I), 3),
    (re.compile(r"term\s+of\s+this|initial\s+term|\bterm\b", re.I), 2),
    (re.compile(r"expir|perpetu|anniversary|until\s+terminated", re.I), 2),
    (re.compile(r"commenc|effective\s+date|effective\s+as\s+of", re.I), 2),
    (re.compile(r"notice", re.I), 1),
    (re.compile(r"confidential|indemnif|insurance|warrant|cure|breach", re.I), -2),
]

PROMPT = """Below are passages from a contract, numbered in document order.

{passages}

Extract the contract's term and renewal facts. Return one JSON object with these keys:
"effective_date": the date the agreement takes effect, as "YYYY-MM-DD", or null.
"end_date": the date the initial term ends if the contract states a calendar date ("YYYY-MM-DD"); "perpetual" if it runs until someone terminates it; otherwise null.
"initial_term": the initial term's length if stated as a length, as {{"n": 2, "unit": "year"}} (unit is day, week, month or year), otherwise null.
"renewal_term": the length of each renewal period, whether automatic or at one party's option, as {{"n": 1, "unit": "year"}}, or null. Ignore renewals that need both parties to agree.
"auto_renew": true if the contract renews unless a party gives notice, false if a renewal needs someone to act, null if there is no renewal.
"notice_period": how long before the end of a term a party must give notice to stop the renewal, as {{"n": 60, "unit": "day"}}, or null. Not cure periods and not notice for termination at any time.
"quotes": an object with the same keys; for each non-null value, copy the exact words from the passages that state it (under 30 words).
Answer with the JSON object only."""


def passages(text: str, budget: int = 6000) -> str:
    """Preamble plus the highest-scoring sentences, in document order."""
    scored = []
    for s, e in sentences(text):
        sent = text[s:e]
        score = sum(w for rx, w in CUES if rx.search(sent))
        if score >= 2:
            scored.append((score, s, e))
    chosen, used = [(0, min(700, len(text)))], min(700, len(text))
    for score, s, e in sorted(scored, key=lambda x: (-x[0], x[1])):
        if s < 700:
            continue
        if used + (e - s) > budget:
            continue
        chosen.append((s, e))
        used += e - s
    chosen.sort()
    return "\n".join(f"[{i + 1}] {text[s:e]}" for i, (s, e) in enumerate(chosen))


def parse_json(raw: str):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def _dur(v):
    try:
        n, unit = int(v["n"]), str(v["unit"]).lower().rstrip("s")
    except (TypeError, KeyError, ValueError):
        return None
    return Duration(n, unit) if unit in ("day", "week", "month", "year") and n > 0 else None


def _date(v):
    try:
        return dt.date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def verify(answer: dict, text: str) -> tuple[dict, dict]:
    """Return (values, reasons). A value survives only if its quote is in the
    contract and the value can be read back out of the quote."""
    quotes = answer.get("quotes") or {}
    body = _squash(text)
    values, reasons = {}, {}
    for key in KEYS:
        raw = answer.get(key)
        if raw is None:
            continue
        if key in ("effective_date", "end_date"):
            value = "perpetual" if key == "end_date" and raw == "perpetual" else _date(raw)
        elif key == "auto_renew":
            value = raw if isinstance(raw, bool) else None
        else:
            value = _dur(raw)
        if value is None:
            reasons[key] = "unparseable value"
            continue
        q = quotes.get(key) if isinstance(quotes, dict) else None
        if not isinstance(q, str) or len(_squash(q)) < 3 or _squash(q) not in body:
            reasons[key] = "quote not found in contract"
            continue
        if isinstance(value, dt.date):
            ok = value in [d for d, _, _ in find_dates(normalize(q))]
        elif value == "perpetual":
            ok = bool(PERPETUAL.search(q))
        elif isinstance(value, Duration):
            ok = any(same_duration(value, d) for d, _, _ in find_durations(normalize(q))) or any(
                rx.search(q) and same_duration(value, d) for rx, d in IMPLICIT_RENEWAL)
        else:
            ok = True
        if not ok:
            reasons[key] = "value not in its quote"
            continue
        values[key] = value
    return values, reasons


def as_prediction(values: dict) -> dict:
    return {
        "start_date": values.get("effective_date"), "end_date": values.get("end_date"),
        "term": values.get("initial_term"), "renewal": values.get("renewal_term"),
        "auto_renew": values.get("auto_renew"), "notice": values.get("notice_period"),
    }


def raw_values(answer: dict) -> dict:
    """The model's answer without the evidence gate, for comparison."""
    out = {}
    for key in KEYS:
        raw = answer.get(key)
        if key in ("effective_date", "end_date"):
            out[key] = "perpetual" if key == "end_date" and raw == "perpetual" else _date(raw)
        elif key == "auto_renew":
            out[key] = raw if isinstance(raw, bool) else None
        else:
            out[key] = _dur(raw)
    return out


def load_model_predictions(recs: list[dict], method: str) -> dict:
    """method: model_raw, model (verified), union (rules, else verified model),
    agree (a value only where rules and verified model give the same one)."""
    from .predict import rules_prediction
    split = recs[0]["split"]
    cached = {}
    for line in open(CACHE / f"{split}.jsonl"):
        r = json.loads(line)
        cached[r["id"]] = r
    out = {}
    for rec in recs:
        if rec["id"] not in cached:
            raise SystemExit(f"no model output for {rec['id']}; run scripts/run_model.py --split {split}")
        answer = parse_json(cached[rec["id"]]["raw"]) or {}
        text = normalize(rec["text"])
        if method == "model_raw":
            out[rec["id"]] = as_prediction(raw_values(answer))
            continue
        model = as_prediction(verify(answer, text)[0])
        if method == "model":
            out[rec["id"]] = model
            continue
        rules = rules_prediction(rec["text"])
        merged = {}
        for k in model:
            a, b = rules[k], model[k]
            if method == "union":
                merged[k] = a if a is not None else b
            elif method == "agree":
                merged[k] = a if a is not None and str(a) == str(b) else None
            else:
                raise SystemExit(f"unknown method {method}")
        # Expiration may come from an end date or from start + term: keep
        # the pair that agrees as a whole.
        if method == "agree":
            from .deadlines import initial_term_end
            ea = initial_term_end(rules["start_date"], rules["end_date"], rules["term"])
            eb = initial_term_end(model["start_date"], model["end_date"], model["term"])
            merged["start_date"], merged["term"] = None, None
            merged["end_date"] = ea if ea is not None and str(ea) == str(eb) else None
        out[rec["id"]] = merged
    return out
