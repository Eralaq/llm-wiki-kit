# Bench: does an agent find the right page?

1. Collect 25-30 real questions, in the words the owner really uses, each with the page(s) that answer it. Take them from real sessions, not from the wiki: `tools/wiki_miner.py` writes `questions.json` (prompts whose answer needed wiki pages) and `tools/add_context.py` adds the task around a question.
2. Fix the right pages by reading the page, not by trusting what the agent opened. In our first set the agent had opened a wrong page for one question and missed an exact page for another.
3. Save as JSON (see `examples/questions.example.json`). A hit means ANY listed page was opened.
4. Freeze a copy of the wiki (`run_bench.py` does this) and run each variant 3 times; one run per question is noisy.
5. Compare variants on hits, steps and input tokens. A hit is not a correct answer; check answers too (planned, see `docs/roadmap.md`).

```
python tools/run_bench.py --wiki <project-root> --snapshot <tmp dir> --out out/A --gold bench/questions.json --pick 1,2,3
python tools/run_bench.py --wiki <project-root> --snapshot <tmp dir> --reuse-snapshot --search --aliases aliases.json --out out/C --gold bench/questions.json --pick 1,2,3
```

Offline and free: `tools/eval_search.py --wiki <project>/wiki --gold bench/questions.json [--aliases aliases.json]` prints the rank of the first right page for the search tool alone.

Cost guide (Haiku, our wiki): about $0.01 per question per run.

Sandbox: the agent runs with `--permission-mode dontAsk` and an allow-list (Read, Grep, Glob; with `--search` also `python tools/wiki_search.py`). It works in a frozen copy, but the copy is not an OS-level sandbox: read-only tools can still read paths outside it, so do not run the bench on a wiki folder that sits next to secrets you would not show the model.
