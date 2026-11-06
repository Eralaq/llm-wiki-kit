# llm-wiki-kit

Everything we know about running an agent-maintained markdown wiki (Karpathy's "LLM Wiki" pattern) and checking that agents can actually find what is in it: a starting template, search and measurement tools, skills, prompts, and honest notes on what worked and what did not.

Status: **v0.1, private, not yet used outside the project it grew from.** Numbers in `docs/` come from one 559-page wiki, one small model and nine questions. Read them as a direction.

## What is inside

| Folder | What | Start with |
|---|---|---|
| `template/` | A clean wiki constitution (`CLAUDE.md`), index, log and page skeletons, alias file example; `DECISIONS.md` lists where 14 diverging wikis disagreed and what we chose | `template/README.md` |
| `tools/` | `wiki_miner` (how agents really move through a wiki), `add_context`, `run_bench` (replay real questions on a frozen copy), `wiki_search` (field-weighted BM25 with a side alias file), `gen_aliases`, `eval_search`, `mine_sessions` + `run_improver.sh`, `apply_additions` | `bench/README.md` |
| `skills/` | `wiki-peek`, `code-peek`, `source-code-context` (portable); `skill-factory`, `skill-hub` (adapt first) | `skills/README.md` |
| `prompts/` | The prompts our tools send, with notes on purpose and known weaknesses | `prompts/` |
| `bench/` | How to build a question set and run an A/B on your own wiki | `bench/README.md` |
| `docs/` | The pattern, our measurements, how we differ from the pattern, imported ideas, roadmap | `docs/README.md` |
| `install.py` | Puts the template, tools and skills into a project without overwriting anything | `INSTALL.md` |

## Quick start (one project)

```
python install.py --target /path/to/project --project "My project" --scope "what the wiki covers" --tools --dry-run
python install.py --target /path/to/project --project "My project" --scope "what the wiki covers" --tools --skills project
```

Then fill `CLAUDE.md` (if the project already has one, compare it with `CLAUDE.template.md`), and measure before changing anything:

```
python tools/wiki_miner.py --wiki /path/to/project/wiki --out out/miner     # read-only, free
python tools/eval_search.py --wiki /path/to/project/wiki --gold bench/questions.json   # free, offline
```

## Rules we follow

1. Measure from the agent's side (real questions, frozen copy, 3 runs per question) before changing a live wiki.
2. A cause becomes a rule only if it shows up in at least three sessions.
3. Owner-language aliases live outside `wiki/`, so wiki pages keep one language.
4. Nothing is written to a live wiki or `CLAUDE.md` without showing the exact lines first.
5. Every claim in `docs/` says whether we measured it, or only read it.

## What is not proven

- That the search tool helps: on our wiki it made agents faster (3.2 vs 6.4 steps) but they reached the right page less often (16 vs 22 of 27). The "Finding pages" line in the template is marked unproven for that reason.
- That a hit means a correct answer. Answer correctness is not measured yet.
- Anything about wikis other than ours. Testing elsewhere is the point of this repo.

## Tests

```
python -I -m unittest discover -s tests -v     # stdlib only, no network, no model
```

Running the bench or `gen_aliases.py` calls `claude -p` and spends subscription: about $0.01 per question per run with Haiku.
