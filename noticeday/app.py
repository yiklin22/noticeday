"""Review app: upload a contract, check each value against its clause,
confirm, and export confirmed notice deadlines as a calendar file.

Run: NOTICEDAY_DB=noticeday.db uvicorn noticeday.app:app --port 8830
"""
from __future__ import annotations

import datetime as dt
import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .deadlines import schedule
from .extract import FIELDS
from .gold import same_duration
from .store import Store, from_json
from .text import Duration

MAX_BYTES = 5 * 1024 * 1024
LABELS = {
    "start_date": "Start / effective date", "end_date": "Initial term ends",
    "term": "Initial term length", "renewal": "Renewal length",
    "auto_renew": "Renews automatically", "notice": "Notice to stop renewal",
    "renewal_limit": "Number of renewals allowed",
}
STATUS_TEXT = {
    "act_by": "Send notice by", "renews_no_notice": "Renews; notice period not found",
    "expires": "Expires", "expired": "Expired", "no_fixed_end": "No fixed end",
    "incomplete": "Needs facts",
}

app = FastAPI(title="noticeday")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
store = Store(os.environ.get("NOTICEDAY_DB", "noticeday.db"))
# Second reader: the local model, on only when NOTICEDAY_MODEL names its
# weights. One worker, because one model already uses 8 GB and 8 threads.
READER = None
if os.environ.get("NOTICEDAY_MODEL"):
    from .model import second_reading as READER
worker = ThreadPoolExecutor(max_workers=1)


def read_again(cid: int):
    c = store.get(cid)
    try:
        reading = READER(c["text"])
    except Exception as e:  # report on the page instead of losing it in a thread
        reading = {"status": "failed", "error": f"{type(e).__name__}: {e}", "values": {}, "dropped": {}, "quotes": {}}
    store.set_second(cid, reading)


def compare(c):
    """Per field: agree / disagree / only_one / none, against the second reading."""
    sec = c["second"]
    if not sec or sec.get("status") != "done":
        return None
    out = {}
    for k in FIELDS:
        if k == "renewal_limit":  # the model is not asked for it
            continue
        mine, theirs = c["values"][k], sec["values"].get(k)
        if isinstance(mine, Duration) and isinstance(theirs, Duration):
            out[k] = "agree" if same_duration(mine, theirs) else "disagree"
        elif mine is None and theirs is None:
            out[k] = "none"
        elif mine is None or theirs is None:
            out[k] = "only_one"
        else:
            out[k] = "agree" if str(mine) == str(theirs) else "disagree"
    return out


def today() -> dt.date:
    t = os.environ.get("NOTICEDAY_TODAY")
    return dt.date.fromisoformat(t) if t else dt.date.today()


def ics_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def plan(c):
    v = c["values"]
    return schedule(v["start_date"], v["end_date"], v["term"], v["renewal"], bool(v["auto_renew"]), v["notice"], today(),
                    renewal_limit=v["renewal_limit"])


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
        cmp = compare(c)
        rows.append({"c": c, "s": s, "days": days, "status": STATUS_TEXT[s.status],
                     "second": None if READER is None and not c["second"] else
                     ("reading…" if not c["second"] else
                      c["second"]["status"] if not cmp else
                      f"{sum(v == 'disagree' for v in cmp.values())} disagree")})
    rows.sort(key=lambda r: (r["s"].act_by is None, r["s"].act_by or dt.date.max))
    unconfirmed = sum(1 for r in rows if not r["c"]["confirmed_at"] and r["s"].act_by)
    return templates.TemplateResponse(request, "index.html", {"rows": rows, "today": today(), "unconfirmed": unconfirmed,
                                                              "second_on": READER is not None or any(r["second"] for r in rows)})


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
    if READER is not None:
        worker.submit(read_again, cid)
    return RedirectResponse(f"/contracts/{cid}", status_code=303)


@app.get("/contracts/{cid}", response_class=HTMLResponse)
def show(request: Request, cid: int):
    c = store.get(cid)
    if not c:
        raise HTTPException(404)
    cmp = compare(c) or {}
    sec = c["second"] or {}
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
                       "unit": value.unit if isinstance(value, Duration) else "year",
                       "cmp": cmp.get(k), "second": (sec.get("values") or {}).get(k),
                       "second_quote": (sec.get("quotes") or {}).get(k), "dropped": (sec.get("dropped") or {}).get(k)})
    return templates.TemplateResponse(request, "contract.html", {"c": c, "fields": fields, "s": plan(c),
                                                                 "status": STATUS_TEXT[plan(c).status], "today": today(),
                                                                 "sec": c["second"], "reader_on": READER is not None})


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
    try:
        limit = form.get("renewal_limit", "").strip()
        values["renewal_limit"] = int(limit) if limit else None
    except ValueError:
        raise HTTPException(400, "Number of renewals must be a whole number, or empty for no limit.")
    reviewer = form.get("reviewer", "").strip()
    store.update(cid, values, reviewer if form.get("action") == "confirm" and reviewer else None)
    return RedirectResponse(f"/contracts/{cid}", status_code=303)


@app.get("/contracts/{cid}/letter", response_class=HTMLResponse)
def letter(request: Request, cid: int, company: str = "", counterparty: str = "", signer: str = ""):
    """Draft a non-renewal notice from confirmed values. Nothing is sent."""
    c = store.get(cid)
    if not c:
        raise HTTPException(404)
    s = plan(c)
    if not c["confirmed_at"]:
        raise HTTPException(409, "Confirm the contract's values before drafting a notice.")
    if s.status not in ("act_by", "renews_no_notice"):
        raise HTTPException(409, "This contract does not renew automatically, so there is nothing to stop.")
    ex = c["extracted"].get("notice")
    clause = c["text"][max(0, ex["start"] - 300): ex["end"] + 300] if ex else None
    return templates.TemplateResponse(request, "letter.html", {
        "c": c, "s": s, "today": today(), "late": s.act_by < today(), "clause": clause,
        "company": company, "counterparty": counterparty, "signer": signer,
        "start": c["values"]["start_date"], "notice": c["values"]["notice"]})


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
