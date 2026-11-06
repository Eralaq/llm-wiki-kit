# Alias and question generation prompt

**Used by**: `tools/gen_aliases.py` (batches of 8 pages)
**Model**: claude-haiku-5-5, no tools

Input per page: slug, title, Summary line and up to ten section headings, nothing else, so no benchmark question can leak into the aliases. Output goes to `aliases.json` OUTSIDE `wiki/`. Known weakness: generic aliases ("email", "config") add noise to the search ranking; review the output and prune before use. Names or nicknames that appear nowhere in the page text cannot be generated; add those by hand.

## Prompt

````text
You help a Russian-speaking developer find pages in an English-only internal wiki. For each page below write search help in RUSSIAN, as the developer would naturally say it (informal, short, how they talk to a coding assistant).
For every page return:
- "aliases": 4 to 8 Russian words or short phrases: translations of the page's key terms, everyday names and synonyms the developer might use, nicknames only if the page text itself names them. Plain nouns/verbs, no sentences.
- "questions": 3 short Russian questions or complaints this page would answer (what the developer might type when they have this problem or want this thing).
Rules: use ONLY facts in the page info; do not invent names, versions or numbers. Keep technical identifiers (file names, commands, product names) as they are. Output ONLY a JSON object {"<slug>": {"aliases": [...], "questions": [...]}, ...} for all slugs, no prose, no code fence.

PAGES:
````
