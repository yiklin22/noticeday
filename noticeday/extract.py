"""Rule-based extraction of term, renewal and notice facts from contract text.

Each field carries the character span it came from, so the review screen can
show the clause. A field the rules cannot find is left out; it is never
filled with a default.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from .text import Duration, find_dates, find_durations, normalize, sentences

FIELDS = ("start_date", "end_date", "term", "renewal", "auto_renew", "notice", "renewal_limit", "option_notice")


@dataclass
class Field:
    value: object
    start: int
    end: int
    rule: str


@dataclass
class Extraction:
    text: str
    fields: dict[str, Field] = field(default_factory=dict)

    def get(self, name):
        f = self.fields.get(name)
        return f.value if f else None

    def quote(self, name, pad: int = 0) -> str:
        f = self.fields[name]
        return self.text[max(0, f.start - pad): f.end + pad]


EFFECTIVE_CUES = [
    # The term clause's own start beats the signing date: "The term of this Agreement shall commence on ...",
    # "commencing the 1st day of September 2004", "The commencement date for this contract will be ...".
    (re.compile(r"(?:(?:(?<!renewal\s)(?<!extension\s)(?<!additional\s)\bterm\b|\bthis\s+\w+|\bappointment\b|\bfranchise\b)(?:(?!renew|extension)[^.;]){0,80}?"
                r"(?:shall|will|to)\s+(?:commence|begin|start)\s+(?:on|as\s+of)|"
                r"(?:(?<!renewal\s)(?<!extension\s)(?<!additional\s)\bterm\b|\bthis\s+\w+)(?:(?!renew|extension)[^.;]){0,80}?,?\s+commencing(?:\s+on)?|"
                r"commencement\s+date[^.;]{0,30}?(?:will\s+be|shall\s+be|is|means:?)|"
                r"effective\s+date\s+of\s+the\s+\w+\s+(?:will|shall)\s+be)\s*(?:the\s+)?$", re.I), 4.5, "commence"),
    (re.compile(r"effective(?:\s+date)?[\s\"'\)]*(?:as\s+of|on|from|is|shall\s+be|means|:)?[\s\"'(]*(?:the\s+)?$", re.I), 4, "effective"),
    (re.compile(r"(?:dated|entered\s+into|made)(?:\s+and\s+entered\s+into)?(?:\s+effective)?\s+(?:as\s+of|on|this)(?:\s+this)?\s*(?:the\s+)?$", re.I), 3, "dated"),
    (re.compile(r"\bas\s+of\s*(?:the\s+)?$", re.I), 3, "as_of"),
    (re.compile(r"(?:dated|entered\s+into|made)\b.{0,40}$", re.I), 2, "dated_near"),
]

TERM_SENTENCE = re.compile(
    r"\bterm\b|expir|remain\s+in\s+(?:full\s+)?(?:force|effect)|continue\s+in\s+(?:full\s+)?(?:force|effect)",
    re.I,
)
END_CUE = re.compile(
    r"(?:expiration\s+date\"?\s+(?:means|shall\s+mean|is)|until(?:\s+the\s+earlier\s+of\s*:?\s*(?:\(?(?:i|a|1)\)\s*)?)?|through(?:\s+and\s+including)?|up\s+to(?:\s+and\s+including)?|expire[sd]?\s+(?:at\s+[^,;]{0,40}?\s+)?on|terminate[sd]?\s+on|ending\s+on|end\s+on|expiring\s+on|thru)"
    r"\s*(?:the\s+)?(?:close\s+of\s+business\s+on\s+|midnight\s+(?:on\s+)?|11:59\s*p\.?m\.?[^,]{0,30}?on\s+)?$",
    re.I,
)
PERPETUAL = re.compile(
    r"perpetu|in\s+perpetuity|indefinite|until\s+(?:it\s+is\s+)?terminated|unless\s+and\s+until\s+terminated|"
    r"until\s+(?:such\s+time\s+as\s+)?(?:either|one|both|the)\s+part(?:y|ies)\s+terminate|until\s+termination|unlimited\s+period",
    re.I,
)
END_CUE_EXTRA = re.compile(r"(?:concluding|ending|terminating|expiring)\s*(?:on\s+)?$", re.I)
AFTER_TERM = re.compile(r"after\s+(?:the\s+)?(?:expiration\s+of\s+the\s+)?(?:initial|original)\s+term|\bthereafter\b", re.I)
# Where the initial term's text stops (renewal talk starts). Kept narrower than
# RENEW so a "continues month to month" phrase does not cut the term sentence.
RENEW_CUT = re.compile(r"renew|successive|automatically\s+extend|extended\s+automatically|extended\s+for|additional\s+(?:term|period)s?\b", re.I)
RENEW = re.compile(r"renew|successive|automatically\s+extend|extend(?:ed)?\s+automatically|automatic\s+extension|extended\s+(?:for|by)|"
                   r"additional\s+(?:term|period)s?\b|continue\s+(?:on\s+a\s+|thereafter\s+)?(?:month[\s-]+to[\s-]+month|year[\s-]+to[\s-]+year)|"
                   r"(?:effective|continue)\s+(?:on\s+a\s+)?month[\s-]+to[\s-]+month|from\s+year\s+to\s+year", re.I)
AUTO = re.compile(
    r"automatic|unless\s+(?:either|one|a)\s+part|unless\s+.{0,80}?notice|shall\s+(?:be\s+)?(?:renew|extend)|will\s+(?:be\s+)?(?:renew|extend)",
    re.I,
)
OPTION = re.compile(r"\bmay\s+(?:be\s+)?(?:renew|extend)|option\s+to\s+(?:renew|extend)|right\s+to\s+(?:renew|extend)|renewable", re.I)
MUTUAL = re.compile(r"mutual(?:ly)?\s+(?:written\s+)?(?:agree|consent)|by\s+mutual|upon\s+mutual|written\s+agreement\s+of\s+(?:both|the)\s+parties|parties\s+(?:may\s+)?agree|agree(?:s|d)?\s+in\s+writing|satisfactory\s+agreement|to\s+be\s+agreed", re.I)
CURE = re.compile(r"within\s*$|cure|breach|default", re.I)
NOTICE_CONTEXT = re.compile(r"renew|expir|end\s+of\s+(?:the|such|any|its)\s+(?:then[- ]current\s+|initial\s+|renewal\s+)?term|extend|extension|"
                            # an open-ended continuation: its notice period is how it is stopped
                            r"month[\s-]+to[\s-]+month|year[\s-]+to[\s-]+year|continue[^.;]{0,60}until\s+(?:it\s+is\s+)?terminated|"
                            r"automatically\s+continue|continue[^.;]{0,40}until\s+(?:either|one)\s+party\s+gives", re.I)
STRONG_TERM = re.compile(
    r"term\s+of\s+(?:this|the)\s+\w+|initial\s+term|\"?expiration\s+date\"?\s+(?:means|shall\s+mean|is)|\"term\"|the\s+term\s+(?:shall|will|is)|"
    r"(?:this|the)\s+agreement\s+(?:shall|will|is|becomes?)\s+(?:be\s+)?(?:become\s+)?(?:commence|begin|continue|remain|expire|terminate|effective|in\s+(?:full\s+)?(?:force|effect))|"
    r"(?:agreement|contract)\s+(?:shall|will)\s+(?:have|run)|entered\s+into\s+for|contract\s+period|engagement|"
    r"(?:this|the)\s+agreement\s+(?:shall|will)\s+(?:take\s+effect|be\s+valid|be\s+deemed\s+effective)|"
    r"(?:shall|will)\s+(?:expire|terminate)\s+on\b|come\s+into\s+force|remain\s+valid|have\s+a\s+duration|"
    r"\bterm\s*:\s*(?:\w+\s+\d{1,2}\b|\d)|expiration\s+date\"?\s*:|(?:effective|initial|fixed)\s+term\s+(?:is|shall\s+be|will\s+be)\b",
    re.I,
)
SURVIVAL = re.compile(r"^[^.;]{0,30}?\b(?:after|following|beyond|post)\b[^.;]{0,50}?(?:terminat|expir)", re.I)
THEREAFTER = re.compile(r"^[^.;]{0,30}?\bthereafter\b", re.I)
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
            "eighth": 8, "ninth": 9, "tenth": 10, "fifteenth": 15, "twentieth": 20, "twenty-fifth": 25}
ANNIVERSARY = re.compile(
    r"(?:(?P<word>" + "|".join(ORDINALS) + r")(?:\s*\(\s*\d+\s*(?:st|nd|rd|th)?\s*\))?|(?P<num>\d+)\s*(?:st|nd|rd|th))\s+"
    r"(?:anniversary|(?:contract|agreement|lease)\s+year\b)",
    re.I,
)
NOTICE_AFTER = re.compile(
    r"^(?:[^.;]{0,60}?\b(?:prior|before|in\s+advance|preceding)\b|['\u2019]?s?\s*(?:advance\s+|prior\s+)?(?:written\s+)?notice)", re.I)
IMPLICIT_RENEWAL = [
    (re.compile(r"year[\s-]+to[\s-]+year|(?:annual|yearly)\s+basis|annually\s+renew|renew(?:s|ed|ing)?\s+(?:tacitly\s+)?(?:annually|every\s+year|each\s+year)|"
                r"an\s+additional\s+year|one\s+further\s+year|annual\s+(?:renewal\s+)?(?:period|term)s?|annual\s+renewals?", re.I), Duration(1, "year")),
    (re.compile(r"month[\s-]+to[\s-]+month|monthly\s+(?:basis|periods?)|an\s+additional\s+month", re.I), Duration(1, "month")),
    (re.compile(r"half\s+a\s+year", re.I), Duration(6, "month")),
]
NOTICE_BEFORE = re.compile(r"notice[^.;]{0,40}$", re.I)
LENGTH_OF = re.compile(r"\s*(?:-\s*)?(?:initial\s+|renewal\s+|additional\s+|extension\s+|successive\s+)?(?:terms?|periods?)\b", re.I)


EFFECTIVE_LABEL = re.compile(r"\s*,?\s*\((?:the\s+|such\s+date,?\s+the\s+|hereinafter\s+(?:the\s+)?)?[\"“]?effective\s*date[\"”]?\s*\)", re.I)


def _start_date(text: str):
    best = None
    head = max(3000, len(text) // 5)
    for d, s, e in find_dates(text):
        window = text[max(0, s - 90): s]
        # Filing footers ("Source: ACME INC, 10-K, 3/21/2019") are not the contract's date.
        if re.search(r"Source:\s*[^,]{1,60}(?:,[^,]{1,30}){1,3},\s*$|\b(?:10-K|10-Q|8-K|S-1|F-1|20-F|10KSB|1-A|SB-2|S-4|10-12G)(?:/A)?\s*,\s*$",
                     text[max(0, s - 90): s]):
            continue
        # The date of another document: "... Agreement dated May 1, 2009 (the
        # "EPC Agreement")" or "... dated 12 December 2003 entitled ...".
        after = text[e: e + 60]
        named = re.match(r"\s*,?\s*\((?:the\s+|hereinafter\s+)?[\"\u201c]([^\"\u201d]{1,40})[\"\u201d]", after)
        if named and not re.search(r"effective|^(?:this\s+)?agreement$|commencement|execution|contract\s+date", named.group(1), re.I):
            continue
        if re.match(r"\s*,?\s*entitled\b", after, re.I):
            continue
        # "... Services Agreement, dated as of November 28, 2013, by and between FSL and TPH": a date
        # of another agreement in the body. The contract's own preamble says "this" or comes first.
        if s > 1500 and re.match(r"\s*,?\s*(?:by\s+and\s+)?(?:between|among)\b", after, re.I) and not re.search(r"\bthis\b", window[-80:], re.I):
            continue
        score, rule = 0, ""
        for rx, sc, name in EFFECTIVE_CUES:
            if rx.search(window):
                score, rule = sc, name
                break
        # "... as of April 14, 2014 (the "Effective Date")": the contract names this date.
        if EFFECTIVE_LABEL.match(after):
            score, rule = 5, "effective_label"
        if s < head:
            score += 0.5
        if s >= head and rule not in ("effective", "effective_label", "commence"):
            continue
        if not rule:
            score, rule = max(score, 1), "first_date"
        if best is None or score > best[0]:
            best = (score, Field(d, s, e, rule))
    return best[1] if best else None


def _term_sentences(text: str):
    """Sentences that talk about the term, best first."""
    scored = []
    for s, e in sentences(text):
        sent = text[s:e]
        if not STRONG_TERM.search(sent):
            continue
        low = sent.lower()
        score = 0
        score += 3 if re.search(r"term\s+of\s+this\s+(?:agreement|contract|lease)|initial\s+term|this\s+agreement\s+shall\s+(?:commence|continue|remain|expire|terminate)", low) else 0
        score += 2 if re.search(r"commenc|effective\s+date", low) else 0
        score += 1 if "expir" in low else 0
        score += 1 if re.search(r"\bterm\b", low) else 0
        score += 1 if s < len(text) // 2 else 0
        score -= 3 if re.search(r"\bmay\s+(?:\w+\s+){0,2}terminat", low) else 0
        score -= 2 if re.search(r"confidential|warrant|survive|insurance|indemnif", low) else 0
        if score > 0:
            scored.append((score, s, e))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def _term(text: str, start_field):
    """Return (end_date field, term field) for the initial term."""
    for score, s, e in _term_sentences(text)[:8]:
        sent = text[s:e]
        # Stop before text about what happens after the initial term.
        first_value = min([ds - s for _, ds, _ in find_dates(sent, s)[:1]] +
                          [ds - s for _, ds, _ in list(find_durations(sent, s))[:1]] + [len(sent)])
        # "after the initial term" always ends the initial term's text; a bare
        # "thereafter" only does once a date or duration has been stated.
        after = next((m for m in AFTER_TERM.finditer(sent)
                      if m.start() > first_value or not m.group().lower().startswith("thereafter")), None)
        later = [m.start() for m in (RENEW_CUT.search(sent), after) if m]
        cut = min(later) if later else len(sent)
        for d, ds, de in find_dates(sent, s):
            if ds - s > cut:
                break
            if (END_CUE.search(text[max(s, ds - 80): ds]) or END_CUE_EXTRA.search(text[max(s, ds - 40): ds])
                    or re.search(r"\d{4}\s*(?:to|-|\u2013)\s*$", text[max(s, ds - 12): ds])):
                return Field(d, ds, de, "end_date"), None
        for dur, ds, de in find_durations(sent[:cut], s):
            if dur.unit not in ("year", "month"):
                continue
            # "any subsequent one year renewal term": a renewal's length, not the initial term.
            if re.match(r"\s*(?:-\s*)?(?:renewal|extension|additional|successive)\b", text[de: de + 20], re.I):
                continue
            if SURVIVAL.search(text[de: de + 90]):
                continue
            before = text[s:ds]
            if THEREAFTER.search(text[de: de + 60]) and (
                    re.search(r"terminat|expir", before[-80:], re.I)
                    or re.search(r"during\s+the\s+term|term\s+of\s+this\s+agreement\s+and", before, re.I)
                    or not re.search(r"commenc|effective|begin|start|execut", before, re.I)):
                continue
            # "every 12 months", "within the first six months": not the term's length.
            if re.search(r"\b(?:every|each|within|first|next|per)\s+(?:\w+\s+)?$", text[max(s, ds - 20): ds], re.I):
                continue
            # A term counted from an event ("ten years after the First Commercial
            # Sale") has no fixed end date; leave it for a person.
            m = re.match(r"\s*(?:\(\w+\)\s*)?(?:after|following|from)\s+(?:the\s+)?(.{0,40})", text[de: de + 60], re.I)
            if m and not re.match(r"(?:effective|commencement|execution|signing|start|beginning|date\s+(?:hereof|of\s+this|first|signed|of\s+execution|of\s+signature)|such\s+date|this\s+agreement)",
                                  m.group(1), re.I):
                continue
            if NOTICE_AFTER.search(text[de: de + 60]) and not re.match(r"\s*(?:from|after|following|commencing)", text[de: de + 30], re.I):
                continue
            return None, Field(dur, ds, de, "term_length")
        a = ANNIVERSARY.search(sent[:cut])
        if a:
            n = ORDINALS[a.group("word").lower()] if a.group("word") else int(a.group("num"))
            return None, Field(Duration(n, "year"), s + a.start(), s + a.end(), "anniversary")
        m = PERPETUAL.search(sent[:cut])
        if m:
            return Field("perpetual", s + m.start(), s + m.end(), "perpetual"), None
    return None, None


RENEWAL_LIMIT = re.compile(
    r"\b(?:up\s+to\s+|a\s+maximum\s+of\s+|no\s+more\s+than\s+)?"
    r"(?P<count>one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s*(?:\(\s*\d+\s*\)\s*)?"
    r"(?:additional|further|more)\b(?:\s+\S+){0,4}?\s+(?:renewal\s+|extension\s+)?(?:term|period|year)s?\b",
    re.I,
)


def _is_notice(text: str, ds: int, de: int, floor: int) -> bool:
    """A notice period for ending the term, not a cure period after a breach."""
    if not (NOTICE_AFTER.search(text[de: de + 60]) or NOTICE_BEFORE.search(text[max(floor, ds - 40): ds])):
        return False
    cure = CURE.search(text[max(floor, ds - 25): ds])
    if cure and cure.group().lower().startswith("within") and re.match(r"[^.;]{0,30}?\b(?:prior|before)\b", text[de: de + 40], re.I):
        cure = None  # "within sixty (60) days prior to the expiration" is a notice window, not a cure period
    if cure or re.match(r"[^.;]{0,30}?after\s+(?:receipt|receiving|being\s+given|the\s+giving|such\s+notice|notice|written\s+notice)", text[de: de + 60], re.I):
        return False
    return bool(NOTICE_CONTEXT.search(text[max(floor, ds - 150): de + 150]))


OPTION_SENTENCE = re.compile(
    r"option\s+to\s+(?:renew|extend)|right\s+to\s+(?:renew|extend)|(?:elects?|wish(?:es)?|desires?|intends?)\s+to\s+(?:renew|extend)|"
    r"\bmay\s+(?:\w+\s+){0,2}(?:renew|extend)",
    re.I,
)


def _option_notice(text: str):
    """Notice one party must give to *exercise* an option to renew or extend."""
    for s, e in sentences(text):
        sent = text[s:e]
        if not OPTION_SENTENCE.search(sent) or MUTUAL.search(sent):
            continue
        for dur, ds, de in find_durations(sent, s):
            near = text[max(s, ds - 80): de + 60]
            if re.search(r"terminat|cancel", near, re.I):
                continue
            if dur.unit in ("day", "week", "month") and _is_notice(text, ds, de, s):
                return Field(dur, ds, de, "option_notice")
    return None


def _renewal(text: str):
    """Return (renewal, auto_renew, notice) fields."""
    best = None
    for s, e in sentences(text):
        sent = text[s:e]
        r = RENEW.search(sent)
        if not r:
            continue
        low = sent.lower()
        if re.search(r"renew(?:al|ed)?\s+(?:of\s+)?(?:the\s+)?(?:license|insurance|polic|registration|permit|purchase\s+order)|calendar\s+quarter|\bquarter\b", low):
            continue
        score = 1
        score += 2 if "automatic" in low else 0
        score += 2 if "successive" in low or "additional" in low else 0
        score += 1 if re.search(r"\bterm\b|period", low) else 0
        score += 1 if re.search(r"expir|initial\s+term", low) else 0
        score += 1 if "notice" in low else 0
        if best is None or score > best[0]:
            best = (score, s, e)
    if best is None:
        return None, None, None, None
    _, s, e = best
    sent = text[s:e]
    r = RENEW.search(sent)
    renewal = notice = None
    if MUTUAL.search(sent) and not AUTO.search(sent):
        return None, None, None, None
    for dur, ds, de in find_durations(sent, s):
        # "successive 5-year terms": a length of a term, never a notice period.
        is_notice = _is_notice(text, ds, de, s) and not LENGTH_OF.match(text[de: de + 30])
        if is_notice and dur.unit in ("day", "week", "month") or is_notice and notice is None and dur.unit == "year" and renewal:
            if notice is None:
                notice = Field(dur, ds, de, "notice_in_renewal")
            continue
        if renewal is None and ds - s >= r.start() - 30 and dur.unit in ("year", "month"):
            renewal = Field(dur, ds, de, "renewal_length")
    if renewal is None:
        for rx, dur in IMPLICIT_RENEWAL:
            m = rx.search(sent)
            if m:
                renewal = Field(dur, s + m.start(), s + m.end(), "renewal_phrase")
                break
    if notice is None:
        # The notice period is often in the next sentence.
        nxt = text[e: e + 600]
        for dur, ds, de in find_durations(nxt, e):
            if _is_notice(text, ds, de, e):
                if dur.unit in ("day", "week", "month"):
                    notice = Field(dur, ds, de, "notice_next_sentence")
                    break
    limit = RENEWAL_LIMIT.search(sent)
    if limit:
        from .text import words_to_int
        count = int(limit.group("count")) if limit.group("count").isdigit() else words_to_int(limit.group("count"))
        limit = Field(count, s + limit.start(), s + limit.end(), "renewal_limit") if count else None
    auto = bool(AUTO.search(sent)) and not OPTION.search(sent)
    auto_field = Field(auto, s + r.start(), s + r.end(), "auto" if auto else "option_or_unclear")
    if renewal is None and not auto:
        return None, None, None, None
    return renewal, auto_field, notice, limit


def extract(raw_text: str) -> Extraction:
    text = normalize(raw_text)
    ex = Extraction(text)
    start = _start_date(text)
    if start:
        ex.fields["start_date"] = start
    end, term = _term(text, start)
    if end:
        ex.fields["end_date"] = end
    if term:
        ex.fields["term"] = term
    renewal, auto, notice, limit = _renewal(text)
    if renewal is None and auto and auto.value and term:
        sent = text[auto.start: auto.start + 300]
        if re.search(r"same\s+(?:duration|length|period)|equal\s+(?:in\s+length\s+)?to\s+the\s+initial\s+term", sent, re.I):
            renewal = Field(term.value, auto.start, auto.end, "same_as_initial_term")
    for name, f in (("renewal", renewal), ("auto_renew", auto), ("notice", notice), ("renewal_limit", limit)):
        if f:
            ex.fields[name] = f
    if not (auto and auto.value):
        option = _option_notice(text)
        if option:
            ex.fields["option_notice"] = option
    return ex


def initial_end(ex: Extraction):
    """The initial expiration the extraction implies (date, 'perpetual' or None)."""
    from .deadlines import initial_term_end
    return initial_term_end(ex.get("start_date"), ex.get("end_date"), ex.get("term"))
