"""SQLite storage. One row per contract: its text, what the rules extracted,
the current values (edited by a person), and who confirmed them."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from .extract import FIELDS, extract
from .text import Duration

SCHEMA = """
create table if not exists contracts (
  id integer primary key,
  name text not null,
  uploaded_at text not null,
  text text not null,
  extracted text not null,      -- json: field -> {value, start, end, rule}
  current text not null,        -- json: field -> value (after edits)
  confirmed_at text,
  confirmed_by text
);
"""


def to_json(name, v):
    if v is None:
        return None
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, Duration):
        return f"{v.n} {v.unit}"
    return v


def from_json(name, v):
    if v is None or v == "":
        return None
    if name in ("start_date", "end_date"):
        return "perpetual" if v == "perpetual" else dt.date.fromisoformat(v)
    if name in ("term", "renewal", "notice"):
        n, unit = v.split()
        return Duration(int(n), unit)
    return v


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def add(self, name: str, raw_text: str) -> int:
        ex = extract(raw_text)
        extracted = {k: {"value": to_json(k, f.value), "start": f.start, "end": f.end, "rule": f.rule}
                     for k, f in ex.fields.items()}
        current = {k: extracted.get(k, {}).get("value") for k in FIELDS}
        cur = self.db.execute(
            "insert into contracts (name, uploaded_at, text, extracted, current) values (?, ?, ?, ?, ?)",
            (name, dt.datetime.now().isoformat(timespec="seconds"), ex.text, json.dumps(extracted), json.dumps(current)))
        self.db.commit()
        return cur.lastrowid

    def get(self, cid: int):
        r = self.db.execute("select * from contracts where id = ?", (cid,)).fetchone()
        return self._row(r) if r else None

    def all(self):
        return [self._row(r) for r in self.db.execute("select * from contracts order by id")]

    def update(self, cid: int, current: dict, confirmed_by: str | None):
        self.db.execute(
            "update contracts set current = ?, confirmed_at = ?, confirmed_by = ? where id = ?",
            (json.dumps({k: to_json(k, current.get(k)) for k in FIELDS}),
             dt.datetime.now().isoformat(timespec="seconds") if confirmed_by else None, confirmed_by, cid))
        self.db.commit()

    def delete(self, cid: int):
        self.db.execute("delete from contracts where id = ?", (cid,))
        self.db.commit()

    @staticmethod
    def _row(r):
        d = dict(r)
        d["extracted"] = json.loads(d["extracted"])
        d["values"] = {k: from_json(k, v) for k, v in json.loads(d["current"]).items()}
        return d
