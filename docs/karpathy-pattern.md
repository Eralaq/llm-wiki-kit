# The LLM Wiki pattern: what it is, why it works, and where it is known to strain.

Source status: we have NOT read Karpathy's original gist ourselves. This page restates what our own wiki pages record about it (`andrej-karpathy-llm-wiki`, `llm-wiki-pattern`, `llm-wiki-guide`, `karpathy-yt-transcript`, all dated 2026-04-29, built from clipped copies of his post, a long-form write-up of the pattern, and a video transcript). Where a claim is ours, it says so.

## The pattern

Instead of re-discovering knowledge from raw files on every query (plain RAG), an LLM agent builds and maintains a persistent, interlinked markdown wiki between the human and the raw sources. Cross-references are pre-computed, contradictions flagged at write time, synthesis pre-built. (source: wiki page `llm-wiki-pattern`)

Three layers:

| Layer | Owner | Content |
|---|---|---|
| `raw/` | Human | Immutable source documents. The agent reads, never edits. |
| `wiki/` | Agent | Summaries, entity and concept pages, comparisons, synthesis. |
| Schema (for example `CLAUDE.md`) | Co-evolved | Conventions, page format, workflows. |

Two special files:

- `index.md`: a catalogue of every page, one line each, read first for any query. The write-up says it works without embedding search at around 100 pages.
- `log.md`: append-only, with a consistent prefix such as `## [YYYY-MM-DD] op | title` so it can be grepped.

Three operations:

1. **Ingest.** A new source goes into `raw/`; the agent reads it, writes a summary page, updates related entity and concept pages, flags contradictions, updates `index.md`, appends to `log.md`. One source commonly touches 10 to 15 pages.
2. **Query.** The agent reads `index.md`, opens relevant pages, answers with citations. Good answers are filed back as pages so exploration compounds.
3. **Lint.** Periodic health check: orphan pages, missing cross-references, contradictions, stale claims, gaps.

The tweet-level summary also mentions: Obsidian as the viewer, a naive search engine Karpathy vibe-coded over the wiki (usable by a human or by an LLM through a CLI), and a size of roughly 100 articles and 400K words where Q&A works without RAG infrastructure. (source: `andrej-karpathy-llm-wiki`)

## Why it works

Stated in the sources: people abandon wikis because maintenance grows faster than value; an agent does not get bored and can update 15 files in one pass, so maintenance cost drops near zero. The video adds four principles: explicit (no hidden embeddings), yours (local files), file over app, bring your own AI. (source: `llm-wiki-guide`, `karpathy-yt-transcript`)

## Where it is known to strain

1. **Index size.** One flat `index.md` stops fitting the context as pages grow. A research note we hold puts the practical limit of a single index at about 200 pages and says the most common complaint in discussions is the index not fitting at thousands of pages. That note was brought to us by the owner; the papers in it were seen only in excerpts and we verified none of it. (source: `llm-wiki-index-scaling-research`). Our wiki has 559 pages and a 120 KB `index.md`.
2. **Vocabulary gap.** The agent searches with words from the question. If the owner says "groups" and the wiki says "combos" and "tiers", or a bot's nickname appears only on other pages, the right page is not found. This is an observation from our bench, not a claim from the pattern. (source: `wiki-retrieval-bench`; details in [our-findings.md](our-findings.md))
3. **Staleness.** Lint is described as a periodic job, and the research note names resolution of stale facts as needed at scale. Our own bench also showed that gold pages can change during the very task that asked about them, so a wiki is a moving target. (source: `llm-wiki-index-scaling-research`, `wiki-retrieval-bench`)
4. **Overlapping pages.** After many ingests several pages can describe the same mechanism. In our bench, one update question needed four of five overlapping pages. (source: `wiki-retrieval-bench`)

Hypothesis (ours, untested beyond one wiki): the pattern's index-first query flow is not what agents actually do; in our data they mostly search first. See [our-findings.md](our-findings.md).
