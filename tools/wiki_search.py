#!/usr/bin/env python3
"""wiki_search: field-weighted BM25 over a wiki folder, with an alias/question side file.

Stdlib only, no model, no network. Built for agents that grep a wiki by guessing words: it matches the title,
the slug, aliases and "questions this page answers" (any language) before the body, and prints the top pages
with their Summary line so the agent can pick without opening every page.

  python tools/wiki_search.py "screen jumps with two resolutions" [-n 5] [--wiki DIR] [--aliases FILE]

The side file (aliases.json) lives OUTSIDE wiki/ so wiki pages stay English-only:
  {"page-slug": {"aliases": ["Panther", "Пантера"], "questions": ["why does the screen move", "почему экран прыгает"]}}
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

W = {"title": 4.0, "alias": 4.0, "question": 3.0, "summary": 2.0, "heading": 1.5, "body": 1.0}
K1, B = 1.2, 0.75
TOKEN = re.compile(r"[a-zа-яё0-9]+", re.I)
STOP = {"the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are", "how", "why", "what", "do", "does", "we", "our", "it", "for", "with",
        "и", "в", "на", "не", "что", "как", "это", "я", "мы", "по", "с", "к", "а", "но", "у", "из", "для", "то", "ли", "бы"}


def stem(t: str) -> str:
    t = t.lower().replace("ё", "е")
    if re.search(r"[а-я]", t):
        return t[:5]  # crude Russian stemmer: prefix of 5 letters survives most endings
    for suf in ("ing", "ed", "es", "s"):
        if len(t) > 4 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def toks(text: str) -> list[str]:
    return [stem(t) for t in TOKEN.findall(text) if t.lower() not in STOP and len(t) > 1]


def load(wiki: Path, aliases: dict) -> dict:
    docs = {}
    for p in sorted(wiki.glob("*.md")):
        if p.name.startswith("_"):
            continue  # _page-template.md and similar helper files
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        title = next((l[2:].strip() for l in lines if l.startswith("# ")), p.stem)
        m = re.search(r"\*\*Summary\*\*:\s*(.+)", text)
        summary = m.group(1).strip() if m else ""
        heads = " ".join(l.lstrip("# ") for l in lines if l.startswith("#"))
        a = aliases.get(p.stem, {})
        f = {"title": toks(title + " " + p.stem.replace("-", " ")), "alias": toks(" ".join(a.get("aliases", []))),
             "question": toks(" ".join(a.get("questions", []))), "summary": toks(summary), "heading": toks(heads), "body": toks(text)}
        docs[p.stem] = {"f": f, "summary": summary, "title": title}
    return docs


def search(docs: dict, query: str, n: int = 5):
    q = toks(query)
    if not q:
        return []
    N = len(docs)
    avg = {fld: (sum(len(d["f"][fld]) for d in docs.values()) / N) or 1 for fld in W}
    df = {fld: Counter() for fld in W}
    for d in docs.values():
        for fld in W:
            for t in set(d["f"][fld]):
                df[fld][t] += 1
    out = []
    for slug, d in docs.items():
        score, hit = 0.0, Counter()
        for fld, w in W.items():
            tf = Counter(d["f"][fld])
            L = len(d["f"][fld])
            for t in set(q):
                if tf[t]:
                    idf = math.log(1 + (N - df[fld][t] + 0.5) / (df[fld][t] + 0.5))
                    s = idf * tf[t] * (K1 + 1) / (tf[t] + K1 * (1 - B + B * L / avg[fld]))
                    score += w * s
                    hit[fld] += 1
        if score > 0:
            out.append((score, slug, ",".join(k for k, _ in hit.most_common(3))))
    out.sort(reverse=True)
    return out[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-n", type=int, default=5)
    here = Path(__file__).resolve().parent
    root = next((r for r in (here, here.parent, Path.cwd()) if (r / "wiki").is_dir()), here)
    ap.add_argument("--wiki", type=Path, default=root / "wiki")
    ap.add_argument("--aliases", type=Path, default=root / "aliases.json")
    a = ap.parse_args()
    al = json.loads(a.aliases.read_text(encoding="utf-8")) if a.aliases.exists() else {}
    docs = load(a.wiki, al)
    res = search(docs, a.query, a.n)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not res:
        print("no match; try other words or a shorter query")
        return 0
    for score, slug, why in res:
        print(f"{slug}  (score {score:.1f}; matched in: {why})\n    {docs[slug]['summary'][:230]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
