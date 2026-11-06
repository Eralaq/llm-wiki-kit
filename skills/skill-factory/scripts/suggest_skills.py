"""
suggest_skills.py - "these commands were typed 3+ times in this session - make a skill?"  No model calls, no network.

  suggest_skills.py --transcript FILE.jsonl      # print candidates of one session
  suggest_skills.py --hook                       # for a SessionEnd/Stop hook: reads the hook JSON on stdin, prints nothing,
                                                 # appends the candidates to ~/.claude/skill-factory/proposals.md (once per session)
  suggest_skills.py --pending                    # show proposals not yet handled
  suggest_skills.py --clear                      # forget them (after you built a skill or decided not to)

A candidate is a command shape (quoted text, numbers and paths collapsed) run at least --min times (default 3) in one session.
Commands that already call a skill script (/.claude/skills/) and plain reading commands (ls, cat, git, grep, ...) are skipped.
Secrets are masked. Nothing is created: building the skill stays the pipeline in SKILL.md (mine, design, stage, test, install).
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
PROPOSALS = HOME / ".claude" / "skill-factory" / "proposals.md"
GENERIC = re.compile(r"^(cd|ls|cat|echo|pwd|git|head|tail|wc|true|which|export|mkdir|rm|cp|mv|sed -n|grep|rg|find|sleep|test)\b")
SECRET = re.compile(r"(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|authorization|bearer)\s*[=:]?\s*)(['\"]?)[^'\"\s,)]{6,}")


BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")


def mask(text):
    text = BEARER.sub(lambda m: m.group(1) + " ***", text)
    return SECRET.sub(lambda m: m.group(1) + m.group(2) + "***", text)


def skeleton(cmd):
    cmd = re.sub(r"^\s*cd\s+\S+\s*(&&|;)\s*", "", cmd.strip())
    lines = [ln.strip() for ln in cmd.splitlines() if ln.strip()][:3]
    s = " | ".join(lines)
    s = re.sub(r"\"[^\"]*\"|'[^']*'", "S", s)
    s = re.sub(r"[A-Za-z]:\\[^\s]+|/[\w./~-]{3,}", "P", s)
    s = re.sub(r"\b\d+\b", "N", s)
    s = " ".join(s.split())[:120]
    return "" if len(s) < 14 or GENERIC.match(s) else s


def candidates(path, minimum=3):
    shapes, sample = Counter(), {}
    for line in Path(path).open(encoding="utf-8", errors="replace"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("isSidechain"):
            continue
        content = (o.get("message") or {}).get("content")
        for b in content if isinstance(content, list) else []:
            if b.get("type") == "tool_use" and b.get("name") == "Bash":
                cmd = str((b.get("input") or {}).get("command", ""))
                if "/.claude/skills/" in cmd:
                    continue
                sk = skeleton(cmd)
                if sk:
                    shapes[sk] += 1
                    sample.setdefault(sk, mask(" ".join(cmd.split()))[:240])
    return [(sk, n, sample[sk]) for sk, n in shapes.most_common() if n >= minimum]


def render(found):
    return "\n".join(f"- {n} times: `{sk}`\n  - example: `{ex}`" for sk, n, ex in found)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript")
    ap.add_argument("--hook", action="store_true")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--proposals", default=str(PROPOSALS))
    a = ap.parse_args(argv)
    store = Path(a.proposals)
    if a.pending:
        print(store.read_text(encoding="utf-8") if store.exists() and store.read_text(encoding="utf-8").strip() else "no pending proposals")
        return 0
    if a.clear:
        store.unlink(missing_ok=True)
        print("cleared")
        return 0
    if a.hook:
        try:
            data = json.loads(sys.stdin.read() or "{}")
            path, sid = data.get("transcript_path"), str(data.get("session_id", ""))[:8]
            if not path or not Path(path).exists():
                return 0
            found = candidates(path, a.min)
            old = store.read_text(encoding="utf-8") if store.exists() else ""
            if found and f"## session {sid}" not in old:
                store.parent.mkdir(parents=True, exist_ok=True)
                project = Path(path).parent.name
                store.write_text(old + f"\n## session {sid} ({project})\n{render(found)}\n", encoding="utf-8")
        except Exception:
            pass                                    # a hook must never break the session
        return 0
    if not a.transcript:
        ap.error("give --transcript, --hook, --pending or --clear")
    found = candidates(a.transcript, a.min)
    print(render(found) if found else "nothing typed 3+ times")
    return 0


if __name__ == "__main__":
    sys.exit(main())
