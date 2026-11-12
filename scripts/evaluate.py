"""Score predicted term facts against CUAD's lawyer answers.

usage: python scripts/evaluate.py --split dev [--method rules|model|hybrid]

Writes docs/results/<split>-<method>.json and .md, and a per-contract error
list to .cache/eval/<split>-<method>-errors.jsonl.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from noticeday.deadlines import initial_term_end, shift
from noticeday.gold import UNSCORABLE, parse_date_answer, parse_duration_answer, same_duration
from noticeday.predict import load_predictions
from noticeday.text import Duration

ROOT = Path(__file__).resolve().parents[1]


def outcome(pred, gold, same):
    """correct / wrong / missed / false_alarm / true_empty / unscorable."""
    if gold == UNSCORABLE:
        return "unscorable"
    if gold is None:
        return "true_empty" if pred is None else "false_alarm"
    if pred is None:
        return "missed"
    return "correct" if same(pred, gold) else "wrong"


def same_value(p, g):
    return p == g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--method", default="rules")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    recs = [json.loads(l) for l in open(ROOT / "data" / "cuad" / f"{args.split}.jsonl")]
    if args.limit:
        recs = recs[: args.limit]
    preds = load_predictions(recs, args.method)
    tallies = {k: Counter() for k in ("expiration", "renewal", "notice", "deadline")}
    errors = []
    for rec in recs:
        p = preds[rec["id"]]
        g = rec["gold"]
        g_exp = parse_date_answer(g["expiration_date"])
        g_ren = parse_duration_answer(g["renewal_term"])
        g_not = parse_duration_answer(g["notice_period"])
        p_exp = initial_term_end(p["start_date"], p["end_date"], p["term"])
        res = {
            "expiration": outcome(p_exp, g_exp, same_value),
            "renewal": outcome(p["renewal"], g_ren if g_ren != "perpetual" else UNSCORABLE, same_duration),
            "notice": outcome(p["notice"], g_not if g_not != "perpetual" else UNSCORABLE, same_duration),
        }
        # End to end: the last day to give notice of non-renewal.
        if hasattr(g_exp, "year") and isinstance(g_not, Duration):
            gold_dl = shift(g_exp, g_not, -1)
            if hasattr(p_exp, "year") and p["notice"] is not None:
                pred_dl = shift(p_exp, p["notice"], -1)
                res["deadline"] = "correct" if pred_dl == gold_dl else "wrong"
            else:
                res["deadline"] = "flagged"  # incomplete: the app asks a person
        for k, v in res.items():
            tallies[k][v] += 1
        if any(v in ("wrong", "missed", "false_alarm", "flagged") for v in res.values()):
            errors.append({"id": rec["id"], "res": res, "gold": g,
                           "pred": {k: str(v) if v is not None else None for k, v in p.items() if k != "evidence"},
                           "evidence": p.get("evidence", {})})
    summary = {"split": args.split, "method": args.method, "contracts": len(recs),
               "tallies": {k: dict(v) for k, v in tallies.items()}}
    out = ROOT / "docs" / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.split}-{args.method}.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [f"# {args.split} split, {args.method}: {len(recs)} contracts", "",
             "| field | correct | wrong | missed | false alarm | true empty | flagged | unscorable | accuracy where gold has a value |",
             "|---|---|---|---|---|---|---|---|---|"]
    for k, c in tallies.items():
        scored = c["correct"] + c["wrong"] + c["missed"] + c["flagged"]
        acc = f"{c['correct'] / scored:.1%} ({c['correct']}/{scored})" if scored else "n/a"
        lines.append(f"| {k} | {c['correct']} | {c['wrong']} | {c['missed']} | {c['false_alarm']} | {c['true_empty']} | {c['flagged']} | {c['unscorable']} | {acc} |")
    (out / f"{args.split}-{args.method}.md").write_text("\n".join(lines) + "\n")
    cache = ROOT / ".cache" / "eval"
    cache.mkdir(parents=True, exist_ok=True)
    with open(cache / f"{args.split}-{args.method}-errors.jsonl", "w") as f:
        for e in errors:
            f.write(json.dumps(e) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
