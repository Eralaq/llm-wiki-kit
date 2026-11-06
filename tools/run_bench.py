#!/usr/bin/env python3
"""Wiki retrieval bench: how many steps does an agent need to reach the right page(s)?

For each question in questions-gold.json it starts a fresh `claude -p` agent whose only tools are Read, Grep and
Glob and whose working folder is a frozen COPY of the wiki (so before/after runs compare the same thing and the
agent cannot wander into the code). Measured from the stream: wiki steps until the first gold page was opened,
whether all gold pages were opened, total tool calls, tokens, cost, time, and the final answer.

Usage:
  run_bench.py --wiki Z:/Coding/Tanuki/tanuki-wiki --snapshot <dir> --out <dir> --pick 28,32,41 [--model claude-haiku-5-5]
The snapshot is created from <wiki>/wiki/*.md and <wiki>/CLAUDE.md only (never raw/, never PM/).
"""
from __future__ import annotations

import argparse
import json
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


def run_one(q: dict, snap: Path, model: str, max_turns: int, timeout: int, search: bool = False) -> dict:
    allowed = "Read,Grep,Glob" + (",Bash(python tools/wiki_search.py:*)" if search else "")
    denied = ("" if search else "Bash,") + "Edit,Write,NotebookEdit,WebFetch,WebSearch,Agent"
    cmd = ["claude", "-p", PROMPT.format(q=q["question"]), "--model", model, "--output-format", "stream-json", "--verbose",
           "--allowedTools", allowed, "--disallowedTools", denied,
           "--max-turns", str(max_turns), "--no-session-persistence", "--permission-mode", "dontAsk"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=snap, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out, err = r.stdout, r.stderr[-500:]
    except subprocess.TimeoutExpired as e:
        out, err = (e.stdout or "") if isinstance(e.stdout, str) else "", "timeout"
    steps, opened, final, usage, cost = [], [], "", {}, None
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
                    steps.append({"tool": b.get("name"), "arg": str(desc).replace("\\", "/")[-90:]})
                    if b.get("name") == "Read":
                        opened.append(Path(str(inp.get("file_path", ""))).stem)
        elif o.get("type") == "result":
            final = o.get("result") or ""
            usage = o.get("usage") or {}
            cost = o.get("total_cost_usd")
    gold = q["gold_pages"]
    first = next((i + 1 for i, s in enumerate(steps) if s["tool"] == "Read" and Path(s["arg"]).stem in gold), None)
    return {"id": q["id"], "gold": gold, "steps": len(steps), "steps_to_first_gold": first,
            "any_gold": any(g in opened for g in gold), "all_gold": all(g in opened for g in gold),
            "used_search": any(s["tool"] == "Bash" and "wiki_search" in s["arg"] for s in steps), "index_first": bool(steps) and steps[0]["tool"] == "Read" and Path(steps[0]["arg"]).stem == "index",
            "opened": opened, "trace": steps, "seconds": round(time.time() - t0), "cost_usd": cost,
            "tokens_in": (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0),
            "tokens_out": usage.get("output_tokens"), "answer": final[:1500], "stderr": err}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", type=Path, required=True)
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True, help="questions JSON, see bench/README.md")
    ap.add_argument("--pick", required=True)
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--max-turns", type=int, default=14)
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--reuse-snapshot", action="store_true")
    ap.add_argument("--search", action="store_true", help="give the agent `python tools/wiki_search.py` (the only Bash command allowed); the snapshot gets the tool, the alias file and a short note in its CLAUDE.md")
    ap.add_argument("--aliases", type=Path, help="aliases.json for --search (kept outside wiki/)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    n = len(list((a.snapshot / "wiki").glob("*.md"))) if a.reuse_snapshot and a.snapshot.exists() else make_snapshot(a.wiki, a.snapshot)
    if a.search:
        prepare_search(a.snapshot, a.aliases)
    qs = {q["id"]: q for q in json.loads(a.gold.read_text(encoding="utf-8"))}
    res = []
    for i in [int(x) for x in a.pick.split(",")]:
        r = run_one(qs[i], a.snapshot, a.model, a.max_turns, a.timeout, a.search)
        res.append(r)
        print(f"#{i}: steps={r['steps']} to_gold={r['steps_to_first_gold']} all_gold={r['all_gold']} cost={r['cost_usd']} {r['seconds']}s", flush=True)
        (a.out / "bench.json").write_text(json.dumps({"model": a.model, "pages": n, "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"# Wiki bench: {a.model}, snapshot of {n} pages", "",
         "| q | steps | steps to first gold page | all gold opened | index first | tokens in | tokens out | cost $ | sec |", "|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['id']} | {r['steps']} | {r['steps_to_first_gold']} | {r['all_gold']} | {r['index_first']} | {r['tokens_in']} | {r['tokens_out']} | {r['cost_usd']} | {r['seconds']} |" for r in res]
    for r in res:
        L += ["", f"## #{r['id']}  gold: {', '.join(r['gold'])}", "", "Trace: " + " > ".join(f"{s['tool']}({s['arg'][-45:]})" for s in r["trace"]), "", "Answer: " + r["answer"][:600].replace("\n", " ")]
        if r["stderr"]:
            L.append("stderr: " + r["stderr"].replace("\n", " "))
    (a.out / "bench.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
