# Differences from the original pattern: what the pattern gives versus what we added on top.

Caveat: we have not read Karpathy's original gist ourselves. The left column is what our wiki pages (`llm-wiki-pattern`, `llm-wiki-guide`, `andrej-karpathy-llm-wiki`) say the pattern gives. Something we list as "added" may already exist in the original or in other people's work; we only claim we did not find it in our pages.

| Area | The pattern gives | What we added | Status |
|---|---|---|---|
| Layers and files | `raw/` immutable, `wiki/` agent-owned, schema file, `index.md`, `log.md` | Nothing changed. We use it as is. | adopted |
| Operations | ingest, query, lint | A fourth activity: measuring how the reading agent behaves (see next rows) | in use |
| Measurement from the agent's side | Lint checks the wiki's own health (orphans, contradictions, stale claims). No measure of whether an agent finds a page. | A read-only miner over agent transcripts (searches with no hit, pages read together, big pages re-read, unread and unlinked pages) and a bench that replays real questions and records steps to the right page, tokens, cost | built, small sample |
| Evidence rule | Not specified in our pages | A finding counts only if it repeats in at least 3 sessions (borrowed from our session miner) | in use in the miner |
| Comparing changes | Not specified | Frozen copy of the wiki, same questions, only the changed pages differ, several runs per question | A and C measured, B not measured |
| Vocabulary gap | Index and good summaries are expected to be enough | An alias file (nicknames, owner's words, other-language words, questions a page answers), plus a search tool that weights it | draft; first result negative on hits (see our-findings) |
| Language rule | Not specified | Wiki pages stay English only, so aliases live in a side file outside `wiki/` | in use for the draft |
| Index | One catalogue, read first | Idea only: generate indexes from page frontmatter by script, tiered or per-folder; the idea came from an outside research note and is unverified | planned |
| Query path | Agent reads index, then pages | We observed agents grep first (7 of 9 baseline runs) and open the index first in 2 of 9 | observation, one wiki and one model |
| Maintenance by a person | Human curates sources, asks questions | Every change to a live wiki needs the owner's approval; generated files are drafts | policy |

What we do not add: any claim that the pattern is wrong. We measured one 559-page wiki with a cheap model; the pattern as described claims about 100 pages, and we are well beyond that.
