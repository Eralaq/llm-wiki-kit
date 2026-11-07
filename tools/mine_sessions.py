#!/usr/bin/env python3
"""Session miner: compress Claude Code transcripts into per-session signals and cross-session candidates.

Read-only, stdlib only, no model calls. Input: a folder of Claude Code *.jsonl transcripts
(~/.claude/projects/<project>). Output: <out>/sessions.json (per session) and <out>/report.md
(candidates for CLAUDE.md lines, skills, permission rules). A cause counts as a candidate only when it
repeats in at least --min-sessions distinct sessions (default 3), so one odd session cannot make a rule.
Every text snippet passes through redact() before it is stored.

Usage: mine_sessions.py --src ~/.claude/projects/<project-folder> --out <output dir>
"""
from __future__ import annotations

import argparse
import collections
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
CORRECTION = re.compile(r"(?i)^\W*(нет\b|не так|не то\b|исправь|опять|снова|ты не |зачем ты|я же просил|почему ты|stop\b|wrong\b|that'?s not|why did you)")
LOOSE = re.compile(r"(?i)(не так|не то|не надо|не нужно было|я же (просил|говорил|сказал)|почему ты|зачем ты|ты (не |опять|снова|что)|опять|снова|неправильн|ошибс|верни|откати|не понял|что за |wrong|not what i|why did you|i said)")
PROD = re.compile(r"(deploy\.py|systemctl (restart|stop|start)|pm2 (restart|stop|delete)|git push|docker (compose )?(up|restart)|rm -rf)")
LOOP_NOTE = re.compile(r"Bot note: you have run the same kind of check")
PREAMBLE = re.compile(r"^\s*\[(Telegram|Transcript of a voice note)[^\]]*\]\s*")


def clean_prompt(text: str) -> str:
    """User text without the bot's Telegram / voice-note headers."""
    prev = None
    while prev != text:
        prev, text = text, PREAMBLE.sub("", text)
    return text.strip()
PERMISSION = re.compile(r"(?i)(permission (for this action )?(was )?denied|auto mode classifier|requires approval|not allowed|blocked:|denied by tg)")
FAIL_WORDS = re.compile(r"(?i)(error|traceback|no such file|not found|permission denied|refused|timed out|timeout|failed|exception|cannot|unexpected)")


