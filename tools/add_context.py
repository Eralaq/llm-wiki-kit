#!/usr/bin/env python3
"""Add real task context to selected wiki questions. Read-only, stdlib only.

For each selected question (index into questions-clean.json) finds the transcript and writes:
session opening, the 2 user prompts before, the last assistant words before, what the agent said at the end of
this task, and the files it changed. Output: questions-with-context.md. Snippets are redacted.

Usage: add_context.py --clean results/X/questions-clean.json --pick 3,4,5 --out results/X/questions-with-context.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wiki_miner import PREAMBLE, blocks, redact  # noqa: E402

NOISE = re.compile(r"^\s*(<task-notification|<system-reminder|\[SYSTEM|Base directory for this skill|<pasted_content|CONTEXT_LIMIT)")


def load(path: Path):
    ev = []
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("isSidechain"):
            continue
        ev.append(o)
    return ev


def user_text(o):
    bl = blocks(o.get("message"))
    if any(b.get("type") == "tool_result" for b in bl):
        return None
    t = " ".join(b.get("text", "") for b in bl if b.get("type") == "text").strip()
    return PREAMBLE.sub("", t) if t and not NOISE.match(t) else None


LOCAL = re.compile(r"^\s*(<local-command|<command-name|Caveat:|\[Image|\[Request interrupted|\[Earlier usage-limit|/\w+\s*$)")
SUMMARY = re.compile(r"^\s*This session is being continued")


def real_prompt(ev, idx):
    """Return (text, idx) of the real task: skips interrupts, takes the request out of a compaction summary."""
    t = user_text(ev[idx])
    if t.lstrip().startswith("[Request interrupted"):
        for j in range(idx + 1, len(ev)):
            u = ev[j].get("type") == "user" and user_text(ev[j])
            if u and not LOCAL.match(u) and not SUMMARY.match(u):
                return u, j
        return t, idx
    if SUMMARY.match(t):
        m = re.search(r"Primary Request and Intent:?\s*(.{60,1400})", t, re.S)
        if m:
            body = re.split(r"\s(?:2\.\s+Key Technical|##\s*2\b|2\.\s+[A-Z])", m.group(1))[0]
            return "(from the compaction summary, may be a recap of earlier work) " + body[:700], idx
    return t, idx


def asst_text(o):
    return " ".join(b.get("text", "") for b in blocks(o.get("message")) if b.get("type") == "text").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", type=Path, required=True)
    ap.add_argument("--pick", required=True, help="1-based numbers from questions-candidates.md")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--src", type=Path, default=Path.home() / ".claude" / "projects")
    a = ap.parse_args()
    clean = json.loads(a.clean.read_text(encoding="utf-8"))
    files = {}
    for p in a.src.glob("*/*.jsonl"):
        files.setdefault(p.stem[:8], []).append(p)
    L = ["# Wiki questions with real task context", ""]
    for n in [int(x) for x in a.pick.split(",")]:
        q = clean[n - 1]
        L += [f"## {n}. [{q['ts'][:10]}, session {q['session']}]", ""]
        path = next((p for p in files.get(q["session"], []) if any((e.get("timestamp") or "")[:16] == q["ts"] for e in load(p))), None)
        if not path:
            L += ["(transcript not found)", ""]
            continue
        ev = load(path)
        idx = next((i for i, e in enumerate(ev) if e.get("type") == "user" and (e.get("timestamp") or "")[:16] == q["ts"] and user_text(e)), None)
        if idx is None:
            L += ["(prompt not found)", ""]
            continue
        qtext, idx = real_prompt(ev, idx)
        prompts = [(i, user_text(e)) for i, e in enumerate(ev[:idx]) if e.get("type") == "user" and user_text(e) and not LOCAL.match(user_text(e)) and not SUMMARY.match(user_text(e))]
        before = ev[:idx]
        last_a = next((asst_text(e) for e in reversed(before) if e.get("type") == "assistant" and asst_text(e)), "")
        after, nxt = [], len(ev)
        for i in range(idx + 1, len(ev)):
            if ev[i].get("type") == "user" and user_text(ev[i]):
                nxt = i
                break
        after = ev[idx + 1:nxt]
        final = next((asst_text(e) for e in reversed(after) if e.get("type") == "assistant" and asst_text(e)), "")
        changed = []
        for e in after:
            if e.get("type") != "assistant":
                continue
            for b in blocks(e.get("message")):
                if b.get("type") == "tool_use" and b.get("name") in ("Edit", "Write", "NotebookEdit"):
                    fp = str((b.get("input") or {}).get("file_path", "")).replace("\\", "/")
                    if fp and fp not in changed:
                        changed.append(fp)
        L += [f"- **Session opened with:** {redact(prompts[0][1], 320) if prompts else '(this was the first prompt, or the session was continued after /compact)'}"]
        for _, t in prompts[-2:] if len(prompts) > 1 else []:
            L.append(f"- **Earlier prompt:** {redact(t, 260)}")
        if last_a:
            L.append(f"- **Agent had just said:** {redact(last_a, 300)}")
        L += [f"- **Question:** {redact(qtext, 600)}",
              f"- **Gold pages (opened by the agent):** {', '.join(q['gold_pages'])}",
              f"- **How the task ended (agent's last words):** {redact(final, 420) or '(no text answer)'}",
              f"- **Files changed in this task:** {', '.join(c.rsplit('/', 2)[-2] + '/' + c.rsplit('/', 1)[-1] for c in changed[:8]) or 'none'}", ""]
    a.out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
