#!/usr/bin/env python3
"""judge_answers: is the agent's ANSWER right, not only did it open the right page?

Method (the rubric idea of LangChain's WikiBench): every question in the gold file carries "facts", the things a correct
answer must contain, written by the owner who knows the answer. Per answer two separate checks:
  presence   does the answer state the fact?                       (judge sees: question, facts, answer)
  grounding  do the pages the agent actually read support it?      (judge sees: facts, those pages)
score_present = share of facts present; score_grounded = share present AND supported by the pages read.
Different information goes to the two judges on purpose, so the presence judge cannot be swayed by the pages.

A fact is a string, or {"text": "...", "any": ["substring", ...]}. With --offline no model is used: a fact counts as present
when one of its "any" substrings occurs in the answer (case-insensitive); facts without "any" are left unscored and
grounding is skipped. Offline is a cheap smoke check, not a replacement for the judges.

  judge_answers.py --bench out/C/bench.json --gold bench/questions.json --snapshot SNAP_DIR --out out/C/judge [--offline]
                   [--model claude-haiku-5-5] [--resume] [--sample 10]
It also writes manual-sample.md: a random sample of answers for a human to mark correct / partial / wrong. Check the judge
against that sample before trusting it.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_bench import LIMIT_RE  # noqa: E402

PRESENCE_PROMPT = """You grade an answer against a checklist. For each numbered fact decide whether the ANSWER states it (same meaning is enough, exact words are not needed; a vague mention or a contradicting statement does not count).
Output ONLY JSON: {"facts": [{"n": 1, "present": true}, ...]} with one entry per fact. No prose.

QUESTION:
{question}

FACTS:
{facts}

ANSWER:
{answer}
"""
GROUNDING_PROMPT = """You check whether facts are supported by wiki pages. For each numbered fact decide whether the PAGES below contain it (same meaning is enough).
Output ONLY JSON: {"facts": [{"n": 1, "supported": true}, ...]} with one entry per fact. No prose.

FACTS:
{facts}

