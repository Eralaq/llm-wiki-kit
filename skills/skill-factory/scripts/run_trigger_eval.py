"""Does the model pick an installed skill for a phrase? Runs `claude -p` per phrase and watches the first tool call.

Based on anthropics/skills skill-creator `run_eval.py`, changed for Windows (a reader thread instead of select on a pipe,
`claude` found with shutil.which) and for real skills: no temporary command file is written, the installed skill is
tested. The process is killed at the first tool call, so a skill's script never runs.

  python run_trigger_eval.py evals/skill-factory.json --skill skill-factory --cwd /path/to/project [--runs 1] [--timeout 60]

An eval set is a JSON list: [{"query": "...", "should_trigger": true}, ...]. Result JSON goes to stdout and to
`out/<skill>_<timestamp>.json` next to this skill."""
import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def classify(events, skill):
    """True when the first tool the model calls is `Skill` for `skill`; False for any other first tool or for no tool at
    all; None when the events end before either is known. `events` yields parsed stream-json objects."""
    pending, buf = False, ""
    for ev in events:
        kind = ev.get("type")
        if kind == "stream_event":
            e = ev.get("event", {})
            t = e.get("type")
            if t == "content_block_start" and e.get("content_block", {}).get("type") == "tool_use":
                if e["content_block"].get("name") != "Skill":
                    return False
                pending, buf = True, ""
            elif t == "content_block_delta" and pending:
                d = e.get("delta", {})
                if d.get("type") == "input_json_delta":
                    buf += d.get("partial_json", "")
                    if skill in buf:
                        return True
            elif t in ("content_block_stop", "message_stop"):
                if pending:
                    return skill in buf
                if t == "message_stop":
                    return False
        elif kind == "assistant":
            for item in ev.get("message", {}).get("content", []):
                if item.get("type") == "tool_use":
                    return item.get("name") == "Skill" and skill in str((item.get("input") or {}).get("skill", ""))
        elif kind == "result":
            return False
    return None


def stream_events(cmd, cwd, timeout):
    """Parsed JSON lines of a process, read in a thread so a silent process cannot block past `timeout`."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=cwd, env=env)
    lines = queue.Queue()

    def reader():
        for raw in proc.stdout:
            lines.put(raw)
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    end = time.time() + timeout
    try:
        while time.time() < end:
            try:
                raw = lines.get(timeout=1.0)
            except queue.Empty:
                continue
            if raw is None:
                return
            try:
                yield json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def run_query(query, skill, cwd, timeout, model=None):
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("claude is not on PATH")
    cmd = [claude, "-p", query, "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--max-turns", "1"]
    if model:
        cmd += ["--model", model]
    return bool(classify(stream_events(cmd, cwd, timeout), skill))


def evaluate(items, skill, cwd, runs, timeout, workers, model=None, runner=run_query, threshold=0.5):
    jobs = [(it, i) for it in items for i in range(runs)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(lambda j: _safe(runner, j[0]["query"], skill, cwd, timeout, model), jobs))
    by_query = {}
    for (it, _), ok in zip(jobs, outcomes):
        by_query.setdefault(it["query"], [it, []])[1].append(ok)
    results = []
    for query, (it, hits) in by_query.items():
        rate = sum(hits) / len(hits)
        results.append({"query": query, "should_trigger": it["should_trigger"], "triggers": sum(hits), "runs": len(hits),
                        "pass": rate >= threshold if it["should_trigger"] else rate < threshold})
    passed = sum(r["pass"] for r in results)
    return {"skill": skill, "results": results, "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed}}


def _safe(runner, *args):
    try:
        return runner(*args)
    except Exception as e:  # noqa: BLE001 - one failed call counts as "did not trigger", and is said on stderr
        print(f"warning: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("eval_set")
    ap.add_argument("--skill", required=True)
    ap.add_argument("--cwd", default=".", help="the project folder claude runs in (project skills are found from there)")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    items = json.loads(Path(a.eval_set).read_text(encoding="utf-8"))
    out = evaluate(items, a.skill, a.cwd, a.runs, a.timeout, a.workers, a.model)
    folder = Path(__file__).resolve().parent.parent / "out"
    folder.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    text = json.dumps(out, indent=2, ensure_ascii=False)
    (folder / f"{a.skill}_{stamp}.json").write_text(text, encoding="utf-8")
    for r in out["results"]:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['triggers']}/{r['runs']} want={r['should_trigger']}: {r['query'][:80]}")
    s = out["summary"]
    print(f"{a.skill}: {s['passed']}/{s['total']} passed")


if __name__ == "__main__":
    main()
