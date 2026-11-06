#!/usr/bin/env python3
"""Draft aliases from history, without the bench questions (no leakage).

For every past question (user prompt) that led the agent to read wiki pages, words of the prompt are linked to those
pages. A word becomes a page alias when it is rare overall and shows up in >= --min-episodes questions that read
that page. The bench questions are excluded. Output is a DRAFT for the owner to review: reads are noisy labels.
"""
import argparse, collections, json, math, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from wiki_miner import Wiki, mine
STOP = set("""это как что для при или так если вот уже еще ещё все всё его она они нас вас нам вам мне меня тебя ты вы мы там тут чтобы потому почему можно нужно надо сейчас просто тоже очень теперь давай сделай сделать делаем посмотри смотри пожалуйста можешь которые который какие есть было будет быть этого этом этой этих когда после перед между через тогда where which with this that have from into about there their would should could please just also then than some more most make need want does""".split())
WORD = re.compile(r"[а-яёa-z][а-яёa-z0-9\-]{3,}", re.I)
ap = argparse.ArgumentParser()
ap.add_argument("--wiki", type=Path, required=True)
ap.add_argument("--gold", type=Path, required=True, help="bench questions to EXCLUDE (no leakage)")
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--min-episodes", type=int, default=2)
ap.add_argument("--max-df", type=float, default=0.12)
ap.add_argument("--per-page", type=int, default=8)
a = ap.parse_args()
gold = json.loads(a.gold.read_text(encoding="utf-8"))
skip = {(g["session"], g["ts"]) for g in gold}
wiki = Wiki(a.wiki)
eps = []
for p in sorted(Path.home().joinpath(".claude/projects").glob("*/*.jsonl")):
    s = mine(p, wiki)
    for ep in (s["episodes"] if s else []):
        pages = {x["page"] for x in ep["steps"] if x["op"] == "read" and x["page"] in wiki.pages and x["page"] not in ("index", "log")}
        text = ep["q_long"]
        if (s["id"][:8], ep["ts"]) in skip or not pages or text.startswith(("<", "This session", "Base directory", "[")):
            continue
        words = {w.lower().replace("ё", "е") for w in WORD.findall(text)} - STOP
        eps.append((words, pages))
N = len(eps)
df = collections.Counter(w for ws, _ in eps for w in ws)
cnt = collections.defaultdict(collections.Counter)
nep = collections.Counter()
for ws, pages in eps:
    for pg in pages:
        nep[pg] += 1
        for w in ws:
            cnt[pg][w] += 1
out = {}
for pg, c in cnt.items():
    cand = [(c[w] * math.log(N / df[w]), w, c[w]) for w in c if c[w] >= a.min_episodes and df[w] / N <= a.max_df]
    cand.sort(reverse=True)
    if cand:
        out[pg] = {"aliases": [w for _, w, _ in cand[:a.per_page]], "evidence": {w: n for _, w, n in cand[:a.per_page]}, "episodes": nep[pg]}
a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{N} questions used (bench excluded), {len(out)} pages got aliases -> {a.out}")
