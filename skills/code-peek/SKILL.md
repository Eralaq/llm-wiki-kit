---
name: code-peek
description: Looks at a big source file in small pieces - the outline of its functions, classes and methods with line ranges and sizes, then the body of just the one you need - instead of reading the whole file. Use when you are about to open a file over ~300 lines (Python, JS/TS, Vue, Rust, Go, shell, Markdown), the user says look at this file, what is in this file, find the function, show the method, how does X work in this file, посмотри файл, что в этом файле, покажи функцию, найди метод, как устроен файл. Do NOT Read or cat a large file in full just to find one function. Don't use for - editing (edit normally), searching many files (grep).
---

# code-peek

Why: a 40 KB file is ~10k tokens, and every later step of the session pays for them again. The outline is 0.3-1k, one function 0.2-1k.
Call as one plain command with the FULL path, no `cd`, `&&`, pipes: `python3 -I -X utf8 ~/.claude/skills/code-peek/scripts/code.py <command>`. Stdlib only, read-only.

## Order of work
1. `outline FILE` - every function, class and method as `L<start>-<end> kind name (lines)`, nested by indentation, plus the file's size in lines and tokens. Pick the entry you need.
2. `show FILE NAME` - the body of that entry (`NAME` or `Class.method`). If two entries share a name it lists them; pick with `--at LINE`.
3. Need the code around it or a range? `Read` with `offset` and `limit` (never without them on a large file). Need a string or a usage across files? `grep -n`.

## Rules
- A file under ~300 lines can simply be read. Above that, outline first; read the whole file only when you really must change most of it, and then once.
- Python is exact; JS/TS/Vue/Rust/Go/shell use patterns plus brace matching: if a range looks wrong, `Read` that region with `offset`/`limit`.
- Before you edit a function, `show` it to copy its exact text; the edit still needs the file read by your editing tool if it demands it, but that read can be a small `offset`/`limit` one.
- Do not `cat a b c` several files: outline each, or `grep -n` the name over them.
- Keep what you learned: do not outline or show the same entry twice in a session unless the file changed.
