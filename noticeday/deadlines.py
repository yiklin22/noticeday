"""Date arithmetic for terms, renewals and notice deadlines.

Convention (it is CUAD's, see the CUAD README): a two-year term from
2/14/2019 ends on 2/14/2021, and 60 days' notice before that is due by
12/16/2020. A real contract may define it differently ("the day before the
anniversary"); the app shows the clause so a person can check.
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

from .text import Duration


def add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def shift(d: dt.date, dur: Duration, sign: int = 1) -> dt.date:
    if dur.months is not None:
        return add_months(d, sign * dur.months)
    days = dur.n * (7 if dur.unit == "week" else 1)
    return d + dt.timedelta(days=sign * days)


@dataclass
class Schedule:
    status: str                 # act_by | renews_no_notice | expires | expired | no_fixed_end | incomplete
    term_end: dt.date | None = None    # end of the term that is current on `today`
    act_by: dt.date | None = None      # last day to send notice of non-renewal
    cycles_rolled: int = 0
    reason: str = ""


def initial_term_end(start, end, term: Duration | None):
    """Explicit end date wins; otherwise start + term length."""
    if end == "perpetual":
        return "perpetual"
    if isinstance(end, dt.date):
        return end
    if start and term:
        return shift(start, term)
    return None


def schedule(start, end, term, renewal, auto_renew: bool, notice: Duration | None,
             today: dt.date, renewal_limit: int | None = None, option_notice: Duration | None = None) -> Schedule:
    """renewal_limit: how many renewals the contract allows ("one (1) additional
    period" -> 1); None means no limit was found."""
    first_end = initial_term_end(start, end, term)
    if first_end == "perpetual":
        return Schedule("no_fixed_end", reason="No fixed end date; check the termination clause.")
    if first_end is None:
        return Schedule("incomplete", reason="Term end unknown: need an end date, or a start date and a term length.")
    term_end, rolled = first_end, 0
    renews = auto_renew and isinstance(renewal, Duration)
    if renews:
        # Roll forward to the first cycle whose notice window has not closed.
        while (shift(term_end, notice, -1) if notice else term_end) < today and rolled < 500:
            if renewal_limit is not None and rolled >= renewal_limit:
                break
            term_end = shift(term_end, renewal)
            rolled += 1
        if renewal_limit is not None and rolled >= renewal_limit:
            # The term now running is the last one the contract allows.
            if term_end < today:
                return Schedule("expired", term_end=term_end, cycles_rolled=rolled,
                                reason=f"Ended after the last of {renewal_limit} allowed renewal(s).")
            return Schedule("expires", term_end=term_end, act_by=term_end, cycles_rolled=rolled,
                            reason=f"Final term: the contract allows {renewal_limit} renewal(s) and no more.")
    if not renews:
        if option_notice is not None and term_end >= today:
            by = shift(term_end, option_notice, -1)
            if by >= today:
                return Schedule("option_by", term_end=term_end, act_by=by,
                                reason=f"Renewal is your option: give notice {option_notice} before the term ends to renew.")
            return Schedule("expires", term_end=term_end, act_by=term_end,
                            reason="The window to exercise the renewal option has closed; the term ends on this date.")
        if term_end < today:
            return Schedule("expired", term_end=term_end, reason="Term ended and no automatic renewal was found.")
        return Schedule("expires", term_end=term_end, act_by=term_end,
                        reason="Ends on this date unless renewed; no automatic renewal found.")
    if notice is None:
        return Schedule("renews_no_notice", term_end=term_end, act_by=term_end, cycles_rolled=rolled,
                        reason="Renews automatically, but no notice period was found: check before this date.")
    return Schedule("act_by", term_end=term_end, act_by=shift(term_end, notice, -1), cycles_rolled=rolled,
                    reason=f"Renews for {renewal} unless notice is given {notice} before the term ends.")
