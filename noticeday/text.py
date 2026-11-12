"""Text helpers: whitespace normalisation, number words, durations and dates.

Everything here is plain parsing. Nothing guesses: a phrase that does not
parse returns None.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass

MONTHS = {
    name.lower(): i for i, name in enumerate(calendar.month_name) if name
}
MONTHS.update({
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
})
MONTH_RE = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
NUMBER_WORDS = set(UNITS) | set(TENS) | {"hundred", "and"}


def _tail_value(tokens: list[str]) -> int | None:
    if not tokens or tokens[0] == "and":
        return None
    total = 0
    for t in tokens:
        if t in UNITS:
            total += UNITS[t]
        elif t in TENS:
            total += TENS[t]
        elif t == "hundred":
            total = (total or 1) * 100
        elif t != "and":
            return None
    return total


def normalize(text: str) -> str:
    """Collapse runs of whitespace; contract text from PDFs is full of them."""
    return re.sub(r"\s+", " ", text).strip()


def words_to_int(phrase: str) -> int | None:
    """'one hundred and eighty' -> 180. Uses the longest numeric tail,
    so 'a period of sixty' -> 60."""
    tokens = [t for t in re.split(r"[\s-]+", phrase.lower()) if t]
    while tokens and tokens[-1] not in NUMBER_WORDS:
        tokens.pop()
    for i in range(len(tokens)):
        v = _tail_value(tokens[i:])
        if v is not None:
            return v
    return None


@dataclass(frozen=True)
class Duration:
    n: int
    unit: str  # "day", "week", "month" or "year"

    @property
    def months(self) -> int | None:
        if self.unit == "year":
            return self.n * 12
        if self.unit == "month":
            return self.n
        return None

    def __str__(self) -> str:
        return f"{self.n} {self.unit}{'' if self.n == 1 else 's'}"


DURATION_RE = re.compile(
    r"(?:(?P<num>\d+)|(?P<words>[a-z]+(?:[\s-][a-z]+){0,4}))"
    r"\s*(?:\(\s*(?P<par>\d+)\s*\)\s*)?(?:-|\s)*"
    r"(?:calendar\s+|business\s+|working\s+|consecutive\s+)?"
    r"(?P<unit>year|month|day|week)s?\b",
    re.IGNORECASE,
)


def find_durations(text: str, offset: int = 0):
    """Yield (Duration, start, end) for each duration phrase in text."""
    for m in DURATION_RE.finditer(text):
        n = None
        if m.group("par"):
            n = int(m.group("par"))
        elif m.group("num"):
            n = int(m.group("num"))
        elif m.group("words"):
            n = words_to_int(m.group("words"))
        if n is None or n == 0:
            continue
        unit = m.group("unit").lower()
        # Start the span at the number, not at words the regex swallowed.
        start = m.start()
        if m.group("words") and not m.group("par"):
            for w in re.finditer(r"[a-z]+", m.group("words").lower()):
                if w.group() in NUMBER_WORDS - {"and"} and words_to_int(m.group("words")[w.start():]) == n:
                    start = m.start() + w.start()
                    break
        yield Duration(n, unit), start + offset, m.end() + offset


DATE_PATTERNS = [
    # September 7, 1999 / Sept. 7 1999
    (re.compile(r"\b" + MONTH_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b", re.I), "mdy"),
    # 7th day of September, 1999
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s+" + MONTH_RE + r"\s*,?\s*(\d{4})\b", re.I), "dmy"),
    # 7 September 1999
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + MONTH_RE + r"\s*,?\s*(\d{4})\b", re.I), "dmy"),
    # 9/7/1999 or 9-7-99
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4}|\d{2})\b"), "num"),
]


def _year(y: str) -> int:
    v = int(y)
    if len(y) == 2:
        v += 2000 if v < 60 else 1900
    return v


def find_dates(text: str, offset: int = 0):
    """Yield (date, start, end), sorted by position, no overlaps."""
    found = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                if kind == "mdy":
                    d = dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
                elif kind == "dmy":
                    d = dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
                else:
                    d = dt.date(_year(m.group(3)), int(m.group(1)), int(m.group(2)))
            except (ValueError, KeyError):
                continue
            found.append((d, m.start() + offset, m.end() + offset))
    found.sort(key=lambda x: (x[1], -(x[2] - x[1])))
    out, last_end = [], -1
    for d, s, e in found:
        if s >= last_end:
            out.append((d, s, e))
            last_end = e
    return out


def parse_us_date(s: str) -> dt.date | None:
    """CUAD answer format: M/D/YY or M/D/YYYY. Partial dates ('[]/[]/05') -> None."""
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\s*", s)
    if not m:
        return None
    try:
        return dt.date(_year(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def sentences(text: str):
    """Yield (start, end) of rough sentences. Long runs are cut at 1,200 chars."""
    start = 0
    for m in re.finditer(r"(?<=[a-z0-9\)\"'][.;:])\s+(?=[A-Z(\"\d])", text):
        end = m.start()
        while end - start > 1200:
            yield start, start + 1200
            start += 1200
        if end > start:
            yield start, end
        start = m.end()
    while len(text) - start > 1200:
        yield start, start + 1200
        start += 1200
    if start < len(text):
        yield start, len(text)
