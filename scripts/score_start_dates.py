"""Score the rules' start dates against CUAD.

usage: python scripts/score_start_dates.py --split dev

Gold is CUAD's effective date, or its agreement date when there is no
effective date. Partial dates ("[]/[]/2013") are not scored. Prints the
counts and each wrong date with its context.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from noticeday.extract import extract
from noticeday.gold import parse_date_answer

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    args = ap.parse_args()
    tally = Counter()
    for line in open(ROOT / "data" / "cuad" / f"{args.split}.jsonl"):
        rec = json.loads(line)
        g = rec["gold"]
        gold = parse_date_answer(g["effective_date"] or g["agreement_date"])
        if not hasattr(gold, "year"):
            tally["not scored"] += 1
            continue
        ex = extract(rec["text"])
        pred = ex.get("start_date")
        if pred is None:
            tally["not found"] += 1
        elif pred == gold:
            tally["correct"] += 1
        else:
            tally["wrong"] += 1
            f = ex.fields["start_date"]
            context = ex.text[max(0, f.start - 100): f.end + 40].replace("\n", " ")
            print(f"{rec['id'][:60]}  gold {gold}  got {pred} [{f.rule}]\n    {context}")
    scored = tally["correct"] + tally["wrong"] + tally["not found"]
    print(f"\n{args.split}: {tally['correct']} of {scored} right, {tally['wrong']} wrong, "
          f"{tally['not found']} not found, {tally['not scored']} not scored")


if __name__ == "__main__":
    main()