PAGES:
{pages}
"""
PAGE_CHARS = 6000
MAX_PAGES = 5


def fill(template: str, **kw: str) -> str:
    """Plain replace of {name}: the templates contain literal JSON braces, so str.format would fail."""
    for k, v in kw.items():
        template = template.replace("{" + k + "}", v)
    return template


def fact_text(f) -> str:
    return f if isinstance(f, str) else f["text"]


def numbered(facts: list) -> str:
    return "\n".join(f"{i}. {fact_text(f)}" for i, f in enumerate(facts, 1))


def call_model(prompt: str, model: str) -> str:
    r = subprocess.run(["claude", "-p", "--model", model, "--tools", "", "--output-format", "text"], input=prompt, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=tempfile.gettempdir(), timeout=300)
    return r.stdout + "\n" + r.stderr[-300:]


def parse_flags(raw: str, key: str, n: int) -> list[bool | None]:
    """Read {"facts":[{"n":1,key:true}...]} out of a model reply; missing entries become None."""
    out: list[bool | None] = [None] * n
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return out
    try:
        for e in json.loads(m.group(0)).get("facts", []):
            i = int(e["n"]) - 1
            if 0 <= i < n and isinstance(e.get(key), bool):
                out[i] = e[key]
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return out


def offline_present(facts: list, answer: str) -> list[bool | None]:
    a = answer.lower()
    return [any(s.lower() in a for s in f["any"]) if isinstance(f, dict) and f.get("any") else None for f in facts]


def pages_text(snapshot: Path, opened: list[str]) -> str:
    chunks = []
    for slug in list(dict.fromkeys(opened))[:MAX_PAGES]:
        p = snapshot / "wiki" / f"{slug}.md"
        if p.is_file():
            chunks.append(f"=== {slug} ===\n{p.read_text(encoding='utf-8', errors='replace')[:PAGE_CHARS]}")
    return "\n\n".join(chunks) or "(the agent read no wiki page)"


def score(flags: list[bool | None]) -> float | None:
    known = [f for f in flags if f is not None]
    return None if not known else sum(known) / len(known)


def judge_one(q: dict, r: dict, snapshot: Path, model: str, offline: bool, caller=call_model) -> dict:
    facts = q["facts"]
    out = {"id": r["id"], "n_facts": len(facts)}
    if offline:
        present = offline_present(facts, r["answer"])
        grounded: list[bool | None] = [None] * len(facts)
    else:
        raw_p = caller(fill(PRESENCE_PROMPT, question=q["question"], facts=numbered(facts), answer=r["answer"]), model)
        if LIMIT_RE.search(raw_p):
            return {**out, "error": "limit"}
        present = parse_flags(raw_p, "present", len(facts))
        raw_g = caller(fill(GROUNDING_PROMPT, facts=numbered(facts), pages=pages_text(snapshot, r.get("opened", []))), model)
        if LIMIT_RE.search(raw_g):
            return {**out, "error": "limit"}
        sup = parse_flags(raw_g, "supported", len(facts))
        grounded = [(p and s) if p is not None and s is not None else None for p, s in zip(present, sup)]
    return {**out, "present": present, "grounded": grounded, "score_present": score(present), "score_grounded": score(grounded),
            "error": "unparsed" if all(x is None for x in present) else None}


def manual_sample(rows: list[dict], results: dict, golds: dict, k: int, seed: int = 1) -> str:
    pick = random.Random(seed).sample(rows, min(k, len(rows)))
    L = ["# Manual check", "", "Mark each answer: correct / partial / wrong. Compare with the judge afterwards.", ""]
    for row in pick:
        q, r = golds[row["id"]], results[row["id"]]
        L += [f"## #{q['id']}: {q['question']}", "", "Facts the answer must contain:", *[f"- {fact_text(f)}" for f in q["facts"]], "",
              "Answer:", "", r["answer"], "", f"Judge: present {row.get('score_present')}, grounded {row.get('score_grounded')}",
              "Your mark: ", ""]
    return "\n".join(L)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="folder for judge.json, judge.md, manual-sample.md")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--sample", type=int, default=10)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    golds = {q["id"]: q for q in json.loads(a.gold.read_text(encoding="utf-8")) if q.get("facts")}
    results = {r["id"]: r for r in json.loads(a.bench.read_text(encoding="utf-8"))["results"] if not r.get("error")}
    todo = [i for i in results if i in golds]
    print(f"{len(todo)} answers with facts ({len(results) - len(todo)} valid runs skipped: no facts in the gold file)")
    jf = a.out / "judge.json"
    rows = [x for x in json.loads(jf.read_text(encoding="utf-8")) if not x.get("error")] if a.resume and jf.exists() else []
    done = {x["id"] for x in rows}
    code = 0
    for i in todo:
        if i in done:
            continue
        row = judge_one(golds[i], results[i], a.snapshot, a.model, a.offline)
        rows.append(row)
        jf.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"#{i}: present={row.get('score_present')} grounded={row.get('score_grounded')} error={row.get('error')}", flush=True)
        if row.get("error") == "limit":
            print("STOPPED: usage limit. Run again with --resume after it resets.")
            code = 3
            break
    ok = [x for x in rows if not x.get("error")]
    sp = [x["score_present"] for x in ok if x["score_present"] is not None]
    sg = [x["score_grounded"] for x in ok if x["score_grounded"] is not None]
    md = [f"# Answer judge ({'offline' if a.offline else a.model})", "", f"{len(ok)} judged answers, {len(rows) - len(ok)} failed.", "",
          f"Mean share of facts present: {sum(sp) / len(sp):.2f}" if sp else "No present-scores.",
          f"Mean share present AND supported by the pages read: {sum(sg) / len(sg):.2f}" if sg else "No grounding scores (offline mode or no data).", "",
          "| q | present | grounded | error |", "|---|---|---|---|"]
    md += [f"| {x['id']} | {x.get('score_present')} | {x.get('score_grounded')} | {x.get('error') or ''} |" for x in rows]
    (a.out / "judge.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    if ok:
        (a.out / "manual-sample.md").write_text(manual_sample(ok, results, golds, a.sample), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
