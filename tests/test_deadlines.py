import datetime as dt

from noticeday.deadlines import add_months, schedule
from noticeday.text import Duration

D = dt.date


def test_cuad_readme_example():
    # CUAD README: 2-year term from 2/14/2019, then 3-year renewals, 60 days' notice.
    s = schedule(D(2019, 2, 14), None, Duration(2, "year"), Duration(3, "year"), True, Duration(60, "day"), today=D(2020, 1, 1))
    assert s.status == "act_by" and s.term_end == D(2021, 2, 14) and s.act_by == D(2020, 12, 16)


def test_rolls_forward_to_open_cycle():
    # One-year auto renewals, 30 days notice. On 2026-11-13 the 2026-12-01 cycle
    # has passed its notice deadline (2026-11-01), so the next act-by is 2027-11-01.
    s = schedule(D(2020, 12, 1), None, Duration(1, "year"), Duration(1, "year"), True, Duration(30, "day"), today=D(2026, 11, 13))
    assert s.term_end == D(2027, 12, 1) and s.act_by == D(2027, 11, 1) and s.cycles_rolled == 6


def test_no_renewal_expires():
    assert schedule(D(2020, 1, 1), D(2030, 1, 1), None, None, False, None, today=D(2026, 1, 1)).status == "expires"
    assert schedule(D(2020, 1, 1), D(2021, 1, 1), None, None, False, None, today=D(2026, 1, 1)).status == "expired"


def test_missing_facts_are_reported_not_guessed():
    assert schedule(None, None, Duration(1, "year"), None, False, None, today=D(2026, 1, 1)).status == "incomplete"
    assert schedule(None, "perpetual", None, None, False, None, today=D(2026, 1, 1)).status == "no_fixed_end"
    s = schedule(D(2025, 6, 1), None, Duration(1, "year"), Duration(1, "year"), True, None, today=D(2026, 1, 1))
    assert s.status == "renews_no_notice"


def test_month_end_clamps():
    assert add_months(D(2024, 1, 31), 1) == D(2024, 2, 29)


def test_renewal_limit_stops_rolling():
    # Twelve months from 2017-11-30, "one (1) additional twelve month period", 90 days' notice.
    args = (D(2017, 11, 30), None, Duration(12, "month"), Duration(12, "month"), True, Duration(90, "day"))
    assert schedule(*args, today=D(2026, 11, 13)).act_by == D(2027, 9, 1)   # no limit known: wrong but rolls
    s = schedule(*args, today=D(2026, 11, 13), renewal_limit=1)
    assert s.status == "expired" and s.term_end == D(2019, 11, 30)
    s = schedule(*args, today=D(2018, 10, 1), renewal_limit=1)
    assert s.status == "expires" and s.term_end == D(2019, 11, 30)  # notice window for 2018 closed; final term
