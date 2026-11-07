# How others implement the pattern and how they evaluate retrieval (read 2026-11-07)

Method and limits: web search plus reading the pages below. For most projects I read a description or an article about them, not their source code or closed issues, so "what people broke" is mostly unknown. Star counts and the list of "17+ implementations" come from one review article that gives no benchmarks. Treat every row as a lead to check, not as a verified fact about the code.

## Evaluation work (the part we learned most from)

| Source | Setup | What they measure | What we took |
|---|---|---|---|
| [Taktile, LLM Wiki for agent memory](https://taktile.com/blog/llm-wiki-agent-memory) | 88 entries, 24 queries with gold labels (how they were chosen is not explained) | recall, hit-rate and "junk" (non-gold entries retrieved) at K = 3, 5, 10; methods grep, SQLite FTS5 BM25 with Porter stemmer, vectors, LLM judgment over index.md, and an LLM+vector hybrid by reciprocal rank fusion | Junk as a metric (`eval_search`, `run_bench`). BM25 is a sound default. They report grep as not viable (barely a fifth of the relevant entries at K=3) and the LLM judgment as most accurate but about 150,000 times slower than BM25 |
| [sw30labs, wiki vs RAG](https://github.com/sw30labs/.github/wiki/wiki-vs-rag.stub) | 89 pages, 30 questions written by a model from the corpus, 4 retrieval arms | answer quality 1 to 5 by an LLM judge, head-to-head wins, losses and ties, tokens, dollars | Pairwise comparison and cost reporting. Their own result is mostly ties, so the differences are within noise. A hybrid retriever with reranking scored leaf pages above overview pages and lost badly on questions that need a topic overview: the same shape as our "agent trusts the top hit and the overview page was not first" |
| [LangChain, WikiBench](https://www.langchain.com/blog/evaluating-openwiki-with-wikibench) | Wikis generated for code repositories; a reader agent answers generated questions | a JSON rubric of required facts per question; two LLM judges: is the fact in the answer, is it grounded in the pages the agent read | The rubric and the two judges: this is what `judge_answers.py` does. Their finding that wiki plus source beats either alone, and that a wiki alone is much worse, matches the idea of a wiki as an index |

Not read in full: the LLM-WikiRace paper (arXiv 2602.16902) tests link navigation on Wikipedia, not retrieval from a project wiki, so we did not use it.

## Implementations of the pattern

| Project | What it does differently | Evaluation or lint it reports | What we took |
|---|---|---|---|
| [Karpathy's gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | The idea file: raw sources, wiki, schema; ingest, query, lint | Names lint checks: contradictions, stale claims, orphans, missing pages and cross-references, data gaps. Says the index works at moderate scale (about a hundred sources) and that real search is wanted later, naming `qmd` as an option. Gives no threshold | The lint list became `wiki_lint.py` (the structural part: it cannot find contradictions) |
| [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) | An agent skill for several tools; deliberately leaves out hashes, confidence scores, decay, vector and graph search | Lint of index integrity, links and stale cross-references. No benchmark. Says it would add search only if recall measurably drops | The rule "add search only when measurement says so", which is our "unproven" stance |
| Ar9av/obsidian-wiki (via [a review](https://srisatyalokesh.is-a.dev/learn-ai/best-llm-wiki-community-implementations/)) | A validation layer after every model write: broken wikilinks, missing front matter, entity pages naming nonexistent sources | None measured | The check list for `wiki_lint.py`. Running it after every agent write is the open idea |
| swarmvault (same review) | Cache keyed by a semantic hash; deterministic contradiction detection across sources | None measured | The hash idea, as the page hash in `gen_aliases.py` |
| [rohitg00, LLM Wiki v2](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2) | Confidence scores, superseded claims kept and marked, forgetting curves, hybrid search, self-healing lint | No metrics for these mechanisms | Nothing yet. "Mark a claim stale instead of deleting it" is already on our roadmap |
| atomicmemory/llm-wiki-compiler (our copy: `sources/llm-wiki-compiler`; the origin account name differs between our note and the review, check it) | Compiles sources into a wiki in one command, incremental runs | No lint or benchmarks reported | See `docs/imported-ideas.md` |
| roomi-fields/rtfm (same review) | Hybrid FTS5 and semantic search as an MCP server | "Tested on a 1,700-file vault", no figures | Only as a scale reference |

I found nobody who mines real working sessions for questions or repeats runs to estimate noise. That is not proof nobody does; it is what the sources I read contain.

## What changed in our kit because of this

1. `eval_search.py` and `run_bench.py` report **junk**, `eval_search` reports recall at several k.
2. `judge_answers.py` measures correctness with an owner-written fact checklist and two judges.
3. `wiki_lint.py` implements the structural checks named by Karpathy, Astro-Han and obsidian-wiki.
4. `wiki_search.py` prints a note when several results score close to the top, and has `--hub-boost` (off by default) for the "overview page loses to a leaf page" problem. On our nine questions the boost did nothing at 0.1 and 0.15 and hurt at 0.3, so it stays off.
5. We did **not** add confidence scores, decay, graphs or hybrid vector search: nobody we read measured that they help, and neither have we.

## Unresolved

- Whether a Russian-aware stemmer helps. `wiki_search.stem_ru` exists; on our nine questions it was not better than the 5-letter prefix, and nine questions cannot settle it.
- Whether LLM judgment over the index, the most accurate method in the Taktile numbers, is worth its cost for a wiki of our size. Not tried.
