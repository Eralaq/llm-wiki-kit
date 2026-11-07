# Installing llm-wiki-kit

The kit is plain Python and Markdown. There is nothing to compile and no package to install.

## 1. Requirements

| Need | For what | Notes |
|---|---|---|
| Python 3 | every tool and `install.py` | Standard library only. Tested on Python 3.12; older 3.x versions are likely fine but untested. |
| git | getting the kit | Optional: a ZIP download works too (step 2). |
| [Claude Code](https://claude.com/claude-code) CLI (`claude`) | only `run_bench.py`, `gen_aliases.py`, `run_improver.sh` | These call `claude -p` and spend your subscription, about $0.01 per question per run with a small model. `wiki_miner`, `wiki_search`, `eval_search`, `mine_sessions` and `install.py` need no model and no network. |

## 2. Get the kit

```
git clone https://github.com/Eralaq/llm-wiki-kit.git
cd llm-wiki-kit
```

No git: open https://github.com/Eralaq/llm-wiki-kit, press Code, Download ZIP, and unpack it.

Mirror: `https://git.ctll.ru/Babylen/llm-wiki-kit.git` (`git clone` works without an account; that server asks for a sign-in on its web pages, API and ZIP links, so give people the GitHub address).

## 3. Check it works here (no network, no model)

```
python -X utf8 -I -m unittest discover -s tests -v
```

All tests should pass (22 at the time of writing; the ruff test is skipped when `ruff` is not installed). Use `-X utf8`, not the `PYTHONUTF8` variable: `-I` ignores every `PYTHON*` environment variable. The tools themselves no longer crash on a legacy console encoding such as cp1251 (`install.py` prints `?` for characters the console cannot show; the other tools write UTF-8), and a test covers it.

## 4. Put it into a project

Dry run first: it prints every file it would write and changes nothing.

```
python install.py --target /path/to/your/project --project "My project" --scope "what the wiki covers" --tools --dry-run
```

Then the real thing:

```
python install.py --target /path/to/your/project --project "My project" --scope "what the wiki covers" --tools --skills project
```

What you get in the project:

| Path | What |
|---|---|
| `CLAUDE.md` | The wiki constitution with your project name filled in. If the project already has a `CLAUDE.md`, yours is left untouched, the template is written to `CLAUDE.template.md`, and a diff is printed. |
| `wiki/index.md`, `wiki/log.md`, `wiki/_page-template.md` | Skeleton files. Existing files are skipped. |
| `aliases.example.json` | Format of the alias file (copy it to `aliases.json`, keep it outside `wiki/`). |
| `tools/` | With `--tools`: the measurement, search, lint and judge scripts. |
| `.claude/skills/` | With `--skills project`: `wiki-peek`, `code-peek`, `source-code-context`. Use `--skills global` to put them in `~/.claude/skills/` for all projects. |

`install.py` never overwrites a file and asks for confirmation (use `--yes` to skip). To undo, delete the files it listed.

`skill-factory` and `skill-hub` are not installed by `install.py`: their text describes our own environment. See `skills/README.md`.

## 5. First measurements (free)

From the project root, with the wiki in `wiki/`:

```
python tools/wiki_miner.py --wiki wiki --out out/miner
python tools/mine_sessions.py --src ~/.claude/projects/<your-project-folder> --out out/sessions
```

`wiki_miner` reads your Claude Code session transcripts and reports how agents moved through the wiki. Open `out/miner/report.md`. It also writes `out/miner/questions.json`, the raw material for a question set.

## 6. Measure whether agents find the right pages (spends subscription)

Follow `bench/README.md`: build 25 to 30 real questions with their right pages, then

```
python tools/run_bench.py --wiki . --snapshot /tmp/wiki-snap --gold bench/questions.json --out out/A --pick 1,2,3
```

Run each variant three times and change one thing at a time. The result files are `bench.json` and `bench.md`.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `UnicodeEncodeError` on Windows | Set `PYTHONUTF8=1`. |
| `claude` not found | Install Claude Code and make sure `claude` is on `PATH`; only the bench, alias generation and the session improver need it. |
| Bench runs return 0 steps | The model call failed (usage limit or an HTTP 403 for an unsupported network). Look at `answer` in `bench.json`; do not read zeros as results. |
| `wiki_miner` finds 0 sessions | It reads `~/.claude/projects/*/*.jsonl`; pass `--src` if your transcripts are elsewhere. A project has to have been worked on with Claude Code and touched the wiki for there to be anything to find. |
| `CLAUDE.md` was not replaced | By design. Compare it with `CLAUDE.template.md` and merge by hand. |

## Status

v0.2. It grew out of one project's wiki (559 pages). The first outside run by another agent found real defects (silent zeros at a usage limit, hits counted only for `Read`, a crash on a cp1251 console); v0.2 fixes them and adds `wiki_lint`, `judge_answers`, split question sets and alias hashes. None of the search-quality claims is proven yet: see `docs/related-work.md` for how others measure and `docs/roadmap.md` for what is still open.
