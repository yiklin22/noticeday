"""Turn an extraction method's output into the plain values the scorer uses."""
from __future__ import annotations

from .extract import extract


def rules_prediction(text: str) -> dict:
    ex = extract(text)
    return {
        "start_date": ex.get("start_date"), "end_date": ex.get("end_date"), "term": ex.get("term"),
        "renewal": ex.get("renewal"), "auto_renew": ex.get("auto_renew"), "notice": ex.get("notice"),
        "evidence": {k: ex.quote(k, 60) for k in ex.fields},
    }


def load_predictions(recs: list[dict], method: str) -> dict:
    if method == "rules":
        return {r["id"]: rules_prediction(r["text"]) for r in recs}
    from .model import load_model_predictions
    return load_model_predictions(recs, method)
