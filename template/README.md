# Wiki template

A clean starting point for an LLM-maintained wiki (Karpathy pattern). Copy it into a project, fill the placeholders, and the agent knows how to ingest, answer and lint.

## Contents

| File | Purpose |
|------|---------|
| `CLAUDE.md` | The wiki constitution the agent reads. About 5 KB, English |
| `wiki/index.md` | Table of contents skeleton |
| `wiki/log.md` | Append-only log skeleton, entry format `## [YYYY-MM-DD] type \| title` |
| `wiki/_page-template.md` | Skeleton to copy for each page. Search and lint should skip it |
| `aliases.example.json` | Format of the optional search aliases |
| `DECISIONS.md` | Where the old wikis disagreed and what this template chose |

`raw/` is not shipped (it is the owner's, and is empty at the start); `install.py` creates it.

## Placeholders to fill

| Placeholder | Where | Meaning |
|-------------|-------|---------|
| `{{PROJECT}}` | `CLAUDE.md`, `wiki/index.md`, `wiki/log.md` | Project name |
| `{{ONE_LINE_SCOPE}}` | `CLAUDE.md` | What the wiki covers, one line |
| `{{WIKI_LANGUAGE}}` | `CLAUDE.md` | Language of pages, index and log. Default English |
| `YYYY-MM-DD` | `wiki/index.md`, `wiki/log.md` | Today's date |

## What `install.py` will do

Planned, not written yet:

1. Ask for the target folder, project name, scope line and wiki language.
2. Copy this template there and replace the placeholders.
3. Create an empty `raw/`.
4. Copy `aliases.example.json` to `aliases.json` if absent.
5. Optionally copy `tools/wiki_search.py`. Without it, the "Finding pages" section falls back to grep.
6. Refuse to overwrite an existing `CLAUDE.md` or `wiki/` unless told to.

It will not run git, commit or push.

## Notes

- Owner-language aliases and sample questions go to `aliases.json`, never into pages.
- A project with extra rules (deploy scripts, PM folders, access notes) adds its own section to `CLAUDE.md`, and keeps secrets out of it.
- The "Finding pages" rule is a candidate, not a proven one; see `DECISIONS.md` row 4.
