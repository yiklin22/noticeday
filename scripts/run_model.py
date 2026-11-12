"""Run the local model over a split and cache its raw answers.

usage: python scripts/run_model.py --split dev --limit 30 [--threads 8]
Set NOTICEDAY_MODEL to a local weights folder if they are not in the HF cache.
Needs: pip install -e '.[model]' and the Qwen/Qwen3-4B-Instruct-2507 weights
in the Hugging Face cache. CPU only; about a minute per contract.
"""
import argparse
import json
import os
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from noticeday.model import CACHE, MODEL_ID, PROMPT, passages  # noqa: E402
from noticeday.text import normalize  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--split", default="dev")
ap.add_argument("--limit", type=int)
ap.add_argument("--threads", type=int, default=8)
args = ap.parse_args()

import torch  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

torch.set_num_threads(args.threads)
tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.bfloat16)
model.eval()

recs = [json.loads(l) for l in open(f"data/cuad/{args.split}.jsonl")]
if args.limit:
    recs = recs[: args.limit]
CACHE.mkdir(parents=True, exist_ok=True)
path = CACHE / f"{args.split}.jsonl"
done = {json.loads(l)["id"] for l in open(path)} if path.exists() else set()
with open(path, "a") as out:
    for i, rec in enumerate(recs):
        if rec["id"] in done:
            continue
        t0 = time.time()
        prompt = PROMPT.format(passages=passages(normalize(rec["text"])))
        msgs = [{"role": "user", "content": prompt}]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        with torch.inference_mode():
            gen = model.generate(**ids, max_new_tokens=450, do_sample=False)
        raw = tok.decode(gen[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
        secs = time.time() - t0
        out.write(json.dumps({"id": rec["id"], "raw": raw, "prompt_tokens": int(ids["input_ids"].shape[1]),
                              "seconds": round(secs, 1)}) + "\n")
        out.flush()
        print(f"{i + 1}/{len(recs)} {secs:.0f}s {ids['input_ids'].shape[1]} tokens", flush=True)
