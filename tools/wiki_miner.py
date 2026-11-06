#!/usr/bin/env python3
"""Wiki miner: how do agents actually move through a wiki? Read-only, stdlib only, no model calls.

Input: Claude Code transcripts (~/.claude/projects/*/*.jsonl) and one wiki folder.
Output: <out>/report.md and <out>/wiki.json with signals that point at wiki changes:
  - searches inside the wiki that found nothing        -> missing article / missing words in an article
  - pages read together in the same question           -> missing link or pages to merge
  - big pages read again and again, often in pieces    -> split or add a short summary at the top
  - pages never read / pages nobody links to           -> orphan, dead, or hidden
  - index.md not read first / raw/ read instead of wiki -> index does not lead to the answer
  - questions that took many wiki steps                -> hard-to-find answers (look at the question text)
A finding counts as a candidate only if it repeats in >= --min-sessions distinct sessions
(default 3), as in session-miner. Snippets pass through redact().

Usage: wiki_miner.py --wiki <project>/wiki --out <dir> [--src <projects dir> ...]
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import re
import sys
from pathlib import Path

SECRET = [
    (re.compile(r"(?i)\b(sk|pk|ghp|gho|xox[bap]|AKIA|glpat)[-_A-Za-z0-9]{16,}"), "[key]"),
    (re.compile(r"(?i)(api[_-]?key|token|secret|passw(or)?d|authorization|bearer)\s*[:=]?\s*['\"]?[A-Za-z0-9._\-/+=]{8,}"), r"\1=[redacted]"),
    (re.compile(r"\b[A-Za-z0-9+/_-]{32,}={0,2}\b"), "[blob]"),
    (re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b"), "[ip]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
]
MISS = re.compile(r"(?i)^\s*(no (files|matches) found|no results)")
LINK = re.compile(r"\[\[([^\]|#]+)")
PREAMBLE = re.compile(r"^\s*\[(Telegram|Transcript of a voice note)[^\]]*\]\s*")
GREPLIKE = re.compile(r"\b(grep|rg|ripgrep|findstr|Select-String)\b")


def redact(text: str, limit: int = 140) -> str:
    t = " ".join(str(text).split())
    for rx, rep in SECRET:
        t = rx.sub(rep, t)
    return t[:limit]


def norm(p: str) -> str:
    return str(p).replace("\\", "/").lower()


def blocks(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def result_text(b) -> str:
    c = b.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return ""


class Wiki:
    def __init__(self, root: Path):
        root = root.resolve()  # a relative path such as "wiki" has no parent name and would match every wiki
        self.root = root
        self.key = norm(root.parent.name + "/" + root.name) + "/"  # e.g. myproject/wiki/
        self.pages = {p.stem: p for p in sorted(root.glob("*.md")) if not p.name.startswith("_")}
        self.size = {n: p.stat().st_size for n, p in self.pages.items()}
        self.inbound = collections.Counter()
        for n, p in self.pages.items():
            for m in set(LINK.findall(p.read_text(encoding="utf-8", errors="replace"))):
                tgt = m.strip()
                if tgt != n:
                    self.inbound[tgt] += 1

    def page_of(self, path: str) -> str | None:
        q = norm(path)
        i = q.find(self.key)
        if i < 0:
            return None
        rest = q[i + len(self.key):]
        return rest[:-3] if rest.endswith(".md") and "/" not in rest else (rest or "<dir>")

    def raw_of(self, path: str) -> bool:
        q = norm(path)
        return q.find(self.key.replace("/wiki/", "/raw/")) >= 0

    def touches(self, path: str) -> bool:
        return self.page_of(path) is not None or self.raw_of(path)


def mine(path: Path, wiki: Wiki) -> dict | None:
    s = {"id": path.stem, "project": path.parent.name, "episodes": [], "wiki_calls": 0}
    pending: dict[str, dict] = {}
    cur = None

    def close():
        nonlocal cur
        if cur and cur["steps"]:
            s["episodes"].append(cur)
        cur = None

    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("isSidechain"):
            continue
        kind, msg = o.get("type"), o.get("message") or {}
        if kind == "user":
            bl = blocks(msg)
            for b in bl:
                if b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    st = pending.pop(b["tool_use_id"])
                    st["miss"] = bool(MISS.match(result_text(b))) or not result_text(b).strip()
            texts = [b.get("text", "") for b in bl if b.get("type") == "text"]
            if texts and not any(b.get("type") == "tool_result" for b in bl):
                close()
                full = PREAMBLE.sub("", " ".join(texts))
                cur = {"q": redact(full, 160), "q_long": redact(full, 400), "ts": (o.get("timestamp") or "")[:16], "steps": []}
        elif kind == "assistant" and cur is not None:
            for b in blocks(msg):
                if b.get("type") != "tool_use":
                    continue
                name, inp = b.get("name", ""), b.get("input") or {}
                st = None
                if name == "Read" and wiki.touches(inp.get("file_path", "")):
                    pg = wiki.page_of(inp["file_path"])
                    st = {"op": "read" if pg else "raw", "page": pg or norm(inp["file_path"]).rsplit("/", 1)[-1],
                          "partial": bool(inp.get("offset") or inp.get("limit"))}
                elif name in ("Grep", "Glob") and (wiki.touches(inp.get("path", "")) or wiki.key.rstrip("/") in norm(inp.get("pattern", "") + inp.get("glob", ""))):
                    st = {"op": name.lower(), "pattern": redact(inp.get("pattern", ""), 80)}
                elif name == "Bash" and wiki.key in norm(inp.get("command", "")) and GREPLIKE.search(inp.get("command", "")):
                    st = {"op": "bashgrep", "pattern": redact(inp.get("command", ""), 100)}
                if st:
                    pending[b.get("id", "")] = st
                    cur["steps"].append(st)
                    s["wiki_calls"] += 1
    close()
    return s if s["wiki_calls"] else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", type=Path, required=True, help="the wiki/ folder, e.g. /path/to/project/wiki")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--src", type=Path, nargs="*", default=[Path.home() / ".claude" / "projects"])
    ap.add_argument("--min-sessions", type=int, default=3)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    wiki = Wiki(a.wiki)
    files = []
    for src in a.src:
        direct = list(src.glob("*.jsonl"))
        files += direct or list(src.glob("*/*.jsonl"))
    sessions = [m for p in sorted(set(files)) if (m := mine(p, wiki))]

    reads_by_sess = collections.defaultdict(lambda: collections.Counter())
    miss_sess = collections.defaultdict(set)
    miss_n = collections.Counter()
    pair_sess = collections.defaultdict(set)
    partial = collections.defaultdict(set)
    noindex, rawread, eps_total, steps_hist = set(), collections.Counter(), 0, []
    hard = []
    for s in sessions:
        sid = s["id"][:8]
        for ep in s["episodes"]:
            eps_total += 1
            ops = ep["steps"]
            pages = [x["page"] for x in ops if x["op"] == "read" and x["page"] not in ("<dir>",)]
            for x in ops:
                if x["op"] == "read":
                    reads_by_sess[x["page"]][sid] += 1
                    if x["partial"]:
                        partial[x["page"]].add(sid)
                if x["op"] == "raw":
                    rawread[x["page"]] += 1
                if x["op"] in ("grep", "glob", "bashgrep") and x.get("miss"):
                    miss_sess[x["pattern"]].add(sid)
                    miss_n[x["pattern"]] += 1
            for p, q in itertools.combinations(sorted(set(pages)), 2):
                if "index" not in (p, q) and "log" not in (p, q):
                    pair_sess[(p, q)].add(sid)
            if pages and pages[0] != "index" and len(pages) >= 3:
                noindex.add(sid)
            steps_hist.append(len(ops))
            if len(ops) >= 8:
                hard.append((len(ops), sid, ep["q"]))

    ge = lambda d: sorted(((k, len(v)) for k, v in d.items() if len(v) >= a.min_sessions), key=lambda r: -r[1])
    readcount = collections.Counter({k: sum(c.values()) for k, c in reads_by_sess.items()})
    big = sorted(wiki.size.values())[len(wiki.size) * 9 // 10] if wiki.size else 0
    never = sorted(n for n in wiki.pages if n not in readcount and n not in ("index", "log"))
    orphans = sorted(n for n in wiki.pages if wiki.inbound[n] == 0 and n not in ("index", "log"))

    L = [f"# Wiki miner report: {a.wiki.parent.name}", "",
         f"{len(wiki.pages)} wiki pages. {len(sessions)} sessions touched this wiki, {eps_total} questions (user prompt to next prompt) with wiki calls. Candidate rule: repeats in >= {a.min_sessions} sessions (a page-level count below that is shown only where noted).", "",
         f"- Median wiki calls per question: {sorted(steps_hist)[len(steps_hist)//2] if steps_hist else 0}; questions with 8+ wiki calls: {len(hard)}.",
         f"- Sessions that read 3+ pages without opening index.md first: {len(noindex)}.",
         f"- Reads of raw/ files (agent went around the wiki): {sum(rawread.values())} across {len(rawread)} files.", "",
         "## Searches in the wiki that found nothing (candidates: missing article or missing words)", "",
         "| sessions | times | search |", "|---|---|---|"]
    L += [f"| {n} | {miss_n[k]} | `{k}` |" for k, n in ge(miss_sess)[:25]] or ["| - | - | none reached the threshold |"]
    L += ["", "Misses seen in 1-2 sessions (weaker, top 12):", ""] + [f"- {len(v)} sessions: `{k}`" for k, v in sorted(miss_sess.items(), key=lambda r: -len(r[1])) if len(v) < a.min_sessions][:12]
    L += ["", "## Pages read together in the same question (candidates: add [[links]] between them, or merge)", "",
          "| sessions | page A | page B | already linked? |", "|---|---|---|---|"]
    def linked(p, q):
        def has(x, y):
            f = wiki.pages.get(x)
            return bool(f) and f"[[{y}" in f.read_text(encoding="utf-8", errors="replace")
        return "yes" if has(p, q) or has(q, p) else "NO"
    pr = sorted(((k, len(v)) for k, v in pair_sess.items() if len(v) >= a.min_sessions), key=lambda r: -r[1])[:25]
    L += [f"| {n} | `{p}` | `{q}` | {linked(p, q)} |" for (p, q), n in pr] or ["| - | none | | |"]
    L += ["", "## Big pages read again and again (candidates: split, or short summary on top)", "",
          f"Size threshold = top 10% of pages ({big} bytes).", "", "| sessions | reads | partial-read sessions | bytes | page |", "|---|---|---|---|---|"]
    bp = sorted(((n, len(reads_by_sess[n]), readcount[n], len(partial[n])) for n in readcount if wiki.size.get(n, 0) >= big and len(reads_by_sess[n]) >= a.min_sessions), key=lambda r: -r[2])[:15]
    L += [f"| {s_} | {r} | {pp} | {wiki.size.get(n, 0)} | `{n}` |" for n, s_, r, pp in bp] or ["| - | - | - | - | none |"]
    L += ["", "## Most read pages (what agents really use)", "", "| reads | sessions | page |", "|---|---|---|"]
    L += [f"| {c} | {len(reads_by_sess[n])} | `{n}` |" for n, c in readcount.most_common(15)]
    L += ["", "## Pages nobody read in the analysed sessions", "", ", ".join(f"`{n}`" for n in never) or "none",
          "", f"## Pages with no inbound [[link]] ({len(orphans)})", "", ", ".join(f"`{n}`" for n in orphans) or "none",
          "", "## Hardest questions (8+ wiki calls) with their first words", ""]
    L += [f"- {n} calls, session {sid}: {q}" for n, sid, q in sorted(hard, reverse=True)[:15]] or ["- none"]
    L += ["", "## Raw files read instead of wiki pages", ""] + [f"- {n} x `{k}`" for k, n in rawread.most_common(12)]
    # Question set: real prompts whose answer needed wiki pages; gold = wiki pages the agent opened (in order).
    qs = []
    for s in sessions:
        for ep in s["episodes"]:
            gold = []
            for x in ep["steps"]:
                if x["op"] == "read" and x["page"] not in ("index", "log", "<dir>") and x["page"] not in gold:
                    gold.append(x["page"])
            if not gold or len(ep["q"]) < 25:
                continue
            qs.append({"session": s["id"][:8], "ts": ep["ts"], "question": ep["q_long"], "gold_pages": gold,
                       "wiki_calls": len(ep["steps"]), "searches": [x["pattern"] for x in ep["steps"] if x["op"] != "read" and x.get("pattern")][:5]})
    qs.sort(key=lambda r: r["ts"], reverse=True)
    (a.out / "questions.json").write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (a.out / "wiki.json").write_text(json.dumps({"sessions": len(sessions), "questions": eps_total, "reads": dict(readcount), "never_read": never, "orphans": orphans}, indent=1), encoding="utf-8")
    print(f"{len(sessions)} sessions, {eps_total} questions -> {a.out}/report.md; misses {len(ge(miss_sess))}, pairs {len(pr)}, big pages {len(bp)}, never read {len(never)}, orphans {len(orphans)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
