"""
mine_reads.py - find what Claude keeps READING in past sessions of a project: the files read in full again and again, the
tool results that were big and stayed in the context for hundreds of later calls. This is where a long session's cost comes
from (mine_sessions.py looks at what is typed; this looks at what comes back).

  mine_reads.py MyProject                    # project folder name fragment under ~/.claude/projects (case-insensitive)
  mine_reads.py MyProject --top 12 --out reads.md
  mine_reads.py MyProject --session 62fecebe  # only transcript files whose name starts with this

What it reports (deterministic, no LLM, secrets are masked):
  1. CARRY     the results that cost most: tokens x the number of later model calls that carried them in the context
               (the carry ends at a /compact). This is the number a skill should cut, not the size alone.
  2. REREAD    files read in full more than once (Read without offset/limit, or `cat file`), with the tokens re-read
  3. TOOLS     tokens of results per tool

Tokens are estimated from characters (Latin about 3.5 characters a token, Cyrillic and other scripts about 2).
The output is a CANDIDATE list for a human. Nothing is created here; see scaffold_skill.py.
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

SECRET = re.compile(r"(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|PGPASSWORD)\s*[=:]\s*)(['\"]?)[^'\"\s,)]+")
CAT = re.compile(r"^\s*(?:cat|type|Get-Content)\s+(\S+)\s*$")


def mask(s):
    return SECRET.sub(lambda m: m.group(1) + m.group(2) + "***", s)


def tokens(text):
    ascii_chars = len(text.encode("ascii", "ignore"))
    return round(ascii_chars / 3.5 + (len(text) - ascii_chars) / 2.0)


IMAGE_TOKENS = 1500     # an image costs about this whatever its bytes: counting its base64 as text would be far too much


def result_tokens(content):
    if isinstance(content, str):
        return tokens(content)
    if isinstance(content, list):
        total = 0
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                total += tokens(c.get("text", ""))
            elif isinstance(c, dict) and c.get("type") == "image":
                total += IMAGE_TOKENS
            else:
                total += tokens(json.dumps(c, ensure_ascii=False))
        return total
    return tokens(json.dumps(content, ensure_ascii=False)) if content is not None else 0


def files_of(fragment, session):
    root = os.path.expanduser("~/.claude/projects")
    out = []
    for d in glob.glob(root + "/*"):
        if fragment.lower() in os.path.basename(d).lower():
            out += glob.glob(d + "/*.jsonl")
    if session:
        out = [f for f in out if os.path.basename(f).startswith(session)]
    return sorted(out)


def what(name, args):
    args = args if isinstance(args, dict) else {}
    detail = args.get("command") or args.get("file_path") or args.get("pattern") or args.get("path") or ""
    return mask(f"{name}: {str(detail)[:80]}".replace("\n", " ")).strip(": ")


def full_read_key(name, args):
    """The file a call reads in full, or None (a partial read, or not a read)."""
    args = args if isinstance(args, dict) else {}
    if name == "Read" and not args.get("offset") and not args.get("limit"):
        return args.get("file_path")
    if name == "Bash":
        m = CAT.match(args.get("command") or "")
        return m.group(1) if m else None
    return None


def mine(path):
    """Yield one record per tool result: (what, tool, tokens, calls_carried, full_read_key, session)."""
    calls = {}            # tool_use id -> (name, what, key)
    segment = []          # results since the last compaction: [what, tool, tokens, call index, key]
    n_calls = 0
    sid = os.path.basename(path)[:8]
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("isSidechain"):
                continue
            if d.get("type") == "system" and d.get("subtype") == "compact_boundary":
                for r in segment:
                    yield (r[0], r[1], r[2], n_calls - r[3], r[4], sid)
                segment, n_calls = [], 0
                continue
            content = (d.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            if d.get("type") == "assistant":
                if (d.get("message") or {}).get("usage"):
                    n_calls += 1
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        args = b.get("input")
                        calls[b.get("id")] = (b.get("name") or "tool", what(b.get("name") or "tool", args), full_read_key(b.get("name"), args))
            elif d.get("type") == "user":
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        name, desc, key = calls.get(b.get("tool_use_id"), ("tool", "tool", None))
                        segment.append([desc, name, result_tokens(b.get("content")), n_calls, key])
    for r in segment:
        yield (r[0], r[1], r[2], n_calls - r[3], r[4], sid)


def k(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else str(int(n))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project", help="fragment of the folder name under ~/.claude/projects")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-tokens", type=int, default=1500, help="ignore results smaller than this for CARRY")
    ap.add_argument("--session", help="only transcript files whose name starts with this")
    ap.add_argument("--out", help="also write the report to this file")
    a = ap.parse_args()

    files = files_of(a.project, a.session)
    if not files:
        sys.exit("no transcripts match " + a.project)
    rows = [r for f in files for r in mine(f)]
    by_tool = Counter()
    for desc, tool, tok, carried, key, sid in rows:
        by_tool[tool] += tok
    out = [f"# reads in {len(files)} transcript(s), {len(rows)} tool results, ~{k(sum(by_tool.values()))} tokens of results"]

    big = sorted((r for r in rows if r[2] >= a.min_tokens), key=lambda r: r[2] * max(r[3], 1), reverse=True)[:a.top]
    out.append("\n## CARRY: result tokens x later model calls that carried them (cut these first)")
    for desc, tool, tok, carried, key, sid in big:
        out.append(f"{k(tok * max(carried, 1)):>8} = {k(tok):>6} x {carried:<4} {sid}  {desc}")

    groups = defaultdict(list)
    for desc, tool, tok, carried, key, sid in rows:
        if key:
            groups[key].append((tok, carried, sid))
    rereads = sorted(((key, v) for key, v in groups.items() if len(v) > 1), key=lambda kv: sum(t for t, _, _ in kv[1][1:]), reverse=True)[:a.top]
    out.append("\n## REREAD: files read in full more than once (a skill or an offset/limit habit removes these)")
    if not rereads:
        out.append("none")
    for key, v in rereads:
        extra = sum(t for t, _, _ in v[1:])
        out.append(f"{len(v):>3}x  {k(extra):>7} re-read  ~{k(v[0][0])} each  {mask(key)}")

    out.append("\n## TOOLS: result tokens per tool")
    for tool, tok in by_tool.most_common(6):
        out.append(f"{k(tok):>8}  {tool}")

    text = "\n".join(out)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    main()
