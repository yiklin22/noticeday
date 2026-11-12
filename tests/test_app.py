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
