"""Load a few CUAD dev-split contracts into a fresh demo database.

usage: python scripts/seed_demo.py demo.db
Picks contracts where the rules found an automatic renewal, plus two where
they found no renewal, so the dashboard shows each status.
"""
import json
import re
import sys
from pathlib import Path

from noticeday.store import Store

ROOT = Path(__file__).resolve().parents[1]
path = Path(sys.argv[1] if len(sys.argv) > 1 else "demo.db")
path.unlink(missing_ok=True)
store = Store(path)
renewing, other = [], []
for line in open(ROOT / "data" / "cuad" / "dev.jsonl"):
    rec = json.loads(line)
    name = re.sub(r"_", " ", rec["id"].split("-")[-1]).strip().title() + " (" + rec["id"].split("_")[0][:28] + ")"
    if rec["gold"]["notice_period"] and len(renewing) < 6:
        renewing.append((name, rec["text"]))
    elif not rec["gold"]["renewal_term"] and rec["gold"]["expiration_date"][:1].isdigit() and len(other) < 2:
        other.append((name, rec["text"]))
for name, text in renewing + other:
    store.add(name, text)
print(f"loaded {len(renewing) + len(other)} contracts into {path}")
