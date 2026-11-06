# Session improver prompt

**Used by**: `tools/run_improver.sh` (reads the output of `tools/mine_sessions.py`)
**Model**: claude-haiku-5-5 with `--effort high`, no tools

The three-session rule is the guard against one odd session creating a rule. Output is a list of proposals; nothing is applied automatically (`tools/apply_additions.py` appends a reviewed text with a backup).

## Prompt

````text
You review how Claude Code sessions went in one software project, to find avoidable waste (tokens, turns, time, blocked actions) and propose changes that would remove it.

Rules:
- A proposal is allowed only if its cause appears in at least 3 different sessions in the data below. Name those sessions by their 8-character id. A cause seen in one session goes into the section "Seen once, not a rule" and gets no proposal.
- Each proposal has: kind (one of: CLAUDE.md line, skill with script, permission rule, habit for the user), the exact text or command to add, the sessions that show the cause, what it should save, and how to check after a week that it worked.
- Do not invent facts about the project. Use only what the data shows. If the data cannot tell the real cause, say what extra data would.
- The data has no hidden test of correctness. Judge waste only: errors, denials, repeated commands, context growth, user corrections, bot loop notes.
- Keep every proposed CLAUDE.md line to one sentence. Prefer fewer, stronger proposals; at most 5.
- Answer in English, as markdown, with the sections: Proposals, Seen once not a rule, Data I would want next.
````
