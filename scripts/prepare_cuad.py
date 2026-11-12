"""Build data/cuad/{dev,test}.jsonl from the CUAD v1 release.

Inputs (download first, see README): data/raw/cuad/CUADv1.json and test.json
from github.com/TheAtticusProject/cuad (data.zip), and
data/raw/CUAD_v1/master_clauses.csv from zenodo.org/records/4595826.
Test = CUAD's own 102-contract test split. Dev = the other contracts.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "cuad"
COLUMNS = {
    "agreement_date": "Agreement Date-Answer",
    "effective_date": "Effective Date-Answer",
    "expiration_date": "Expiration Date-Answer",
    "renewal_term": "Renewal Term-Answer",
    "notice_period": "Notice Period To Terminate Renewal- Answer",
}
SPAN_CATEGORIES = ["Effective Date", "Expiration Date", "Renewal Term", "Notice Period To Terminate Renewal"]


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\.pdf$", "", name, flags=re.I).lower())


def main():
    data = json.load(open(RAW / "cuad" / "CUADv1.json"))["data"]
    test_titles = {d["title"] for d in json.load(open(RAW / "cuad" / "test.json"))["data"]}
    rows = {key(r["Filename"]): r for r in csv.DictReader(open(RAW / "CUAD_v1" / "master_clauses.csv", encoding="utf-8-sig"))}
    OUT.mkdir(parents=True, exist_ok=True)
    counts = {"dev": 0, "test": 0, "no_answers": 0}
    files = {s: open(OUT / f"{s}.jsonl", "w") for s in ("dev", "test")}
    for d in data:
        row = rows.get(key(d["title"]))
        if row is None:
            counts["no_answers"] += 1
            continue
        para = d["paragraphs"][0]
        spans = {}
        for qa in para["qas"]:
            cat = qa["id"].split("__")[-1]
            if cat in SPAN_CATEGORIES:
                spans[cat] = [a["text"] for a in qa["answers"]]
        split = "test" if d["title"] in test_titles else "dev"
        rec = {
            "id": d["title"], "split": split, "text": para["context"],
            "gold": {k: row[c].strip() for k, c in COLUMNS.items()},
            "gold_spans": spans,
        }
        files[split].write(json.dumps(rec) + "\n")
        counts[split] += 1
    print(counts)


if __name__ == "__main__":
    main()
