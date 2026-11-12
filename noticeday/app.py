"""Review app: upload a contract, check each value against its clause,
confirm, and export confirmed notice deadlines as a calendar file.

Run: NOTICEDAY_DB=noticeday.db uvicorn noticeday.app:app --port 8830
"""
from __future__ import annotations

import datetime as dt
import io
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .deadlines import schedule
from .extract import FIELDS
from .store import Store, from_json
from .text import Duration

MAX_BYTES = 5 * 1024 * 1024
LABELS = {
    "start_date": "Start / effective date", "end_date": "Initial term ends",
    "term": "Initial term length", "renewal": "Renewal length",
    "auto_renew": "Renews automatically", "notice": "Notice to stop renewal",
}
STATUS_TEXT = {
    "act_by": "Send notice by", "renews_no_notice": "Renews; notice period not found",
    "expires": "Expires", "expired": "Expired", "no_fixed_end": "No fixed end",
    "incomplete": "Needs facts",
}

app = FastAPI(title="noticeday")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
store = Store(os.environ.get("NOTICEDAY_DB", "noticeday.db"))


def today() -> dt.date:
    t = os.environ.get("NOTICEDAY_TODAY")
    return dt.date.fromisoformat(t) if t else dt.date.today()


def ics_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def plan(c):
    v = c["values"]
    return schedule(v["start_date"], v["end_date"], v["term"], v["renewal"], bool(v["auto_renew"]), v["notice"], today())


def pdf_text(data: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    rows = []
    for c in store.all():
        s = plan(c)
        days = (s.act_by - today()).days if s.act_by else None
        rows.append({"c": c, "s": s, "days": days, "status": STATUS_TEXT[s.status]})
    rows.sort(key=lambda r: (r["s"].act_by is None, r["s"].act_by or dt.date.max))
    unconfirmed = sum(1 for r in rows if not r["c"]["confirmed_at"] and r["s"].act_by)
    return templates.TemplateResponse(request, "index.html", {"rows": rows, "today": today(), "unconfirmed": unconfirmed})


@app.post("/contracts")
async def upload(file: UploadFile | None = File(None), name: str = Form(""), text: str = Form("")):
    if file is not None and file.filename:
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "File is over 5 MB.")
        if file.filename.lower().endswith(".pdf"):
            text = pdf_text(data)
        elif file.filename.lower().endswith(".txt"):
            text = data.decode("utf-8", errors="replace")
        else:
            raise HTTPException(415, "Upload a .pdf or .txt file.")
        name = name or file.filename
    if not text.strip():
        raise HTTPException(400, "No contract text found. Scanned PDFs need OCR first.")
    cid = store.add(name.strip() or "Untitled contract", text)
    return RedirectResponse(f"/contracts/{cid}", status_code=303)


@app.get("/contracts/{cid}", response_class=HTMLResponse)
def show(request: Request, cid: int):
    c = store.get(cid)
    if not c:
        raise HTTPException(404)
    fields = []
    for k in FIELDS:
        ex = c["extracted"].get(k)
        quote = None
        if ex:
            a, b = ex["start"], ex["end"]
            quote = (c["text"][max(0, a - 220):a], c["text"][a:b], c["text"][b:b + 220])
        value = c["values"][k]
        fields.append({"key": k, "label": LABELS[k], "value": value, "found": ex is not None,
                       "edited": ex is not None and str(from_json(k, ex["value"])) != str(value) or ex is None and value is not None,
                       "rule": ex["rule"] if ex else None, "quote": quote,
                       "n": value.n if isinstance(value, Duration) else "",
                       "unit": value.unit if isinstance(value, Duration) else "year"})
    return templates.TemplateResponse(request, "contract.html", {"c": c, "fields": fields, "s": plan(c),
                                                                 "status": STATUS_TEXT[plan(c).status], "today": today()})


@app.post("/contracts/{cid}")
async def save(request: Request, cid: int):
    c = store.get(cid)
    if not c:
        raise HTTPException(404)
    form = await request.form()
    values = {}
    try:
        for k in ("start_date", "end_date"):
            raw = form.get(k, "").strip()
            values[k] = "perpetual" if raw.lower() == "perpetual" else (dt.date.fromisoformat(raw) if raw else None)
        for k in ("term", "renewal", "notice"):
            n = form.get(f"{k}_n", "").strip()
            values[k] = Duration(int(n), form.get(f"{k}_unit", "day")) if n else None
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD (or 'perpetual' for the end); lengths must be whole numbers.")
    values["auto_renew"] = form.get("auto_renew") == "on"
    reviewer = form.get("reviewer", "").strip()
    store.update(cid, values, reviewer if form.get("action") == "confirm" and reviewer else None)
    return RedirectResponse(f"/contracts/{cid}", status_code=303)


@app.post("/contracts/{cid}/delete")
def delete(cid: int):
    store.delete(cid)
    return RedirectResponse("/", status_code=303)


@app.get("/calendar.ics")
def calendar():
    """Only confirmed contracts go on the calendar."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//noticeday//EN", "CALSCALE:GREGORIAN"]
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    for c in store.all():
        s = plan(c)
        if not c["confirmed_at"] or not s.act_by:
            continue
        day = s.act_by.strftime("%Y%m%d")
        summary = ics_text(f"{STATUS_TEXT[s.status]}: {c['name']}")
        lines += ["BEGIN:VEVENT", f"UID:noticeday-{c['id']}-{day}", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{day}", f"SUMMARY:{summary}",
                  "DESCRIPTION:" + ics_text(f"{s.reason} Term ends {s.term_end}. Confirmed by {c['confirmed_by']}."),
                  "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Contract notice deadline in 14 days", "TRIGGER:-P14D", "END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="notice-deadlines.ics"'})
