#!/usr/bin/env python3
"""Offline retrieval check (free): rank of the first right page for each gold question. Usage: eval_search.py [--aliases FILE]"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from wiki_search import load, search
ap = argparse.ArgumentParser()
ap.add_argument("--wiki", type=Path, required=True)
ap.add_argument("--aliases", type=Path)
ap.add_argument("--gold", type=Path, required=True, help="questions JSON, see bench/README.md")
a = ap.parse_args()
al = json.loads(a.aliases.read_text(encoding="utf-8")) if a.aliases and a.aliases.exists() else {}
docs = load(a.wiki, al)
gold = json.loads(a.gold.read_text(encoding="utf-8"))
hit1 = hit5 = 0
for q in gold:
    res = [s for _, s, _ in search(docs, q["question"], 50)]
    rank = next((i + 1 for i, s in enumerate(res) if s in q["gold_pages"]), None)
    hit1 += rank == 1; hit5 += bool(rank and rank <= 5)
    print(f"#{q['id']:>2} rank={rank}  top3={res[:3]}")
print(f"top1 {hit1}/{len(gold)}  top5 {hit5}/{len(gold)}")
