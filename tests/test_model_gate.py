import datetime as dt

from noticeday.model import parse_json, passages, verify
from noticeday.text import Duration, normalize
from tests.test_extract import CONTRACT

TEXT = normalize(CONTRACT)


def test_verified_values_survive():
    answer = {"effective_date": "2021-03-01", "initial_term": {"n": 2, "unit": "years"},
              "renewal_term": {"n": 1, "unit": "year"}, "auto_renew": True, "notice_period": {"n": 60, "unit": "day"},
              "quotes": {"effective_date": "entered into as of March 1, 2021",
                         "initial_term": "continue for a period of two (2) years",
                         "renewal_term": "automatically renew for successive one (1) year periods",
                         "auto_renew": "shall automatically renew",
                         "notice_period": "at least sixty (60) days prior to the expiration"}}
    values, reasons = verify(answer, TEXT)
    assert reasons == {}
    assert values["effective_date"] == dt.date(2021, 3, 1) and values["notice_period"] == Duration(60, "day")


def test_gate_drops_invented_quotes_and_values_not_in_quote():
    answer = {"notice_period": {"n": 90, "unit": "day"}, "end_date": "2025-01-01", "renewal_term": {"n": 1, "unit": "year"},
              "quotes": {"notice_period": "at least sixty (60) days prior to the expiration",
                         "end_date": "this Agreement ends on January 1, 2025",
                         "renewal_term": None}}
    values, reasons = verify(answer, TEXT)
    assert values == {}
    assert reasons == {"notice_period": "value not in its quote", "end_date": "quote not found in contract",
                       "renewal_term": "quote not found in contract"}


def test_parse_json_and_passages():
    assert parse_json('Here: {"a": 1} done') == {"a": 1}
    assert parse_json("no json") is None
    p = passages(TEXT)
    assert p.startswith("[1] SUPPLY AGREEMENT") and "sixty (60) days" in p
