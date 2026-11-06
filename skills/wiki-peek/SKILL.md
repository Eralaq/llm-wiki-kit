---
name: wiki-peek
description: Reads a project wiki in small pieces - find the page, see its outline, read one section, the newest log entries, grep - instead of reading index.md, log.md or whole pages. Use when the user says check the wiki, what does the wiki say, look in the wiki, is it documented, last wiki entries, update the wiki log, проверь вики, посмотри в вики, что в вики про, есть ли в вики, последние записи лога, найди страницу в вики. Do NOT Read or cat wiki/index.md, wiki/log.md or a long wiki page yourself. Don't use for - editing wiki pages (edit them normally), code search (grep the code).
---

# wiki-peek

Why: `index.md`, `log.md` and long pages are 5-60k tokens each, and every later step of the session pays for them again. These calls return 0.3-1.5k.
Call as one plain command with the FULL path, no `cd`, `&&`, pipes: `python3 -I -X utf8 ~/.claude/skills/wiki-peek/scripts/wiki.py <command>`. Stdlib only, read-only.
Run it from the project folder; with several wikis there (for example a wiki repo inside the project) put `--wiki DIR` before the command (`wiki.py --wiki DIR find ...`), where DIR holds `index.md`. The error message lists the choices.

## Order of work
1. `find WORDS...` - which pages are about it, one line each (name - summary). Use 1-3 distinctive words, not a sentence.
2. `page NAME` - a short page (up to ~1.2k tokens) is printed in full; a long one comes as an outline: each heading with its line and size.
3. `page NAME --section "Heading"` - just that section (any case, the start of the heading is enough). `--lines 40-90` for a range.
4. `tail [N]` - the newest N log entries (default 3), shortened; `--full` for more of each. It knows whether the log is newest-first or newest-last.
5. `grep WORDS...` - every line that has all the words, as `page:line: text` (25 lines at most, `--max` to change). Use it for a name, a port, a flag, an error text.

## Rules
- Do not read `index.md` or `log.md` with Read or cat, and do not read a long page in full: `find` then `page --section` does the same for a tenth of the tokens.
- Before you write a log entry, `tail 2` shows the format the log uses; copy it.
- When the wiki has nothing (`find` and `grep` both empty), say so; do not guess it is documented.
- To change a page or the log, edit the file normally; this skill only reads. The wiki's own rules (language, index and log updates) still apply.
