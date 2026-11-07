# Bench: does an agent find the right page, and answer correctly?

Two things are measured and they are not the same: whether the agent **opened the right page** (hit), and whether its **answer is right** (facts). A search tool can raise the first and lower the second. Report both, and report failed runs separately, never as misses.

## 1. Build two question sets

Each question is one JSON object (see `examples/questions.example.json`):

```json
{"id": 7, "question": "...", "gold_pages": ["page-a", "page-b"], "split": "tune", "author": "agent",
 "facts": ["a thing a correct answer must say", {"text": "another", "any": ["substring", "other spelling"]}]}
```

- `gold_pages`: the pages that answer it. A hit means ANY listed page was opened.
- `split`: `tune` or `holdout`.
- `facts`: the checklist for `judge_answers.py`. A fact is a short statement. `any` (optional) is a list of substrings for the free offline check.
- `author`: who wrote it (`owner` or `agent`), so you can see later whether the two kinds behave differently.

**Tune set** (any size): questions you may look at while adjusting aliases, the search tool or page text. Take them from real sessions: `tools/wiki_miner.py` writes `questions.json` and `tools/add_context.py` adds the task around a question. The miner output is raw: expect a third of it to be junk (pasted blocks, task notifications), so read it.

**Holdout set** (25 to 30 questions, the number that counts): written by the **owner** from what they ask in real work, **before looking at the wiki pages**, with the facts written by the owner too. Do not use it to tune anything. Run it once per variant (three repeats) and report it separately. If you tune on the holdout it stops being one.

Why two sets: questions written by looking at page titles are easy to find by title, and aliases tuned on them make the score look better than it is. The two wiki-retrieval write-ups with numbers that we found (see `docs/related-work.md`) use 24 and 30 questions; one does not say how its questions were chosen and the other had a model write them from the corpus. Yours should say who wrote them.

## 2. Measure

```
# offline and free: search tool alone
python tools/eval_search.py --wiki <project>/wiki --gold bench/questions.json --aliases aliases.json --split tune
# agent runs (spends subscription, about $0.01 per question per run with a small model)
python tools/run_bench.py --wiki <project-root> --snapshot <tmp dir> --gold bench/questions.json --split holdout --out out/A1
python tools/run_bench.py --wiki <project-root> --snapshot <tmp dir> --reuse-snapshot --search --aliases aliases.json --gold bench/questions.json --split holdout --out out/C1
# answers
python tools/judge_answers.py --bench out/C1/bench.json --gold bench/questions.json --snapshot <tmp dir> --out out/C1/judge
```

- `eval_search`: hit@k, recall@k (share of ALL gold pages found) and junk@k (average non-gold pages in the top k) for k = 1, 3, 5.
- `run_bench`: steps, steps to the first gold page, pages opened that were not gold (junk), tokens, cost. A page counts as opened through `Read` or `wiki_search.py --show <slug>`. With `--search` the agent may run only `wiki_search.py`, so it cannot read pages another way that the bench would miss.
- **Usage limit.** When the limit is reached `run_bench` stops, saves the finished questions and exits with code 3. Run the same command with `--resume` after the reset. Runs that failed for network reasons (HTTP 403 and similar) are retried once and, if they still fail, are listed with an `error` and left out of every figure.
- `judge_answers`: per fact, is it in the answer (presence) and is it supported by the pages the agent read (grounding). Two separate model calls. It also writes `manual-sample.md`: ten random answers for a human to mark correct, partial or wrong. **Compare the judge with your marks before trusting its numbers.** `--offline` checks only facts that have an `any` list and spends nothing.

Run each variant three times (different `--out`); one run per question is noisy. The same question can pass and fail on different runs (in our baseline one question was found 1 time in 3), so a single run proves little.

## 3. Decide

A variant with a search tool counts as better than the plain wiki only if, on the holdout set, all three hold: pages found (hit) not lower, steps not higher, and **correct answers not lower** (grounded fact share and the human sample). If steps fall and correct answers fall too, the tool changed nothing useful: keep the claim "unproven" in your `CLAUDE.md`. Also run the check on a deliberately damaged copy of the wiki (titles shuffled between pages): the bench must score it worse, otherwise it is not measuring what you think.

## 4. Cost and safety

Cost guide (Haiku, our wiki): about $0.01 per question per run; the judge adds two small calls per answer.

Sandbox: the agent runs with `--permission-mode dontAsk` and an allow-list (Read, Grep, Glob; with `--search` also `python tools/wiki_search.py`). It works in a frozen copy, but the copy is not an OS-level sandbox: read-only tools can still read paths outside it, so do not run the bench on a wiki folder that sits next to secrets you would not show the model.