def redact(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    for rx, rep in SECRET:
        text = rx.sub(rep, text)
    return text[:limit]


GENERIC = re.compile(r"^(cd|ls|cat|echo|pwd|git|head|tail|wc|true|which|export|mkdir|rm|cp|mv|sed -n|grep|rg|find|sleep|test)\b")


def skeleton(cmd: str) -> str:
    """Shape of a command: leading cd removed, quoted text, numbers and paths collapsed, first three lines only."""
    cmd = re.sub(r"^\s*cd\s+\S+\s*(&&|;)\s*", "", cmd.strip())
    lines = [ln.strip() for ln in cmd.splitlines() if ln.strip()][:3]
    s = " | ".join(lines)
    s = re.sub(r"\"[^\"]*\"|'[^']*'", "S", s)
    s = re.sub(r"[A-Za-z]:\\[^\s]+|/[\w./~-]{3,}", "P", s)
    s = re.sub(r"\b\d+\b", "N", s)
    s = " ".join(s.split())[:120]
    return "" if len(s) < 14 or GENERIC.match(s) else s


def signature(text: str) -> str:
    """Stable key for 'the same error': numbers, paths and ids removed."""
    t = redact(text, 400).lower()
    t = re.sub(r"[a-z]:\\[^\s'\"]+|/[\w./~-]{3,}", "<path>", t)
    t = re.sub(r"\b[0-9a-f]{7,}\b", "<id>", t)
    t = re.sub(r"\d+", "N", t)
    return t[:110]


def blocks(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def mine(path: Path) -> dict | None:
    s = {"id": path.stem, "events": 0, "user_prompts": 0, "assistant_turns": 0, "tools": collections.Counter(),
         "errors": [], "denials": 0, "corrections": [], "bash": collections.Counter(), "reads": collections.Counter(),
         "tokens": collections.Counter(), "peak_context": 0, "compactions": 0, "first_prompt": "", "retries": 0, "loop_notes": 0, "stamps": [], "compact_kinds": collections.Counter(), "compact_pre": [], "timeouts": [], "deny_reasons": collections.Counter(), "trail": [], "loose": [], "denied_cmds": collections.Counter(), "retry_cmds": collections.Counter(), "prod": [], "skel": collections.Counter(), "skel_sample": {}}
    uses: dict[str, tuple[str, dict]] = {}
    first = last = None
    prev_cmd = None
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        s["events"] += 1
        ts = o.get("timestamp")
        if ts:
            first, last = first or ts, ts
            s["stamps"].append(ts)
        kind = o.get("type")
        if o.get("isSidechain"):
            continue
        if kind == "system" and "compact" in str(o.get("subtype", "")):
            s["compactions"] += 1
            meta = o.get("compactMetadata") or {}
            s["compact_kinds"][str(meta.get("trigger", "?"))] += 1
            s["compact_pre"].append(int(meta.get("preTokens") or 0) // 1000)
            s["trail"].append("K: context compacted")
        msg = o.get("message") or {}
        if kind == "assistant":
            s["assistant_turns"] += 1
            u = msg.get("usage") or {}
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                s["tokens"][k] += u.get(k, 0) or 0
            ctx = (u.get("input_tokens", 0) or 0) + (u.get("cache_read_input_tokens", 0) or 0) + (u.get("cache_creation_input_tokens", 0) or 0)
            s["peak_context"] = max(s["peak_context"], ctx)
            for b in blocks(msg):
                if b.get("type") == "tool_use":
                    name, inp = b.get("name", "?"), b.get("input") or {}
                    uses[b.get("id", "")] = (name, inp)
                    s["tools"][name] += 1
                    if name == "Bash":
                        cmd = " ".join(str(inp.get("command", "")).split())
                        words = cmd.split()
                        s["bash"][" ".join(words[:2])] += 1
                        if cmd and cmd == prev_cmd:
                            s["retries"] += 1
                            s["retry_cmds"][redact(cmd, 90)] += 1
                        sk = skeleton(str(inp.get("command", "")))
                        if sk:
                            s["skel"][sk] += 1
                            s["skel_sample"].setdefault(sk, redact(inp.get("command", ""), 320))
                        if PROD.search(cmd):
                            s["prod"].append(redact(cmd, 90))
                            s["trail"].append("P: " + redact(cmd, 90))
                        prev_cmd = cmd
                    elif name in ("Read", "Edit", "Write"):
                        s["reads"][str(inp.get("file_path", ""))[-60:]] += 1
        elif kind == "user":
            for b in blocks(msg):
                t = b.get("type")
                if t == "text":
                    text = b.get("text", "")
                    if text.startswith("<") or not text.strip():
                        continue
                    if LOOP_NOTE.search(text[:200]):
                        s["loop_notes"] += 1
                        s["trail"].append("B: bot loop note")
                        continue
                    text = clean_prompt(text)
                    if not text or text.startswith("<pasted_content") or text.startswith("▐"):
                        continue
                    s["user_prompts"] += 1
                    if not s["first_prompt"]:
                        s["first_prompt"] = redact(text, 200)
                    if LOOSE.search(text[:200]):
                        s["loose"].append(redact(text, 140))
                    if CORRECTION.search(text[:80]):
                        s["corrections"].append(redact(text, 140))
                        s["trail"].append("C: " + redact(text, 140))
                    else:
                        s["trail"].append("U: " + redact(text, 120))
                elif t == "tool_result":
                    body = b.get("content")
                    if isinstance(body, list):
                        body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                    body = str(body or "")
                    name = uses.get(b.get("tool_use_id", ""), ("?", {}))[0]
                    if PERMISSION.search(body[:400]):
                        s["denials"] += 1
                        s["errors"].append((name, "DENIED " + signature(body[:200])))
                        m = re.search(r"(?i)reason: \[([^\]]{1,60})\]", body[:600])
                        s["deny_reasons"][m.group(1) if m else "no tag"] += 1
                        _inp = uses.get(b.get("tool_use_id", ""), ("?", {}))[1]
                        s["denied_cmds"][redact(f"{name}: " + str(_inp.get("command") or _inp.get("file_path") or _inp.get("pattern") or ""), 100)] += 1
                        s["trail"].append(f"D: {name} denied: " + signature(body[:120]))
                    elif b.get("is_error") or (name == "Bash" and FAIL_WORDS.search(body[:300]) and "exit code" in body[:300].lower()):
                        s["errors"].append((name, signature(body[:200])))
                        if name in ("Glob", "Grep") and "timed out" in body[:200]:
                            inp = uses.get(b.get("tool_use_id", ""), ("?", {}))[1]
                            s["timeouts"].append(redact(f"{name} path={inp.get('path', '(cwd)')} pattern={inp.get('pattern', '')} glob={inp.get('glob', '')}", 150))
                        s["trail"].append(f"E: {name}: " + signature(body[:120]))
    s["start"], s["end"] = first, last
    from datetime import datetime
    try:
        ts = sorted(datetime.fromisoformat(x.replace("Z", "+00:00")) for x in s["stamps"])
        gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
        s["active_min"] = round(sum(g for g in gaps if g <= 600) / 60)
        s["wall_min"] = round((ts[-1] - ts[0]).total_seconds() / 60) if ts else 0
    except ValueError:
        s["active_min"] = s["wall_min"] = 0
    s["stamps"] = []
    if not s["events"] or not s["assistant_turns"]:
        return None
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-sessions", type=int, default=3)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    sessions = [m for p in sorted(a.src.glob("*.jsonl")) if (m := mine(p))]
    sessions.sort(key=lambda x: x["start"] or "")

    def share(key_fn):
        seen = collections.defaultdict(set)
        total = collections.Counter()
        for s in sessions:
            for k in key_fn(s):
                seen[k].add(s["id"])
                total[k] += 1
        return sorted(((k, len(v), total[k], sorted(i[:8] for i in v)) for k, v in seen.items() if len(v) >= a.min_sessions), key=lambda r: (-r[1], -r[2]))

    errs = share(lambda s: {f"{n}: {sg}" for n, sg in s["errors"]})
    cmds = share(lambda s: {k for k, c in s["bash"].items() if c >= 3})
    reads = share(lambda s: {k for k, c in s["reads"].items() if c >= 3 and k})
    denials = sum(s["denials"] for s in sessions)

    out = []
    for s in sessions:
        out.append({**{k: v for k, v in s.items() if k not in ("tools", "bash", "reads", "errors", "tokens", "trail", "skel", "skel_sample", "loose", "denied_cmds", "retry_cmds", "prod")},
                    "tools": dict(s["tools"].most_common(8)), "tokens": dict(s["tokens"]),
                    "errors": len(s["errors"]), "top_errors": collections.Counter(f"{n}: {g}" for n, g in s["errors"]).most_common(3)})
    (a.out / "sessions.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    heavy = sorted(sessions, key=lambda x: -x["tokens"]["output_tokens"])[:5]
    dig = a.out / "digests"
    dig.mkdir(exist_ok=True)
    for s in heavy:
        trail = s["trail"]
        keep = trail if len(trail) <= 90 else trail[:45] + [f"... {len(trail)-90} events skipped ..."] + trail[-45:]
        head = f"session {s['id'][:8]}  start {s['start']}  prompts {s['user_prompts']}  turns {s['assistant_turns']}  out_tokens {s['tokens']['output_tokens']}  peak_ctx {s['peak_context']}"
        (dig / f"{s['id'][:8]}.txt").write_text(head + chr(10) + chr(10).join(keep) + chr(10), encoding="utf-8")
    bloat = [s for s in sessions if s["peak_context"] >= 300_000 or s["compactions"] >= 3]
    tot = sum(s["tokens"]["output_tokens"] for s in sessions) or 1
    causes = [
        f"- Context bloat (peak >= 300k or >= 3 compactions): {len(bloat)} sessions, {sum(s['tokens']['output_tokens'] for s in bloat)*100//tot}% of all output tokens.",
        f"- Bot loop notes (same check repeated): {sum(s['loop_notes'] for s in sessions)} in {sum(1 for s in sessions if s['loop_notes'])} sessions.",
        f"- Permission denials: {denials} in {sum(1 for s in sessions if s['denials'])} sessions.",
        f"- Identical Bash command repeated back to back: {sum(s['retries'] for s in sessions)} times.",
        f"- Real user corrections (strict filter): {sum(len(s['corrections']) for s in sessions)}; loose filter (pushback words in the first 200 chars): {sum(len(s['loose']) for s in sessions)} in {sum(1 for s in sessions if s['loose'])} sessions.",
        f"- Production-type commands (deploy, restart, push, rm -rf): {sum(len(s['prod']) for s in sessions)} in {sum(1 for s in sessions if s['prod'])} sessions.",
    ]

    L = [f"# Session miner report: {a.src.name}", "", f"{len(sessions)} sessions. Candidate rule: repeats in >= {a.min_sessions} sessions.", "",
         "## Causes, by share", "", *causes, "",
         "## Sessions", "", "| session | start | prompts | turns | tool errors | denials | retries | corrections | peak ctx (k) | compactions | out tokens (k) | all input incl. cache (M) | active min | wall min |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sessions:
        L.append(f"| {s['id'][:8]} | {(s['start'] or '')[:16]} | {s['user_prompts']} | {s['assistant_turns']} | {len(s['errors'])} | {s['denials']} | {s['retries']} | {len(s['corrections'])} | {s['peak_context']//1000} | {s['compactions']} | {s['tokens']['output_tokens']//1000} | {(s['tokens']['input_tokens']+s['tokens']['cache_read_input_tokens']+s['tokens']['cache_creation_input_tokens'])/1e6:.1f} | {s['active_min']} | {s['wall_min']} |")
    L += ["", "## Errors repeated across sessions (candidates for a CLAUDE.md line, a script or a permission rule)", "", "| sessions | times | error (tool: signature) | session ids |", "|---|---|---|---|"]
    L += [f"| {n} | {t} | `{k}` | {' '.join(ids)} |" for k, n, t, ids in errs[:25]] or ["| - | - | none | |"]
    L += ["", "## Bash commands repeated 3+ times in a session, in 3+ sessions (candidates for a skill or script)", "", "| sessions | prefix | session ids |", "|---|---|---|"]
    L += [f"| {n} | `{k}` | {' '.join(ids)} |" for k, n, t, ids in cmds[:20]] or ["| - | none | |"]
    L += ["", "## Files read or edited 3+ times in a session, in 3+ sessions (candidates for a CLAUDE.md pointer)", "", "| sessions | file tail | session ids |", "|---|---|---|"]
    L += [f"| {n} | `{k}` | {' '.join(ids)} |" for k, n, t, ids in reads[:20]] or ["| - | none | |"]
    reasons = collections.Counter()
    kinds = collections.Counter()
    for s in sessions:
        reasons.update(s["deny_reasons"])
        kinds.update(s["compact_kinds"])
    tmo = collections.Counter(t for s in sessions for t in s["timeouts"])
    L += ["", "## Compactions by trigger", "", ", ".join(f"{k}: {v}" for k, v in kinds.most_common()) or "none",
          "", "Context size before each compaction (k tokens), per session: " + "; ".join(f"{s['id'][:8]} {s['compact_pre']}" for s in sessions if s["compact_pre"]),
          "", "## Permission denials by classifier reason", ""] + [f"- {n} x {k}" for k, n in reasons.most_common(12)]
    L += ["", "## Search timeouts: tool, path, pattern (most repeated first)", ""] + [f"- {n} x {k}" for k, n in tmo.most_common(15)]
    dc, rc = collections.defaultdict(set), collections.Counter()
    dn = collections.Counter()
    for s in sessions:
        for k, n in s["denied_cmds"].items():
            dc[k].add(s["id"][:8])
            dn[k] += n
        for k, n in s["retry_cmds"].items():
            rc[k] += n
    sk_s, sk_n, sk_ex = collections.defaultdict(set), collections.Counter(), {}
    for s in sessions:
        for k, n in s["skel"].items():
            if n >= 3:
                sk_s[k].add(s["id"][:8])
                sk_n[k] += n
                sk_ex.setdefault(k, s["skel_sample"].get(k, ""))
    cand = sorted(((k, len(v)) for k, v in sk_s.items() if len(v) >= a.min_sessions), key=lambda r: (-r[1], -sk_n[r[0]]))
    L += ["", "## Skill candidates: command shapes typed 3+ times in a session, in 3+ sessions", "",
          "Shape = quoted text, numbers and paths collapsed. Deep dive for one candidate: skill-factory `mine_sessions.py <project fragment>`.", ""]
    for k, n in cand[:12]:
        L += [f"- {n} sessions, {sk_n[k]} times: `{k}`", f"  - example (redacted): `{sk_ex[k][:300]}`", f"  - sessions: {' '.join(sorted(sk_s[k]))}"]
    if not cand:
        L.append("- none")
    L += ["", "## Denied commands (redacted), most repeated first", ""] + [f"- {dn[k]} x `{k}` in {len(dc[k])} sessions" for k, _ in dn.most_common(15)]
    L += ["", "## Identical back-to-back Bash commands (redacted), by total repeats", ""] + [f"- {n} x `{k}`" for k, n in rc.most_common(12)]
    L += ["", "## Production-type commands per session", ""] + [f"- {s['id'][:8]}: {len(s['prod'])}" for s in sessions if s["prod"]]
    L += ["", "## Loose pushback matches (first words, redacted)", ""]
    for s in sessions:
        for c in s["loose"][:4]:
            L.append(f"- {s['id'][:8]}: {c}")
    L += ["", f"## Permission denials in total: {denials}", "", "## User corrections (first words, redacted)", ""]
    for s in sessions:
        for c in s["corrections"][:3]:
            L.append(f"- {s['id'][:8]}: {c}")
    (a.out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(sessions)} sessions -> {a.out}/report.md; candidate errors {len(errs)}, commands {len(cmds)}, files {len(reads)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
