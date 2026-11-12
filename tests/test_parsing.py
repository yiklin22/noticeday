import datetime as dt

from noticeday.gold import UNSCORABLE, parse_date_answer, parse_duration_answer, same_duration
from noticeday.text import Duration, find_dates, find_durations, words_to_int


def test_words_to_int():
    assert words_to_int("one hundred and eighty") == 180
    assert words_to_int("a period of sixty") == 60
    assert words_to_int("twenty-four") == 24
    assert words_to_int("period of") is None


def test_durations_prefer_digits_in_brackets():
    found = [d for d, _, _ in find_durations("ten (10) years; sixty calendar days; 3 months; one-year terms")]
    assert found == [Duration(10, "year"), Duration(60, "day"), Duration(3, "month"), Duration(1, "year")]


def test_dates_in_contract_formats():
    got = [d for d, _, _ in find_dates("this 7th day of September, 1999; Sept. 1, 2001; 12/31/34; 2 March 2010")]
    assert got == [dt.date(1999, 9, 7), dt.date(2001, 9, 1), dt.date(2034, 12, 31), dt.date(2010, 3, 2)]


def test_gold_answers():
    assert parse_date_answer("3/14/20") == dt.date(2020, 3, 14)
    assert parse_date_answer("10/29/99") == dt.date(1999, 10, 29)
    assert parse_date_answer("[]/[]/05") == UNSCORABLE
    assert parse_date_answer("Perpetual") == "perpetual"
    assert parse_date_answer("") is None
    assert parse_duration_answer("successive 1 year") == Duration(1, "year")
    assert parse_duration_answer("2 successive 1 year") == Duration(1, "year")
    assert parse_duration_answer("180 days / 6 months") == (Duration(180, "day"), Duration(6, "month"))
    assert parse_duration_answer("2 years; 3 years") == UNSCORABLE


def test_same_duration_compares_years_as_months():
    assert same_duration(Duration(12, "month"), Duration(1, "year"))
    assert same_duration(Duration(6, "month"), (Duration(180, "day"), Duration(6, "month")))
    assert same_duration(Duration(2, "week"), Duration(14, "day"))
    assert not same_duration(Duration(30, "day"), Duration(1, "month"))
