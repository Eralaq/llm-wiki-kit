"""
mine_sessions.py - find what Claude keeps retyping in past sessions of a project, so it can become a skill + scripts.

  mine_sessions.py MyProject                 # project folder name fragment under ~/.claude/projects (case-insensitive)
  mine_sessions.py MyProject --min 2         # report things seen in >= 2 separate tool calls (default 2)
  mine_sessions.py MyProject --top 15 --out report.md

What it reports (deterministic, no LLM, secrets are masked):
  1. SQL        statements passed to execute() / mysql -e / psql, normalised and counted
  2. LINES      identical code lines repeated across different Bash/Write tool calls (connect boilerplate, SSL setup, ...)
  3. COMMANDS   shell commands with the same first words (ssh host, python -I -X utf8 ..., curl ...)
  4. COST       how many characters of repeated code went through the model - the thing a skill removes

The output is a CANDIDATE list for a human. Nothing is created here; see scaffold_skill.py.
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

BS = chr(92)
SECRET = re.compile(r"(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|PGPASSWORD)\s*[=:]\s*)(['\"]?)[^'\"\s,)]+")
EX = re.compile(
    r'execute\(\s*(?:f?"""(.*?)"""|f?"((?:[^"' + BS + BS + r']|' + BS + BS + r'.)*)"|f?' + "'" + r"((?:[^'" + BS + BS + r']|' + BS + BS + r".)*)')",
    re.S,
)
SHELL_SQL = re.compile(r'(?:mysql|psql)[^\n]*?\s-[ec]\s+(?:"([^"]*)"|' + "'([^']*)')", re.S)
SQL_START = re.compile(r"(?i)^(select|show|describe|desc|explain|with|insert|update|delete|copy)\b")
TRIVIAL_LINE = re.compile(r"^(\s*$|\s*#|\s*import\b|\s*from\b.*\bimport\b|\s*(return|pass|else:|try:|except.*:|finally:|\)|\]|\}|EOF)\s*$|\s*print\(.{0,20}\)\s*$)")


def mask(s):
    return SECRET.sub(lambda m: m.group(1) + m.group(2) + "***", s)


def norm_sql(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\b\d+\b", "N", s)
    return s


def project_dirs(fragment):
    root = os.path.expanduser("~/.claude/projects")
    return [d for d in glob.glob(root + "/*") if fragment.lower() in os.path.basename(d).lower()]


def tool_inputs(dirs):
    """Yield (session_id, tool_name, text) for every code-like tool_use input."""
    for d in dirs:
        for f in sorted(glob.glob(d + "/*.jsonl")):
            sid = os.path.basename(f)[:8]
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    c = (o.get("message") or {}).get("content")
                    if not isinstance(c, list):
                        continue
                    for b in c:
                        if b.get("type") != "tool_use":
                            continue
                        inp = b.get("input") or {}
                        for key in ("command", "content", "new_string"):
                            t = inp.get(key)
                            if isinstance(t, str) and t.strip():
                                yield sid, b.get("name", "?"), t


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", help="fragment of the folder name under ~/.claude/projects, e.g. MyProject")
    ap.add_argument("--min", type=int, default=2, help="minimum number of separate tool calls")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--out", help="also write the report to this file")
    a = ap.parse_args()

    dirs = project_dirs(a.project)
    if not dirs:
        raise SystemExit(f"No folder matching '{a.project}' under ~/.claude/projects")

    sql_calls = defaultdict(set)      # normalised sql -> set of call ids
    sql_raw = {}
    line_calls = defaultdict(set)     # stripped line -> call ids
    cmd_calls = defaultdict(set)      # first words -> call ids
    cmd_example = {}
    chars_total = Counter()
    n_calls = 0

    for sid, name, text in tool_inputs(dirs):
        n_calls += 1
        cid = f"{sid}:{n_calls}"
        for m in list(EX.finditer(text)) + list(SHELL_SQL.finditer(text)):
            s = next(g for g in m.groups() if g)
            if SQL_START.match(s.strip()):
                k = norm_sql(s)
                sql_calls[k].add(cid)
                sql_raw.setdefault(k, mask(re.sub(r"\s+", " ", s).strip()))
        if name == "Bash":
            first = " ".join(text.strip().splitlines()[0].split()[:3])
            first = re.sub(r"^cd\s+\S+\s*&&\s*", "", first)
            if first:
                cmd_calls[first].add(cid)
                cmd_example.setdefault(first, mask(text.strip().splitlines()[0][:160]))
        for ln in set(l.strip() for l in text.splitlines()):
            if len(ln) >= 25 and not TRIVIAL_LINE.match(ln):
                line_calls[ln].add(cid)
                chars_total[ln] += len(ln)

    out = []
    p = out.append
    p(f"# Skill candidates for '{a.project}'  ({n_calls} code-bearing tool calls scanned)\n")

    p("## SQL statements repeated or worth a named report")
    rows = sorted(sql_calls.items(), key=lambda kv: -len(kv[1]))
    for k, ids in rows[: a.top * 2]:
        p(f"- x{len(ids)}  {sql_raw[k][:220]}")
    if not rows:
        p("- none found")

    p("\n## Identical code lines repeated across calls (boilerplate -> belongs in a shared library script)")
    rep = [(l, c) for l, c in line_calls.items() if len(c) >= a.min]
    rep.sort(key=lambda lc: -(len(lc[1]) * len(lc[0])))
    for l, c in rep[: a.top * 2]:
        p(f"- x{len(c)}  {mask(l)[:200]}")
    if not rep:
        p("- none found")

    p("\n## Shell commands that start the same way")
    cm = [(k, c) for k, c in cmd_calls.items() if len(c) >= a.min]
    cm.sort(key=lambda kc: -len(kc[1]))
    for k, c in cm[: a.top]:
        p(f"- x{len(c)}  {cmd_example[k]}")
    if not cm:
        p("- none found")

    wasted = sum(len(l) * (len(c) - 1) for l, c in rep)
    p(f"\n## Cost of the repetition\n- about {wasted} characters (~{wasted // 4} tokens) of repeated lines were generated again after their first use.")
    p("- A skill replaces them with one short script call. Biggest wins first: shared connection library, then named reports, then wrappers for repeated shell commands.")

    text = "\n".join(out)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    main()
