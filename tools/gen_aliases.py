#!/usr/bin/env python3
"""Generate Russian aliases and typical owner questions for every wiki page from the page's OWN text (title, Summary,
headings). Output stays OUTSIDE wiki/ (aliases.generated.json) so wiki pages remain English-only. No bench questions
are used, so there is no leakage. Haiku through `claude -p`, no tools, batches of pages, resumable.

Each entry stores a "hash" of the page text the aliases were made from. A later run regenerates only pages whose hash
changed or is missing, and --prune drops entries of deleted pages.

  gen_aliases.py --wiki WIKI_DIR --out aliases.generated.json            # new and changed pages only
  gen_aliases.py --wiki WIKI_DIR --out aliases.generated.json --check    # report only, no model call (exit 1 if stale)
  gen_aliases.py --wiki WIKI_DIR --out aliases.generated.json --adopt-current
        # stamp today's hash on entries that have none. This ASSERTS that they still describe the pages; use it once,
        # for a file made before hashes existed, only if you know the pages did not change meaningfully since.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROMPT = """You help a Russian-speaking developer find pages in an English-only internal wiki. For each page below write search help in RUSSIAN, as the developer would naturally say it (informal, short, how they talk to a coding assistant).
For every page return:
- "aliases": 4 to 8 Russian words or short phrases: translations of the page's key terms, everyday names and synonyms the developer might use, nicknames only if the page text itself names them. Plain nouns/verbs, no sentences.
- "questions": 3 short Russian questions or complaints this page would answer (what the developer might type when they have this problem or want this thing).
Rules: use ONLY facts in the page info; do not invent names, versions or numbers. Keep technical identifiers (file names, commands, product names) as they are. Output ONLY a JSON object {"<slug>": {"aliases": [...], "questions": [...]}, ...} for all slugs, no prose, no code fence.

PAGES:
"""
SKIP = ("index", "log")
MODEL = "claude-haiku-5-5"


def info(p: Path) -> str:
    t = p.read_text(encoding="utf-8", errors="replace")
    title = next((x[2:].strip() for x in t.splitlines() if x.startswith("# ")), p.stem)
    m = re.search(r"\*\*Summary\*\*:\s*(.+)", t)
    heads = [x.lstrip("# ").strip() for x in t.splitlines() if x.startswith("## ")][:10]
    return f"slug: {p.stem}\ntitle: {title}\nsummary: {(m.group(1) if m else '')[:420]}\nsections: {'; '.join(heads)[:300]}\n"


def page_hash(p: Path) -> str:
    """Hash of exactly the text the model sees (title, Summary, section names), so a body-only edit does not trigger a rerun."""
    return hashlib.sha1(info(p).encode("utf-8")).hexdigest()[:12]


def classify(wiki: Path, res: dict) -> dict:
    """Sort pages into new / changed / unhashed / fresh, and entries into orphaned (no page any more)."""
    pages = {p.stem: p for p in sorted(wiki.glob("*.md")) if p.stem not in SKIP and not p.name.startswith("_")}
    out = {"new": [], "changed": [], "unhashed": [], "fresh": [], "orphaned": sorted(set(res) - set(pages))}
    for slug, p in pages.items():
        entry = res.get(slug)
        if entry is None:
            out["new"].append(slug)
        elif "hash" not in entry:
            out["unhashed"].append(slug)
        elif entry["hash"] != page_hash(p):
            out["changed"].append(slug)
        else:
            out["fresh"].append(slug)
    return out


def run(batch: list[Path]):
    prompt = PROMPT + "\n".join(info(p) for p in batch)
    r = subprocess.run(["claude", "-p", "--model", MODEL, "--tools", "", "--output-format", "text"], input=prompt, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=tempfile.gettempdir(), timeout=300)
    m = re.search(r"\{.*\}", r.stdout, re.S)
    try:
        return json.loads(m.group(0)) if m else {}, r.stdout[:200] if not m else ""
    except ValueError:
        return {}, r.stdout[:200]


def main() -> int:
    global MODEL
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", type=Path, required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--check", action="store_true", help="report new/changed/orphaned entries and stop; no model call")
    ap.add_argument("--prune", action="store_true", help="delete entries whose page no longer exists")
    ap.add_argument("--adopt-current", action="store_true", help="stamp the current hash on entries without one (see the docstring)")
    a = ap.parse_args()
    MODEL = a.model
    res = json.loads(a.out.read_text(encoding="utf-8")) if a.out.exists() else {}
    st = classify(a.wiki, res)
    print("pages: " + ", ".join(f"{k} {len(v)}" for k, v in st.items()))
    if a.check:
        for k in ("new", "changed", "unhashed", "orphaned"):
            if st[k]:
                print(f"  {k}: {', '.join(st[k][:12])}{' ...' if len(st[k]) > 12 else ''}")
        return 1 if (st["new"] or st["changed"] or st["orphaned"]) else 0
    if a.adopt_current:
        for slug in st["unhashed"]:
            res[slug]["hash"] = page_hash(a.wiki / f"{slug}.md")
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"stamped {len(st['unhashed'])} entries")
        return 0
    if a.prune:
        for slug in st["orphaned"]:
            del res[slug]
    todo = st["new"] + st["changed"] + st["unhashed"]
    pages = [a.wiki / f"{s}.md" for s in todo]
    if a.limit:
        pages = pages[: a.limit]
    batches = [pages[i:i + a.batch] for i in range(0, len(pages), a.batch)]
    print(f"{len(pages)} pages in {len(batches)} batches", flush=True)
    bad = 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, (got, err) in enumerate(ex.map(run, batches), 1):
            for k, v in got.items():
                if isinstance(v, dict) and v.get("aliases") is not None and (a.wiki / f"{k}.md").exists():
                    res[k] = {"aliases": v.get("aliases", []), "questions": v.get("questions", []), "hash": page_hash(a.wiki / f"{k}.md")}
            if not got:
                bad += 1
                print("batch failed:", err.replace("\n", " "), flush=True)
            a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            if i % 5 == 0:
                print(f"{i}/{len(batches)} batches, {len(res)} pages", flush=True)
    if not batches:
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {len(res)} pages, {bad} failed batches")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
