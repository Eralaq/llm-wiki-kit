"""
code.py - look at a source file in small pieces: the outline (every function, class and method with its line range and size),
then just the one you need. Reading a 40 KB file in full puts about 10k tokens into the context, and every later step of the
session pays for them again; the outline costs a few hundred and `show` costs only the function.

  code.py outline FILE              functions, classes, methods: L<start>-<end> kind name (lines), nested by indentation
  code.py show FILE NAME            the body of one function / class / method (NAME, or Class.method)
  code.py show FILE NAME --at 120   when several entries have that name: the one that starts at that line

Python is parsed exactly (ast). JavaScript, TypeScript, Vue, Rust, Go and shell are read with patterns and brace matching, so
the line ranges are good but not perfect on odd formatting; other files get a generic pattern. Markdown gives its headings.
Read-only, stdlib only.
"""
import argparse
import ast
import os
import re
import sys

CAP = 200       # lines printed for one `show`
MAX_ROWS = 150  # entries printed by `outline`

JS = [
    ("function", r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+(\w+)"),
    ("class", r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)"),
    ("type", r"^\s*(?:export\s+)?(?:declare\s+)?(?:interface|type|enum)\s+(\w+)"),
    ("fn", r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>"),
    ("method", r"^\s{2,}(?:(?:static|async|public|private|protected|get|set|override)\s+)*(\w+)\s*(?:<[^>]*>)?\([^)]*\)\s*(?::\s*[^{]+)?\{\s*$"),
]
RUST = [
    ("fn", r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)"),
    ("type", r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|mod|union)\s+(\w+)"),
    ("impl", r"^\s*(?:unsafe\s+)?impl(?:<[^>]*>)?\s+(.+?)\s*(?:where\b.*)?\{\s*$"),
]
GO = [
    ("func", r"^func\s+(?:\([^)]*\)\s*)?(\w+)"),
    ("type", r"^type\s+(\w+)\s+(?:struct|interface)"),
]
SHELL = [("function", r"^(?:function\s+)?(\w+)\s*\(\)\s*\{")]
GENERIC = [("def", r"^\s*(?:(?:public|private|protected|static|final|abstract|async|override|virtual|inline|extern|export)\s+)*"
                   r"(?:def|fun|func|function|class|interface|struct|enum|trait|impl|object|module)\s+(\w+)")]
KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "else", "with", "constructor_"}

LANGS = {".js": JS, ".mjs": JS, ".cjs": JS, ".jsx": JS, ".ts": JS, ".tsx": JS, ".vue": JS, ".svelte": JS,
         ".rs": RUST, ".go": GO, ".sh": SHELL, ".bash": SHELL}


def tokens(text):
    ascii_chars = len(text.encode("ascii", "ignore"))
    return round(ascii_chars / 3.5 + (len(text) - ascii_chars) / 2.0)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def python_entries(text):
    tree = ast.parse(text)
    out = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                kind = "class" if isinstance(child, ast.ClassDef) else ("async def" if isinstance(child, ast.AsyncFunctionDef) else "def")
                out.append((start, child.end_lineno, kind, prefix + child.name))
                if isinstance(child, ast.ClassDef):
                    visit(child, prefix + child.name + ".")
            elif isinstance(child, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                visit(child, prefix)

    visit(tree, "")
    return out


def brace_end(lines, i, rust=False):
    """The line where the block that opens at or after line i closes; i itself when there is no block."""
    depth, started = 0, False
    quotes = '"' if rust else "\"'`"
    for j in range(i, min(len(lines), i + 6000)):
        s, k, inside = lines[j], 0, None
        while k < len(s):
            c = s[k]
            if inside:
                if c == chr(92):
                    k += 2
                    continue
                if c == inside:
                    inside = None
            elif c in quotes:
                inside = c
            elif c == "/" and s[k + 1:k + 2] == "/":
                break
            elif c == "{":
                depth += 1
                started = True
            elif c == "}":
                depth -= 1
                if started and depth == 0:
                    return j
            k += 1
        if not started and j >= i + 3:
            return i
    return i


def pattern_entries(text, patterns, rust=False):
    lines = text.splitlines()
    compiled = [(kind, re.compile(rx)) for kind, rx in patterns]
    out = []
    for i, line in enumerate(lines):
        for kind, rx in compiled:
            m = rx.match(line)
            if m and not (kind == "method" and m.group(1) in KEYWORDS):
                out.append((i + 1, brace_end(lines, i, rust) + 1, kind, m.group(1)))
                break
    return out


def markdown_entries(text):
    lines = text.splitlines()
    heads = [(i, len(m.group(1)), m.group(2).strip()) for i, line in enumerate(lines) if (m := re.match(r"^(#{1,6})\s+(.*)$", line))]
    out = []
    for k, (i, level, title) in enumerate(heads):
        end = next((heads[j][0] for j in range(k + 1, len(heads)) if heads[j][1] <= level), len(lines))
        out.append((i + 1, end, "#" * level, title))
    return out


def vue_blocks(text):
    out = []
    for m in re.finditer(r"(?m)^<(template|script|style)\b[^>]*>", text):
        end = text.find("</" + m.group(1) + ">", m.end())
        a = text.count("\n", 0, m.start()) + 1
        b = text.count("\n", 0, end if end >= 0 else len(text)) + 1
        out.append((a, b, "block", m.group(1)))
    return out


def entries_of(path, text):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        try:
            return python_entries(text), "python"
        except SyntaxError as e:
            sys.exit(f"{path}: not valid Python ({e.msg}, line {e.lineno}); read it with offset/limit instead")
    if ext in (".md", ".markdown"):
        return markdown_entries(text), "markdown"
    rows = pattern_entries(text, LANGS.get(ext, GENERIC), rust=(ext == ".rs"))
    if ext == ".vue":
        rows = vue_blocks(text) + rows
    return sorted(rows, key=lambda r: (r[0], -r[1])), ext.lstrip(".") or "text"


def cmd_outline(path):
    text = read(path)
    rows, lang = entries_of(path, text)
    total = len(text.splitlines())
    print(f"{path}: {total} lines, ~{tokens(text) / 1000:.1f}k tokens ({lang}); {len(rows)} entries")
    if not rows:
        return print("no functions or classes found; read it with `Read` offset/limit or grep")
    stack = []
    shown = 0
    for start, end, kind, name in rows:
        while stack and stack[-1] < start:
            stack.pop()
        if shown < MAX_ROWS:
            print(f"{'  ' * len(stack)}L{start}-{end} {kind} {name} ({end - start + 1})")
            shown += 1
        stack.append(end)
    if len(rows) > MAX_ROWS:
        print(f"... {len(rows) - MAX_ROWS} more entries; use `show FILE NAME` or grep for the rest")


def cmd_show(path, name, at):
    text = read(path)
    rows, _ = entries_of(path, text)
    want = name.lower()
    hits = [r for r in rows if r[3].lower() == want or r[3].lower().endswith("." + want)]
    if at:
        hits = [r for r in hits if r[0] == at] or [r for r in rows if r[0] == at]
    if not hits:
        near = [r[3] for r in rows if want in r[3].lower()][:12]
        sys.exit(f"no entry called {name}" + (("; close names: " + ", ".join(near)) if near else "; run `outline` to see the names"))
    if len(hits) > 1:
        return print("several entries have that name; pick one with --at LINE:\n" + "\n".join(f"L{a}-{b} {k} {n}" for a, b, k, n in hits))
    start, end, kind, real = hits[0]
    lines = text.splitlines()[start - 1:end]
    print(f"# {path} L{start}-{end} {kind} {real}")
    print("\n".join(lines[:CAP]))
    if len(lines) > CAP:
        print(f"... {len(lines) - CAP} more lines; the rest is `Read` with offset {start + CAP} limit {len(lines) - CAP}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("outline")
    o.add_argument("file")
    s = sub.add_parser("show")
    s.add_argument("file")
    s.add_argument("name")
    s.add_argument("--at", type=int)
    a = ap.parse_args()
    if not os.path.isfile(a.file):
        sys.exit(f"no such file: {a.file}")
    if a.cmd == "outline":
        cmd_outline(a.file)
    else:
        cmd_show(a.file, a.name, a.at)


if __name__ == "__main__":
    main()
