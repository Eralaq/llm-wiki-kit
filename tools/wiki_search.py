#!/usr/bin/env python3
"""wiki_search: field-weighted BM25 over a wiki folder, with an alias/question side file.

Stdlib only, no model, no network. Built for agents that grep a wiki by guessing words: it matches the title,
the slug, aliases and "questions this page answers" (any language) before the body, and prints the top pages
with their Summary line so the agent can pick without opening every page.

  python tools/wiki_search.py "screen jumps with two resolutions" [-n 5] [--wiki DIR] [--aliases FILE]
  python tools/wiki_search.py --show page-slug          # print one page (the bench counts this as opening it)

The side file (aliases.json) lives OUTSIDE wiki/ so wiki pages stay English-only:
  {"page-slug": {"aliases": ["Panther", "Пантера"], "questions": ["why does the screen move", "почему экран прыгает"]}}
Extra keys in an entry (for example "hash", written by gen_aliases.py) are ignored here.

Two experimental switches, both off by default and to be judged with eval_search.py before use:
  --hub-boost X   multiply a page score by 1 + X * ln(1 + inbound links), so overview pages rank above leaf pages
  RU stemming     suffix stripping (stem_ru) is available but NOT the default: on our 9 questions it was not better than the
                  5-letter prefix (stem_prefix). Switch with wiki_search.RU_STEM = wiki_search.stem_ru and compare with eval_search.py
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

W = {"title": 4.0, "alias": 4.0, "question": 3.0, "summary": 2.0, "heading": 1.5, "body": 1.0}
K1, B = 1.2, 0.75
CLOSE = 0.8  # a result within this share of the top score is reported as a close candidate
TOKEN = re.compile(r"[a-zа-яё0-9]+", re.I)
WIKILINK = re.compile(r"\[\[([^\]|#]+)")
STOP = {"the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are", "how", "why", "what", "do", "does", "we", "our", "it", "for", "with",
        "и", "в", "на", "не", "что", "как", "это", "я", "мы", "по", "с", "к", "а", "но", "у", "из", "для", "то", "ли", "бы"}

# Russian endings, longest first. One ending is removed when at least 3 letters remain.
_RU_ENDINGS = sorted("""
ейшими ейшего ейшему ейшей ейшие ировать овать ывать ивать ется ются ится ятся ается иями ями ами ией иях
ыми ими его ого ему ому ешь ишь ете ите ает ают ует уют ила или ило ыла ыли ала али ало ать ять еть ить ыть уть
ий ый ой ая яя ое ее ие ые ых их ую юю ым им ем ом ей ет ут ют ит ат ят ла ли ло ть ся сь ен на ны
ях ах ов ев ие ия ию ии ья ью ам ям
ы и а я у ю о е ь й
""".split(), key=len, reverse=True)


def stem_ru(t: str) -> str:
    """Light Russian normalisation: strip one common ending, keep at least 3 letters."""
    for suf in _RU_ENDINGS:
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def stem_prefix(t: str) -> str:
    """The first version: the first 5 letters survive most endings (kept to compare with stem_ru)."""
    return t[:5]


RU_STEM = stem_prefix  # default = the variant we measured; stem_ru is not better on our 9 questions, see docs/our-findings.md


def stem(t: str) -> str:
    t = t.lower().replace("ё", "е")
    if re.search(r"[а-я]", t):
        return RU_STEM(t)
    for suf in ("ing", "ed", "es", "s"):
        if len(t) > 4 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def toks(text: str) -> list[str]:
    return [stem(t) for t in TOKEN.findall(text) if t.lower() not in STOP and len(t) > 1]


def load(wiki: Path, aliases: dict) -> dict:
    docs = {}
    inbound: Counter = Counter()
    for p in sorted(wiki.glob("*.md")):
        if p.name.startswith("_"):
            continue  # _page-template.md and similar helper files
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        title = next((x[2:].strip() for x in lines if x.startswith("# ")), p.stem)
        m = re.search(r"\*\*Summary\*\*:\s*(.+)", text)
        summary = m.group(1).strip() if m else ""
        heads = " ".join(x.lstrip("# ") for x in lines if x.startswith("#"))
        a = aliases.get(p.stem, {})
        f = {"title": toks(title + " " + p.stem.replace("-", " ")), "alias": toks(" ".join(a.get("aliases", []))),
             "question": toks(" ".join(a.get("questions", []))), "summary": toks(summary), "heading": toks(heads), "body": toks(text)}
        docs[p.stem] = {"f": f, "summary": summary, "title": title}
        for link in {x.strip() for x in WIKILINK.findall(text)}:
            if link != p.stem:
                inbound[link] += 1
    for slug, d in docs.items():
        d["inbound"] = inbound[slug]
    return docs


def search(docs: dict, query: str, n: int = 5, hub_boost: float = 0.0):
    q = toks(query)
    if not q or not docs:
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
            length = len(d["f"][fld])
            for t in set(q):
                if tf[t]:
                    idf = math.log(1 + (N - df[fld][t] + 0.5) / (df[fld][t] + 0.5))
                    s = idf * tf[t] * (K1 + 1) / (tf[t] + K1 * (1 - B + B * length / avg[fld]))
                    score += w * s
                    hit[fld] += 1
        if score > 0:
            if hub_boost:
                score *= 1 + hub_boost * math.log(1 + d.get("inbound", 0))
            out.append((score, slug, ",".join(k for k, _ in hit.most_common(3))))
    out.sort(reverse=True)
    return out[:n]


def show_page(wiki: Path, name: str) -> tuple[int, str]:
    """Return (exit code, text). The name is a slug, never a path."""
    slug = name[:-3] if name.endswith(".md") else name
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", slug) or slug.startswith("."):
        return 2, f"not a page name: {name!r} (use the slug, for example from a search result)"
    p = wiki / f"{slug}.md"
    if not p.is_file():
        near = difflib.get_close_matches(slug, [x.stem for x in wiki.glob("*.md")], n=3)
        return 1, f"no page {slug!r}." + (f" Did you mean: {', '.join(near)}?" if near else "")
    return 0, p.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("-n", type=int, default=5)
    here = Path(__file__).resolve().parent
    root = next((r for r in (here, here.parent, Path.cwd()) if (r / "wiki").is_dir()), here)
    ap.add_argument("--wiki", type=Path, default=root / "wiki")
    ap.add_argument("--aliases", type=Path, default=root / "aliases.json")
    ap.add_argument("--show", metavar="SLUG", help="print one page instead of searching")
    ap.add_argument("--hub-boost", type=float, default=0.0, help="experimental, see the module docstring")
    a = ap.parse_args()
    if a.show:
        code, text = show_page(a.wiki, a.show)
        print(text)
        return code
    if not a.query:
        ap.error("give a query or --show SLUG")
    al = json.loads(a.aliases.read_text(encoding="utf-8")) if a.aliases.exists() else {}
    docs = load(a.wiki, al)
    res = search(docs, a.query, a.n, a.hub_boost)
    if not res:
        print("no match; try other words or a shorter query")
        return 0
    top = res[0][0]
    close = [s for sc, s, _ in res[1:] if sc >= CLOSE * top]
    for score, slug, why in res:
        print(f"{slug}  (score {score:.1f}; matched in: {why})\n    {docs[slug]['summary'][:230]}")
    if close:
        print(f"\nNote: {len(close)} more page(s) score within {round((1 - CLOSE) * 100)}% of the top one ({', '.join(close)}). "
              "The best page is not always first: read the close ones before you answer.")
    print("\nRead a page: python tools/wiki_search.py --show <slug>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
