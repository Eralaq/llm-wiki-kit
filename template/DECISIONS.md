# Decisions: where 14 diverging wikis disagreed

Compared the `CLAUDE.md` of 14 of our own wikis (labelled A to N below; project names are removed in the public copy) plus one wiki's style guide, its real `index.md` / `log.md`, and the 2026-11-05 retrieval bench. Nine of them share one Karpathy boilerplate that differs by a few lines; the differences are listed below.

| # | Topic | Variants seen | Chosen | Why |
|---|-------|---------------|--------|-----|
| 1 | Wiki language | English only, no exceptions (wiki A, wiki H, wiki G, wiki E, wiki I, wiki M); English with verbatim Russian quotes (wiki D); Russian allowed for Russian-source summaries (wiki L); user scripts and raw may be any language (wiki N); legal folder in Russian (a style guide) | One setting, `{{WIKI_LANGUAGE}}`, default English. Only exceptions: verbatim quotes and data literals | A single language keeps search and lint simple; exceptions that are folders or whole page types (legal, call summaries) are project choices, added by hand |
| 2 | Language of log and index | Explicitly English (wiki E, wiki G, wiki F, wiki M) vs silent (most) | Same language as pages | A mixed log breaks grep |
| 3 | What "raw/" allows | "immutable, never modify" (most); "human-only zone, never create, copy or move" (wiki B); a sync script copies recordings into raw (wiki E) | Human-only zone; the agent only reads on ingest or on request | The strictest wording is the only one that cannot be read two ways. A script-fed raw is a project exception to document by hand |
| 4 | Where to start answering | "Read index.md first" (all 14); bench: agents rarely did so, search tool made runs faster (3.2 vs 6.4 steps) but hit the right page less often (16/27 vs 22/27) | Search tool first if it exists, read top 3, then grep; index is the fallback map; marked unproven | Bench is one run on one wiki with a small model; the tension (faster but trusts the top hit) is why the rule says "do not stop at the first hit" |
| 5 | Permission to edit | Free to edit when asked to ingest (base); "no action without explicit confirmation", exploratory questions are chat-only (wiki B, user global) | Write only when asked; questions are chat-only; offer to save an answer, save after agreement | Prevents unrequested wiki churn; keeps the base ingest rule "discuss before writing" |
| 6 | Git commit, push, deploy | Never (user memory); only with the named action in that message (wiki B); only through a project script (wiki F, wiki C); `master` not `main` (wiki F) | Never unless asked in that message; never `Co-Authored-By` | The project-specific scripts and branch names do not belong in a generic template; each project adds its own line |
| 7 | Citation format | `(source: filename.pdf)` (base); `filename` (wiki H); `filename.md` (wiki N); `wiki C/<path>` for code (wiki C) | `(source: exact/path)`, source may be a raw file or a project file | Exact paths (wiki C rule) let a reader jump straight to the source; works for code-based wikis |
| 8 | Answer citation | "Cite specific wiki pages" without a format | `(wiki: page-name)` | One greppable format |
| 9 | Page-format strictness | "should follow" (all CLAUDE.md); "missing any field is a lint error" (a style guide) | Required; lint checks it | A format that is optional drifts |
| 10 | Log entry format | "date, source name, what changed" (CLAUDE.md); `## [YYYY-MM-DD] type \| title` with types ingest/fix/update/docs (style guide); real log also uses incident, analysis, verification | `## [YYYY-MM-DD] type \| title`, open list of types | The real log outgrew the four types; the heading format is greppable |
| 11 | Index row format | Table `\| [[page]] \| description \|` under 120 chars plus a revision counter (style guide); long multi-sentence rows with bold dates (wiki A real index) | Table rows, one line under 120 characters, no revision counter | Long rows made the index too big to be a map; date tracking lives in the log |
| 12 | Orphans | Lint lists orphans (all); style guide also makes an orphan a creation-time error | Every new page needs one inbound link; lint also finds dead links and index mismatches | Cheap to enforce at write time |
| 13 | Purpose text | Three wikis still say "planning a trip to Japan" (copied boilerplate); wiki G keeps a "Legacy" section for another project; wiki F covers four projects | Placeholder purpose; one wiki, one project | Copy-paste leftovers mislead the agent; mixed-topic wikis dilute search |
| 14 | Style of detail | "Plain language" (all); "be detailed and explicit about file locations" (wiki C) | Both | Compatible, wiki C rule is the stronger half |
| 15 | Encoding | About half of the files carry a byte-order mark and zero-width characters at line starts (copy artifact) | Plain UTF-8, no BOM, no invisible characters | They break headings and grep |
| 16 | Secrets in the wiki | one project's `CLAUDE.md` held a credential in clear text (not copied here); others point to a credentials page | No secrets in the wiki; point to where they live | Clear-text secrets in a doc that is read into every prompt |
| 17 | PM folder and file prefixes | `PM/` with project-specific file prefixes in some, no prefix in others; PM Russian-allowed (wiki E) | Not in the template | Product management is not wiki structure; a project that has it documents it in its own section |
| 18 | `_page-template.md` file name | Style guide forbids underscores in page names | Keep the underscore for the template file only | The underscore sorts it first and marks it as not a real page; search tools and lint should skip it |

## Removed as project-specific

Server access and credentials; deploy scripts and their rules; repository layout and branch schemes of individual projects; pointers to other products; hardware and speech-recognition notes; call-recording sync and test-data rules; "never edit this one file" rules; skill-path notes for design tools; PM naming overrides. Each project keeps these in its own section.

## Open

- Whether a `Finding pages` rule should name the search tool or only describe the behavior is not settled by the bench.
- Where a project keeps `aliases.json` when the wiki is a subfolder of a larger repo: the template assumes the wiki root.
