#!/usr/bin/env python3
"""Offline retrieval check (free, no model): how well does wiki_search rank the right pages for the gold questions?

Per question: rank of the first gold page. Over the set, for k in 1, 3, 5:
  hit@k     share of questions with at least one gold page in the top k
  recall@k  share of ALL gold pages of a question found in the top k, averaged
  junk@k    average number of non-gold pages in the top k (what an agent has to wade through)
Use --split to keep tuning and final checks apart (see bench/README.md): questions carry "split": "tune" or "holdout".

  eval_search.py --wiki WIKI_DIR --gold bench/questions.json [--aliases FILE] [--split tune|holdout]
                 [--hub-boost X] [--stem prefix|suffix] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wiki_search  # noqa: E402

KS = (1, 3, 5)


def evaluate(docs: dict, gold: list[dict], hub_boost: float = 0.0) -> dict:
    rows = []
    for q in gold:
        res = [s for _, s, _ in wiki_search.search(docs, q["question"], 50, hub_boost)]
        gp = set(q["gold_pages"])
        row = {"id": q["id"], "split": q.get("split", "tune"), "top3": res[:3],
               "rank": next((i + 1 for i, s in enumerate(res) if s in gp), None)}
        for k in KS:
            top = res[:k]
            row[f"hit@{k}"] = bool(gp & set(top))
            row[f"recall@{k}"] = len(gp & set(top)) / len(gp)
            row[f"junk@{k}"] = len([s for s in top if s not in gp])
        rows.append(row)
    n = len(rows) or 1
    summary = {"questions": len(rows)}
    for k in KS:
        summary[f"hit@{k}"] = sum(r[f"hit@{k}"] for r in rows) / n
        summary[f"recall@{k}"] = sum(r[f"recall@{k}"] for r in rows) / n
        summary[f"junk@{k}"] = sum(r[f"junk@{k}"] for r in rows) / n
    return {"summary": summary, "rows": rows}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", type=Path, required=True)
    ap.add_argument("--aliases", type=Path)
    ap.add_argument("--gold", type=Path, required=True, help="questions JSON, see bench/README.md")
    ap.add_argument("--split", choices=["tune", "holdout"], help="only questions of this split (default: all)")
    ap.add_argument("--hub-boost", type=float, default=0.0)
    ap.add_argument("--stem", choices=["prefix", "suffix"], default="prefix", help="Russian stemmer: the 5-letter prefix (default) or suffix stripping")
    ap.add_argument("--json", type=Path, help="also write the full result here")
    a = ap.parse_args()
    wiki_search.RU_STEM = wiki_search.stem_ru if a.stem == "suffix" else wiki_search.stem_prefix
    al = json.loads(a.aliases.read_text(encoding="utf-8")) if a.aliases and a.aliases.exists() else {}
    docs = wiki_search.load(a.wiki, al)
    gold = json.loads(a.gold.read_text(encoding="utf-8"))
    if a.split:
        gold = [q for q in gold if q.get("split", "tune") == a.split]
    out = evaluate(docs, gold, a.hub_boost)
    for r in out["rows"]:
        print(f"#{r['id']:>2} [{r['split']}] rank={r['rank']}  top3={r['top3']}")
    s = out["summary"]
    print(f"\n{s['questions']} questions")
    for k in KS:
        print(f"top{k}: hit {s[f'hit@{k}']:.2f}  recall {s[f'recall@{k}']:.2f}  junk {s[f'junk@{k}']:.1f}")
    if a.json:
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
