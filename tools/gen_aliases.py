#!/usr/bin/env python3
"""Generate Russian aliases and typical owner questions for every wiki page from the page's OWN text (title, Summary,
headings). Output stays OUTSIDE wiki/ (aliases.generated.json) so wiki pages remain English-only. No bench questions
are used, so there is no leakage. Haiku through `claude -p`, no tools, batches of pages, resumable.
"""
import argparse, concurrent.futures as cf, json, re, subprocess, sys, tempfile
from pathlib import Path
PROMPT = """You help a Russian-speaking developer find pages in an English-only internal wiki. For each page below write search help in RUSSIAN, as the developer would naturally say it (informal, short, how they talk to a coding assistant).
For every page return:
- "aliases": 4 to 8 Russian words or short phrases: translations of the page's key terms, everyday names and synonyms the developer might use, nicknames only if the page text itself names them. Plain nouns/verbs, no sentences.
- "questions": 3 short Russian questions or complaints this page would answer (what the developer might type when they have this problem or want this thing).
Rules: use ONLY facts in the page info; do not invent names, versions or numbers. Keep technical identifiers (file names, commands, product names) as they are. Output ONLY a JSON object {"<slug>": {"aliases": [...], "questions": [...]}, ...} for all slugs, no prose, no code fence.

PAGES:
"""
def info(p: Path) -> str:
    t = p.read_text(encoding="utf-8", errors="replace")
    title = next((l[2:].strip() for l in t.splitlines() if l.startswith("# ")), p.stem)
    m = re.search(r"\*\*Summary\*\*:\s*(.+)", t)
    heads = [l.lstrip("# ").strip() for l in t.splitlines() if l.startswith("## ")][:10]
    return f"slug: {p.stem}\ntitle: {title}\nsummary: {(m.group(1) if m else '')[:420]}\nsections: {'; '.join(heads)[:300]}\n"
def run(batch):
    prompt = PROMPT + "\n".join(info(p) for p in batch)
    r = subprocess.run(["claude", "-p", "--model", MODEL, "--tools", "", "--output-format", "text"], input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=tempfile.gettempdir(), timeout=300)
    m = re.search(r"\{.*\}", r.stdout, re.S)
    try:
        return json.loads(m.group(0)) if m else {}, r.stdout[:200] if not m else ""
    except ValueError:
        return {}, r.stdout[:200]
MODEL = "claude-haiku-5-5"
ap = argparse.ArgumentParser()
ap.add_argument("--wiki", type=Path, required=True)
ap.add_argument("--model", default="claude-haiku-5-5")
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--batch", type=int, default=8)
ap.add_argument("--workers", type=int, default=3)
ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()
MODEL = a.model
res = json.loads(a.out.read_text(encoding="utf-8")) if a.out.exists() else {}
pages = [p for p in sorted(a.wiki.glob("*.md")) if p.stem not in ("index", "log") and p.stem not in res]
if a.limit: pages = pages[:a.limit]
batches = [pages[i:i + a.batch] for i in range(0, len(pages), a.batch)]
print(f"{len(pages)} pages in {len(batches)} batches", flush=True)
bad = 0
with cf.ThreadPoolExecutor(a.workers) as ex:
    for i, (got, err) in enumerate(ex.map(run, batches), 1):
        for k, v in got.items():
            if isinstance(v, dict) and v.get("aliases") is not None: res[k] = {"aliases": v.get("aliases", []), "questions": v.get("questions", [])}
        if not got: bad += 1; print("batch failed:", err.replace("\n", " "), flush=True)
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        if i % 5 == 0: print(f"{i}/{len(batches)} batches, {len(res)} pages", flush=True)
print(f"done: {len(res)} pages, {bad} failed batches")
