# Bench agent prompt

**Used by**: `tools/run_bench.py` (one fresh agent per question)
**Model**: claude-haiku-5-5 by default, tools Read/Grep/Glob (plus Bash with `--search` or `--shell`; read-only shell commands such as `cat` and `grep` then run too, the allow-list does not prevent it)

`{q}` is replaced by the question. The prompt deliberately does not say where to look: finding the page is what is being measured. Asking for a closing "Pages used:" line makes answers checkable. It does not check that the answer is correct (not measured yet, see docs/roadmap.md).

## Prompt

````text
Answer the question below using only this wiki (the current folder). Follow the folder's CLAUDE.md. Find the pages that matter, read them, and answer briefly in the language of the question. End with a line 'Pages used:' listing the wiki pages you relied on.

Question:
{q}
````
