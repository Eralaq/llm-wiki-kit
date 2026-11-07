#!/usr/bin/env python3
"""wiki_lint: structural health check of a wiki folder. Stdlib only, no model, read-only.

Errors (exit code 1):
  missing-field    page lacks **Summary**, **Sources** or **Last updated** (the page format in template/CLAUDE.md)
  broken-link      [[page]] or (page.md) points to a page that does not exist
  index-dangling   index.md lists a page that does not exist
Warnings (exit code 1 only with --strict):
  not-in-index     page is not listed in index.md
  orphan           no other page links to it
  no-related       no "## Related pages" section
  bad-date         Last updated is not YYYY-MM-DD or lies in the future
  stale            Last updated is older than --stale-days (only when the option is given)
  dup-title        two pages share a title
  stub             body shorter than --min-chars (default 200)
  non-english      Cyrillic text (only with --english-only, for wikis whose rules say English only)

  wiki_lint.py --wiki WIKI_DIR [--strict] [--stale-days N] [--english-only] [--json OUT]

It checks structure, not truth: it cannot tell that a page is wrong, only that it is malformed, unreachable or old.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

WIKILINK = re.compile(r"\[\[([^\]|#]+)")
MDLINK = re.compile(r"\]\(([^)#\s]+?)\.md(?:#[^)]*)?\)")
FIELD = {"Summary": re.compile(r"^\*\*Summary\*\*:\s*\S", re.M), "Sources": re.compile(r"^\*\*Sources\*\*:\s*\S", re.M),
         "Last updated": re.compile(r"^\*\*Last updated\*\*:\s*\S", re.M)}
DATE = re.compile(r"^\*\*Last updated\*\*:\s*(\S+)", re.M)
SPECIAL = {"index", "log"}


CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def targets(text: str) -> set[str]:
    """Link targets outside code: `[[page-name]]` written as an example inside backticks is not a link."""
    text = CODE.sub("", text)
    out = {x.strip() for x in WIKILINK.findall(text)}
    out |= {Path(x).name for x in MDLINK.findall(text) if "://" not in x}
    return out


def lint(wiki: Path, stale_days: int | None = None, english_only: bool = False, min_chars: int = 200, today: datetime.date | None = None) -> list[dict]:
    today = today or datetime.date.today()
    files = {p.stem: p for p in sorted(wiki.glob("*.md")) if not p.name.startswith("_")}
    pages = {k: v for k, v in files.items() if k not in SPECIAL}
    text = {k: v.read_text(encoding="utf-8", errors="replace") for k, v in files.items()}
    issues: list[dict] = []

    def add(level: str, kind: str, page: str, msg: str) -> None:
        issues.append({"level": level, "kind": kind, "page": page, "message": msg})

    inbound: dict[str, set[str]] = defaultdict(set)
    for slug, t in text.items():
        for tgt in targets(t):
            if tgt in pages and tgt != slug:
                inbound[tgt].add(slug)
            elif tgt not in files and slug != "log":  # the log may mention renamed or removed pages
                add("error", "index-dangling" if slug == "index" else "broken-link", slug, f"links to missing page '{tgt}'")
    in_index = targets(text["index"]) if "index" in text else set()
    titles: Counter = Counter()
    for slug in pages:
        t = text[slug]
        for name, rx in FIELD.items():
            if not rx.search(t):
                add("error", "missing-field", slug, f"no **{name}** line")
        if "## Related pages" not in t:
            add("warning", "no-related", slug, "no '## Related pages' section")
        if "index" in text and slug not in in_index:
            add("warning", "not-in-index", slug, "not listed in index.md")
        if not (inbound[slug] - SPECIAL):
            add("warning", "orphan", slug, "no other page links to it")
        m = DATE.search(t)
        if m:
            try:
                d = datetime.date.fromisoformat(m.group(1))
                if d > today:
                    add("warning", "bad-date", slug, f"Last updated {d} is in the future")
                elif stale_days is not None and (today - d).days > stale_days:
                    add("warning", "stale", slug, f"last updated {d}, {(today - d).days} days ago")
            except ValueError:
                add("warning", "bad-date", slug, f"Last updated '{m.group(1)}' is not YYYY-MM-DD")
        title = next((x[2:].strip() for x in t.splitlines() if x.startswith("# ")), slug)
        titles[title.lower()] += 1
        body = t.split("\n---", 1)[-1]
        if len(body.strip()) < min_chars:
            add("warning", "stub", slug, f"body is {len(body.strip())} characters")
        if english_only and re.search(r"[а-яё]", t, re.I):
            add("warning", "non-english", slug, "contains Cyrillic text")
    for slug in pages:
        title = next((x[2:].strip() for x in text[slug].splitlines() if x.startswith("# ")), slug)
        if titles[title.lower()] > 1:
            add("warning", "dup-title", slug, f"title '{title}' is used by {titles[title.lower()]} pages")
    return issues


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", type=Path, required=True)
    ap.add_argument("--strict", action="store_true", help="warnings also give exit code 1")
    ap.add_argument("--stale-days", type=int)
    ap.add_argument("--english-only", action="store_true")
    ap.add_argument("--min-chars", type=int, default=200)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    issues = lint(a.wiki, a.stale_days, a.english_only, a.min_chars)
    n_pages = len([p for p in a.wiki.glob("*.md") if not p.name.startswith("_") and p.stem not in SPECIAL])
    for lvl in ("error", "warning"):
        for i in issues:
            if i["level"] == lvl:
                print(f"{lvl:7} {i['kind']:14} {i['page']}: {i['message']}")
    by = Counter((i["level"], i["kind"]) for i in issues)
    errors = sum(v for (lv, _), v in by.items() if lv == "error")
    warns = sum(v for (lv, _), v in by.items() if lv == "warning")
    print(f"\n{n_pages} pages, {errors} errors, {warns} warnings" + ("" if not by else "  (" + ", ".join(f"{k}: {v}" for (_, k), v in sorted(by.items())) + ")"))
    if a.json:
        a.json.write_text(json.dumps({"pages": n_pages, "issues": issues}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if errors or (a.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
