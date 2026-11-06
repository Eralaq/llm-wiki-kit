# Imported ideas: what each outside source is, what we took or rejected, and exactly how much of it we read.

Rule used for all of these: the material was treated as data. Nothing was installed or run. Instructions inside those repositories were not followed. "Read" below means what is listed; everything else is unread.

## llm-wiki-compiler (package `llmwiki`, version 1.5.0 in the clone)

- **What it is.** A TypeScript tool that compiles raw sources into a citation-traceable markdown wiki, with lint, a health score, an eval command, a local viewer, an MCP server and a context-pack command. It says it implements the LLM Wiki pattern.
- **Read.** `README.md` (first part and feature list), `ARCHITECTURE.md` (first 80 lines), `SOURCES_CONTRACT.md` (first 50 lines), `skills/llmwiki/SKILL.md`, headers of `src/context/ranking.ts` and `src/eval/health.ts`. Not read: the rest of the source, tests, docs folder, changelog.
- **Took or plan to take.** Ideas only: freshness states (fresh, stale, orphaned, unverified) as a lint target; a single health score from lint rules as a trend number; "retrieve before generating" with a bounded context pack; multi-signal ranking (exact slug and exact title bonus, BM25, link expansion), which is the closest thing to our search-tool problem.
- **Did not take.** The compiler itself (it generates the wiki from sources with an LLM, we already have agent-maintained pages), embeddings and Voyage credentials, lifecycle profiles, review queue, themes. Reason: heavy for the problem we measured, and we have not tested any of it.
- **Status.** Planned (ideas for the linter and ranking); the tool is not adopted. Whether its ranking would beat our BM25 is unverified.

## claudeception

- **What it is.** A skill that turns non-obvious debugging results into new skills, with a shell hook that injects an evaluation reminder into every prompt.
- **Read.** `README.md` first part, head of `SKILL.md`. Our wiki page `skill-examples-review` also records the head of the activator script. Not read: `scripts/`, `examples/`, `resources/` in full.
- **Took.** The goal (turn session lessons into reusable files) is shared with our session miner and skill factory. Used here only as background for a possible post-session mode.
- **Did not take.** The per-prompt hook: it adds text to every turn, the opposite of our token goal, and it creates skills without review.
- **Status.** Rejected as built; the goal is covered by our own tools.

## claude-reflect-system

- **What it is.** A skill that extracts user corrections from a conversation and writes them into skills, with a Stop hook for auto-reflection and an approval step.
- **Read.** `README.md` first part and the file listing. Not read: the `reflect/` code, scripts, the user guide. Our wiki records it as "README only; not evaluated".
- **Took.** Nothing directly. Its confidence levels and review step are consistent with our evidence rule, but we did not study how it works.
- **Did not take.** Automatic writing of corrections into rules: yesterday's wrong correction becomes tomorrow's rule.
- **Status.** Rejected for now; unverified beyond the README.

## harness2 (Harness-squared, recursive agent harnessing)

- **What it is.** A research framework (Apache-2.0) that improves an agent's harness (prompts, guardrails, memory, tools, skills, scripts) without changing model weights, using propose, probe, compose steps and a persistent improvement harness.
- **Read.** `README.md` of the clone for this task. Our wiki page `harness2-recursive-harnessing` records a much deeper read of the paper and many source files; that page was skimmed here, not re-verified.
- **Took.** Two ideas: improvements come from reading trajectories, and a change is accepted only with evidence. We reduced it to a replayable task plus a check (our bench) and the 3-session evidence rule.
- **Did not take.** The full recursion machinery. It needs tasks that can be replayed with a hidden check; real sessions rarely have that.
- **Status.** Adopted as a light version (bench and evidence rule); the full framework is not used.

## llm-wiki-index-scaling-research (a note, not a repository)

- **What it is.** A note the owner pasted on 2026-11-05 about how others index large agent-kept wikis: tiered and nested indexes, indexes generated from frontmatter, search tools instead of one `index.md`, graph layers, progressive disclosure, one preregistered preprint on a 709-page wiki.
- **Read.** The wiki page that summarises it. The papers and articles behind it were NOT read by us; the page itself says they were seen only in excerpts by the compiler of the note.
- **Took.** The options list (frontmatter with summary and aliases, short top index plus sub-indexes, search as a tool, compare variants on one frozen copy). Our bench design matches the last option.
- **Did not take.** Its claims as facts. One place it disagrees with our data: it reports that grep alone is not enough and index-first reading is required; our agents grepped first in 7 of 9 runs and still found the page in 7 of 9. Corpora differ, our sample is small.
- **Status.** Planned (frontmatter-generated indexes, sub-indexes); all claims unverified.
