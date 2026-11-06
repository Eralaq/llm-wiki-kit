# LLM Wiki: {{PROJECT}}

A knowledge base maintained by an AI agent, based on Andrej Karpathy's LLM Wiki pattern.

## Purpose

This wiki is the structured, interlinked knowledge base for **{{PROJECT}}**: {{ONE_LINE_SCOPE}}.
The agent maintains the wiki. The human curates sources, asks questions and guides the analysis.
One wiki covers one project. Material about an unrelated topic belongs in another wiki.

## Folder structure

```
raw/          -- source documents (human-only zone, see Rules)
wiki/         -- markdown pages maintained by the agent
wiki/index.md -- table of contents
wiki/log.md   -- append-only record of all operations
aliases.json  -- optional search aliases (outside wiki/, see Language)
tools/        -- optional helpers such as wiki_search.py
```

## Ingest workflow

When the human adds a source to `raw/` and asks you to ingest it:

1. Read the full source.
2. Discuss the key takeaways with the human before writing anything.
3. Create a summary page in `wiki/`, named after the source.
4. Create or update concept pages for each major idea or entity.
5. Link related pages with `[[page-name]]` (no `.md`).
6. Update `wiki/index.md` (one line per new page).
7. Append an entry to `wiki/log.md`.

One source may touch 10-15 pages. That is normal. Every new page needs at least one inbound link.

## Page format

Copy `wiki/_page-template.md`. Every page has, in this order: `# Title`, `**Summary**` (1-2 sentences), `**Sources**`, `**Last updated**` (YYYY-MM-DD), a `---` line, the body, and `## Related pages`. A missing field is a lint error.

Citation rules:
- Cite every factual claim as `(source: exact/path/to/file)`. Give exact paths, not vague pointers. A source may be a file in `raw/` or a file in the project's code.
- If two sources disagree, state the contradiction on the page.
- Mark a claim with no source as `[needs verification]`.
- Record the date for time-sensitive facts.

## Finding pages

<!-- unproven: see docs/our-findings.md -->
If `tools/wiki_search.py` exists, run `python tools/wiki_search.py "<question in any language>"` first and read the top 3 pages. If they do not answer the question, fall back to grep over `wiki/`. Without the tool, grep first and use `wiki/index.md` as a map. Do not stop at the first hit if it does not contain the answer.

## Question answering

1. Find pages (see Finding pages), then read them in full.
2. Answer from the pages and cite them, for example `(wiki: page-name)`.
3. If the wiki does not contain the answer, say so. Do not fill the gap from memory.
4. A valuable answer: offer to save it as a page. Save only after the human agrees.

Questions are chat-only. A question is never an order to edit the wiki.

## Lint

When asked to lint or audit, report a numbered list with a suggested fix for each:

- contradictions between pages;
- orphan pages (no inbound links) and dead `[[links]]`;
- concepts mentioned without their own page;
- claims that newer sources made outdated;
- pages that break the page format;
- index rows without a page, or pages without an index row.

## Language

- Wiki language: **{{WIKI_LANGUAGE}}** (default English). It applies to pages, headings, index and log, whatever the language of the chat or the sources.
- Allowed exceptions: verbatim quotes, and data literals (names, identifiers, code). Everything around them stays in the wiki language.
- Owner-language search words (nicknames, synonyms, how the owner actually phrases questions) do not go into pages. They live in `aliases.json` at the repo root, next to this file, as `{"page-slug": {"aliases": [], "questions": []}}`. See `aliases.example.json`.

## Rules

- `raw/` is a human-only zone. Never create, edit, copy, move or delete anything in it. Read a file only when asked to ingest it, or when asked about it.
- Write to `wiki/` only when the human asks. Do not touch files outside this repo's `wiki/` and `aliases.json` unless asked.
- After every change update `wiki/index.md` and `wiki/log.md`. Log entries are append-only; never edit old ones.
- Page names: lowercase letters, digits, hyphens (`machine-learning.md`). The only underscore file is `_page-template.md`.
- Write plain language. When unsure where something belongs, ask.
- No secrets in the wiki: no passwords, tokens, keys, private addresses. Point to where a secret lives instead.
- Do not run git commit, push or deploy unless the human asks for it in that message. Never add `Co-Authored-By` lines.
