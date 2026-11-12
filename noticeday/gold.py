"""Parse CUAD's lawyer-written answers (master_clauses.csv) into values.

Answers that cannot be scored exactly are marked, not guessed:
partial dates such as '[]/[]/05' and multi-valued answers ('2 years; 3 years')
come back as the string "unscorable".
"""
from __future__ import annotations

import re

from .text import Duration, parse_us_date, words_to_int

UNSCORABLE = "unscorable"


def parse_date_answer(s: str):
    s = s.strip()
    if not s:
        return None
    if s.lower() == "perpetual":
        return "perpetual"
    if ";" in s:
        return UNSCORABLE
    d = parse_us_date(s)
    return d if d else UNSCORABLE


def parse_duration_answer(s: str):
    """'successive 1 year' -> Duration(1, 'year'); '180 days / 6 months' -> both."""
    s = s.strip().lower()
    if not s or s == "[]":
        return None
    if s.startswith("perpetual") and "," not in s:
        return "perpetual"
    if ";" in s or "," in s:
        return UNSCORABLE
    found = []
    for part in s.split("/"):
        m = re.search(r"(\d+(?:\.\d+)?)\)?\s*(day|week|month|year)s?", part)
        if not m:
            w = re.search(r"([a-z\- ]+?)\s*\(\d+\)\s*(day|week|month|year)", part)
            if not w or words_to_int(w.group(1)) is None:
                continue
            found.append(Duration(words_to_int(w.group(1)), w.group(2)))
            continue
        n = float(m.group(1))
        unit = m.group(2)
        if n != int(n):
            if unit == "year":
                n, unit = n * 12, "month"
            if n != int(n):
                return UNSCORABLE
        found.append(Duration(int(n), unit))
    # "2 successive 1 year" means two renewals of one year each; the regex
    # skips "2 successive" and keeps the term length.
    if not found:
        return UNSCORABLE
    return found[0] if len(found) == 1 else tuple(found)


def same_duration(pred: Duration | None, gold) -> bool:
    """Gold may list alternatives ('180 days / 6 months'). Years and months
    are compared in months; days and weeks in days."""
    if pred is None or gold in (None, UNSCORABLE, "perpetual"):
        return False
    options = gold if isinstance(gold, tuple) else (gold,)
    for g in options:
        if pred.months is not None and g.months is not None and pred.months == g.months:
            return True
        days = lambda d: d.n * (7 if d.unit == "week" else 1) if d.unit in ("day", "week") else None
        if days(pred) is not None and days(pred) == days(g):
            return True
    return False
