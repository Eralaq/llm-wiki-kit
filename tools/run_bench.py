#!/usr/bin/env python3
"""Wiki retrieval bench: how many steps does an agent need to reach the right page(s)?

For each question in questions-gold.json it starts a fresh `claude -p` agent whose only tools are Read, Grep and
Glob and whose working folder is a frozen COPY of the wiki (so before/after runs compare the same thing and the
agent cannot wander into the code). Measured from the stream: wiki steps until the first gold page was opened,
whether all gold pages were opened, total tool calls, tokens, cost, time, and the final answer.

Usage:
  run_bench.py --wiki <project> --gold questions.json --snapshot <dir> --out <dir> [--pick 28,32,41 | --split holdout] [--resume] [--search]
The snapshot is created from <wiki>/wiki/*.md and <wiki>/CLAUDE.md only (never raw/, never PM/).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROMPT = (
    "Answer the question below using only this wiki (the current folder). Follow the folder's CLAUDE.md. "
    "Find the pages that matter, read them, and answer briefly in the language of the question. "
    "End with a line 'Pages used:' listing the wiki pages you relied on.\n\nQuestion:\n{q}\n"
)


def make_snapshot(wiki: Path, dest: Path) -> int:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "wiki").mkdir(parents=True)
    n = 0
    for p in (wiki / "wiki").glob("*.md"):
        shutil.copy2(p, dest / "wiki" / p.name)
        n += 1
    if (wiki / "CLAUDE.md").exists():
        shutil.copy2(wiki / "CLAUDE.md", dest / "CLAUDE.md")
    return n


FINDING = (
    "\n## Finding pages\n\n"
    "Before guessing words for grep, run `python tools/wiki_search.py \"<your question, in any language>\"` from the wiki root. "
    "It searches titles, aliases and typical questions and prints the top pages with their Summary line. "
    "Read the best pages next; fall back to grep if nothing fits.\n"
)


def prepare_search(snap: Path, aliases: Path | None) -> None:
    """Idempotent: put the search tool, the alias file and the usage note into the frozen copy."""
    (snap / "tools").mkdir(exist_ok=True)
    shutil.copy2(Path(__file__).with_name("wiki_search.py"), snap / "tools" / "wiki_search.py")
    if aliases:
        shutil.copy2(aliases, snap / "aliases.json")
    md = snap / "CLAUDE.md"
    cur = md.read_text(encoding="utf-8") if md.exists() else ""
    if "## Finding pages" not in cur:
        md.write_text(cur.rstrip() + "\n" + FINDING, encoding="utf-8")


LIMIT_RE = re.compile(r"hit your limit|usage limit|rate limit|5-hour limit|weekly limit|limit reached|resets? at", re.I)
NETWORK_RE = re.compile(r"403|network not allowed|forbidden|ECONNRESET|timed? ?out|overloaded|529|502|503", re.I)
SHOW_RE = re.compile(r"wiki_search\.py\s+(?:-\w+\s+)*--show\s+['\"]?([A-Za-z0-9_.\-]+)")
SHELL_READER = re.compile(r"^\s*(?:cat|head|tail|sed|awk|less|more|bat|nl|type)\b")
WIKI_PATH = re.compile(r"wiki/([A-Za-z0-9_.\-]+?)\.md")


def pages_opened_by_command(cmd: str) -> list[str]:
    """Wiki pages a Bash command prints whole: `wiki_search.py --show X` and cat/head/tail/sed/... on a wiki/X.md path.
    Read-only shell commands run even when the allow-list names only wiki_search (checked 2026-11-07), so they must count."""
    out = [m.removesuffix(".md") for m in SHOW_RE.findall(cmd)]
    for seg in re.split(r"[;&|\n]+", cmd):
        if SHELL_READER.match(seg):
            out += WIKI_PATH.findall(seg.replace("\\", "/"))
    return out


def parse_stream(out: str, stderr: str, gold: list[str]) -> dict:
    """Turn the stream-json of one agent run into measurements. A page counts as opened when the agent used Read on it
    or `wiki_search.py --show <slug>`. `error` is None for a real run, else "limit", "network" or "empty": such a run is
    not a miss and must not be counted in any table."""
    steps, opened, final, usage, cost, is_error, texts = [], [], "", {}, None, False, []
    for line in out.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "assistant":
            for b in (o.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    desc = inp.get("file_path") or inp.get("pattern") or inp.get("command") or inp.get("path") or ""
                    step = {"tool": b.get("name"), "arg": str(desc).replace("\\", "/")[-90:], "opens": []}
                    if b.get("name") == "Read":
                        step["opens"] = [Path(str(inp.get("file_path", ""))).stem]
                    elif b.get("name") == "Bash":
                        step["opens"] = pages_opened_by_command(str(inp.get("command", "")))
                    steps.append(step)
                    opened += step["opens"]
                elif b.get("type") == "text":
                    texts.append(b.get("text", ""))
        elif o.get("type") == "result":
            final = o.get("result") or ""
            usage = o.get("usage") or {}
            cost = o.get("total_cost_usd")
            is_error = bool(o.get("is_error"))
    error = None
    blob = " ".join([final, stderr, " ".join(texts)])
    if LIMIT_RE.search(blob) and (is_error or not steps):
        error = "limit"
    elif not final and not steps:
        error = "network" if (NETWORK_RE.search(stderr) or not out.strip()) else "empty"
    elif is_error and not steps:
        error = "network" if NETWORK_RE.search(blob) else "empty"
    first = next((i + 1 for i, st in enumerate(steps) if any(x in gold for x in st["opens"])), None)
    uniq = list(dict.fromkeys(opened))
    return {"steps": len(steps), "steps_to_first_gold": first,
            "any_gold": any(g in opened for g in gold), "all_gold": all(g in opened for g in gold),
            "junk_pages": [x for x in uniq if x not in gold and x not in ("index", "log", "CLAUDE")],
            "used_search": any(st["tool"] == "Bash" and "wiki_search" in st["arg"] for st in steps),
            "index_first": bool(steps) and steps[0]["tool"] == "Read" and Path(steps[0]["arg"]).stem == "index",
            "opened": opened, "trace": steps, "error": error,
            "tokens_in": (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0),
            "tokens_out": usage.get("output_tokens"), "cost_usd": cost, "answer": final[:1500]}


def run_one(q: dict, snap: Path, model: str, max_turns: int, timeout: int, search: bool = False, shell: bool = False) -> dict:
    """Bash is off in the plain arm. With --search or --shell it is on, and then read-only commands (cat, grep, head) run
    whatever the allow-list says: dontAsk allows them, so the allow-list is not a sandbox. Both arms should get the same
    tools when you compare them: use --shell on the plain arm if the other arm has --search."""
    allowed = "Read,Grep,Glob" + (",Bash(python tools/wiki_search.py:*)" if search else "")
    denied = ("" if (search or shell) else "Bash,") + "Edit,Write,NotebookEdit,WebFetch,WebSearch,Agent"
    cmd = ["claude", "-p", PROMPT.format(q=q["question"]), "--model", model, "--output-format", "stream-json", "--verbose",
           "--allowedTools", allowed, "--disallowedTools", denied,
           "--max-turns", str(max_turns), "--no-session-persistence", "--permission-mode", "dontAsk"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=snap, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out, err = r.stdout, r.stderr[-500:]
    except subprocess.TimeoutExpired as e:
        out, err = (e.stdout or "") if isinstance(e.stdout, str) else "", "timeout"
    res = parse_stream(out, err, q["gold_pages"])
    res.update({"id": q["id"], "gold": q["gold_pages"], "seconds": round(time.time() - t0), "stderr": err})
    return res


def run_with_retry(q: dict, snap: Path, model: str, max_turns: int, timeout: int, search: bool, wait: int = 30, shell: bool = False) -> dict:
    """One retry for a network-type failure (HTTP 403 and similar happen and pass). A usage limit is never retried."""
    r = run_one(q, snap, model, max_turns, timeout, search, shell)
    if r["error"] == "network":
        time.sleep(wait)
        r = run_one(q, snap, model, max_turns, timeout, search, shell)
    return r


def summary_md(model: str, n: int, res: list[dict]) -> str:
    ok = [r for r in res if not r.get("error")]
    L = [f"# Wiki bench: {model}, snapshot of {n} pages", "",
         f"{len(ok)} valid runs, {len(res) - len(ok)} failed runs (failed runs are NOT misses and are left out of every figure).", "",
         "| q | steps | steps to first gold page | gold opened (any/all) | junk pages | index first | tokens in | tokens out | cost $ | sec | error |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['id']} | {r['steps']} | {r['steps_to_first_gold']} | {r['any_gold']}/{r['all_gold']} | {len(r.get('junk_pages', []))} | {r['index_first']} | "
          f"{r['tokens_in']} | {r['tokens_out']} | {r['cost_usd']} | {r['seconds']} | {r.get('error') or ''} |" for r in res]
    if ok:
        L += ["", f"Valid runs: any gold opened {sum(r['any_gold'] for r in ok)}/{len(ok)}, all gold opened {sum(r['all_gold'] for r in ok)}/{len(ok)}, "
              f"mean steps {sum(r['steps'] for r in ok) / len(ok):.1f}, mean junk pages {sum(len(r.get('junk_pages', [])) for r in ok) / len(ok):.1f}."]
    for r in res:
        L += ["", f"## #{r['id']}  gold: {', '.join(r['gold'])}", "", "Trace: " + " > ".join(f"{x['tool']}({x['arg'][-45:]})" for x in r["trace"]),
              "", "Answer: " + r["answer"][:600].replace("\n", " ")]
        if r["stderr"]:
            L.append("stderr: " + r["stderr"].replace("\n", " "))
    return "\n".join(L) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", type=Path, required=True)
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True, help="questions JSON, see bench/README.md")
    ap.add_argument("--pick", help="comma-separated question ids (default: every question of --split)")
    ap.add_argument("--split", choices=["tune", "holdout"], help="only questions of this split")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--max-turns", type=int, default=14)
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--reuse-snapshot", action="store_true")
    ap.add_argument("--resume", action="store_true", help="keep the valid results already in --out/bench.json and run only the rest")
    ap.add_argument("--search", action="store_true", help="give the agent `python tools/wiki_search.py` (the only Bash command allowed); the snapshot gets the tool, the alias file and a short note in its CLAUDE.md")
    ap.add_argument("--shell", action="store_true", help="allow Bash in the plain arm too, so it has the same tools as a --search arm (read-only shell commands only)")
    ap.add_argument("--aliases", type=Path, help="aliases.json for --search (kept outside wiki/)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    n = len(list((a.snapshot / "wiki").glob("*.md"))) if a.reuse_snapshot and a.snapshot.exists() else make_snapshot(a.wiki, a.snapshot)
    if a.search:
        prepare_search(a.snapshot, a.aliases)
    allq = json.loads(a.gold.read_text(encoding="utf-8"))
    qs = {q["id"]: q for q in allq if not a.split or q.get("split", "tune") == a.split}
    ids = [int(x) for x in a.pick.split(",")] if a.pick else list(qs)
    res: list[dict] = []
    bench = a.out / "bench.json"
    if a.resume and bench.exists():
        res = [r for r in json.loads(bench.read_text(encoding="utf-8"))["results"] if not r.get("error")]
        print(f"resume: {len(res)} valid results kept", flush=True)
    done = {r["id"] for r in res}
    code = 0
    for i in ids:
        if i in done:
            continue
        r = run_with_retry(qs[i], a.snapshot, a.model, a.max_turns, a.timeout, a.search, shell=a.shell)
        res.append(r)
        print(f"#{i}: steps={r['steps']} to_gold={r['steps_to_first_gold']} all_gold={r['all_gold']} cost={r['cost_usd']} {r['seconds']}s error={r['error']}", flush=True)
        bench.write_text(json.dumps({"model": a.model, "pages": n, "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
        if r["error"] == "limit":
            print("STOPPED: the usage limit is reached. Partial results are saved; run the same command with --resume after the limit resets.", flush=True)
            code = 3
            break
    (a.out / "bench.md").write_text(summary_md(a.model, n, res), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
