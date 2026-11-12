import importlib

import pytest
from fastapi.testclient import TestClient

from tests.test_extract import CONTRACT


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTICEDAY_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("NOTICEDAY_TODAY", "2026-11-13")
    import noticeday.app as appmod
    importlib.reload(appmod)
    return TestClient(appmod.app)


def test_upload_review_confirm_calendar(client):
    r = client.post("/contracts", data={"name": "Supply – A Co", "text": CONTRACT}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    # Term 2021-03-01 + 2y = 2023-03-01, rolled yearly to 2027-03-01; 60 days earlier.
    assert "Send notice by" in page and "2026-12-31" in page and "<mark>sixty (60) days</mark>" in page
    assert "BEGIN:VEVENT" not in client.get("/calendar.ics").text  # not confirmed yet
    form = {"start_date": "2021-03-01", "end_date": "", "term_n": "2", "term_unit": "year", "renewal_n": "1",
            "renewal_unit": "year", "auto_renew": "on", "notice_n": "60", "notice_unit": "day",
            "reviewer": "Sam", "action": "confirm"}
    client.post("/contracts/1", data=form)
    ics = client.get("/calendar.ics").text
    assert "DTSTART;VALUE=DATE:20261231" in ics and "TRIGGER:-P14D" in ics
    form.update(notice_n="90", action="save")
    client.post("/contracts/1", data=form)
    assert "BEGIN:VEVENT" not in client.get("/calendar.ics").text  # edit clears confirmation
    assert "2026-12-01" in client.get("/contracts/1").text


def test_rejects_bad_uploads(client):
    assert client.post("/contracts", data={"text": "  "}).status_code == 400
    assert client.post("/contracts", files={"file": ("x.docx", b"abc")}).status_code == 415
    client.post("/contracts", data={"text": CONTRACT})
    assert client.post("/contracts/1", data={"start_date": "13/01/2020"}).status_code == 400
    client.post("/contracts/1/delete")
    assert client.get("/contracts/1").status_code == 404


def test_second_reader_flags_disagreement(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTICEDAY_DB", str(tmp_path / "s.db"))
    monkeypatch.setenv("NOTICEDAY_TODAY", "2026-11-13")
    monkeypatch.setenv("NOTICEDAY_MODEL", "fake")
    import noticeday.app as appmod
    import noticeday.model as model
    importlib.reload(appmod)
    # The model says 90 days and quotes words that are not in the contract:
    # the gate drops it, so notice shows as "found nothing it could back".
    # It also gives a renewal of 2 years quoted from text that says one year: dropped.
    raw = ('{"effective_date": "2021-03-01", "initial_term": {"n": 3, "unit": "year"}, "notice_period": {"n": 90, "unit": "day"},'
           ' "quotes": {"effective_date": "entered into as of March 1, 2021", "initial_term": "continue for a period of two (2) years",'
           ' "notice_period": "ninety days before expiry"}}')
    monkeypatch.setattr(appmod, "READER", lambda text: model.second_reading(text, raw=raw))
    c = TestClient(appmod.app)
    c.post("/contracts", data={"name": "A", "text": CONTRACT})
    appmod.worker.shutdown(wait=True)
    page = c.get("/contracts/1").text
    assert page.count("Second reader agrees.") == 1           # start date
    assert "value not in its quote" in page                    # 3-year term dropped
    assert "quote not found in contract" in page               # 90 days dropped
    assert "0 disagree" in c.get("/").text


def test_failed_reader_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTICEDAY_DB", str(tmp_path / "f.db"))
    monkeypatch.setenv("NOTICEDAY_MODEL", "fake")
    import noticeday.app as appmod
    importlib.reload(appmod)

    def boom(text):
        raise MemoryError("not enough RAM")
    monkeypatch.setattr(appmod, "READER", boom)
    c = TestClient(appmod.app)
    c.post("/contracts", data={"text": CONTRACT})
    appmod.worker.shutdown(wait=True)
    assert "Second reader failed: MemoryError: not enough RAM" in c.get("/contracts/1").text


def test_notice_letter_only_after_confirmation(client):
    client.post("/contracts", data={"name": "Supply – A Co", "text": CONTRACT})
    assert client.get("/contracts/1/letter").status_code == 409
    client.post("/contracts/1", data={"start_date": "2021-03-01", "term_n": "2", "term_unit": "year", "renewal_n": "1",
                                      "renewal_unit": "year", "auto_renew": "on", "notice_n": "60", "notice_unit": "day",
                                      "reviewer": "Sam", "action": "confirm"})
    assert "Draft a non-renewal notice" in client.get("/contracts/1").text
    page = client.get("/contracts/1/letter", params={"company": "B Co", "counterparty": "A Co"}).text
    assert "the current term ends on 1 March 2027" in page
    assert "at least 60 days before the end of the term" in page and "before the 31 December 2026 deadline" in page
    assert "sixty (60) days" in page  # the clause is shown for checking
