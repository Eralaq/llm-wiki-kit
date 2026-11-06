"""
wiki.py - read a Markdown wiki in small pieces instead of whole files. The index, the log and long pages are big; reading
them in full puts thousands of tokens into the context that every later step pays for again.

  wiki.py find WORDS...                 which pages are about it: one line per page (name - summary)
  wiki.py page NAME                     a short page in full; a long one as an outline (headings with sizes)
  wiki.py page NAME --section HEADING   one section (the heading text or its start, any case)
  wiki.py page NAME --lines 40-90       a range of lines
  wiki.py tail [N]                      the newest N log entries (default 3), shortened; --full for more of each
  wiki.py grep WORDS...                 lines that contain all the words, as page:line: text (--max 25)
  wiki.py --wiki DIR <command>          the wiki folder (the one with index.md), before the command; found from the current folder when omitted

Works with any layout of index.md and log.md: pages are described by their own title and `**Summary**` line, and the log
order (newest first or last) is detected from its dates. Read-only, stdlib only.
"""
import argparse
import glob
import os
import re
import sys

SMALL_PAGE = 1200       # tokens: a page this short is printed in full
SECTION_CAP = 200       # lines printed for one section or range
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def tokens(text):
    ascii_chars = len(text.encode("ascii", "ignore"))
    return round(ascii_chars / 3.5 + (len(text) - ascii_chars) / 2.0)


def find_wiki(arg):
    if arg:
        for d in (arg, os.path.join(arg, "wiki")):
            if os.path.exists(os.path.join(d, "index.md")):
                return d
        sys.exit(f"no index.md in {arg}")
    env = os.environ.get("WIKI_DIR")
    if env and os.path.exists(os.path.join(env, "index.md")):
        return env
    found = sorted(set(glob.glob("wiki/index.md") + glob.glob("*/wiki/index.md")))
    if not found:
        sys.exit("no wiki found here: run from the project folder or pass --wiki DIR (the folder with index.md)")
    if len(found) > 1:
        sys.exit("several wikis here, pass --wiki DIR with one of: " + ", ".join(os.path.dirname(f) for f in found))
    return os.path.dirname(found[0])


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def pages(root):
    out = {}
    for path in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        name = os.path.relpath(path, root)[:-3].replace(os.sep, "/")
        if name not in ("index", "log"):
            out[name] = path
    return out


def head(text):
    """(title, one-line summary) from the page's own first lines."""
    title, summary = "", ""
    for line in text.splitlines()[:25]:
        s = line.strip()
        if not title and s.startswith("# "):
            title = s[2:].strip()
        elif not summary and s.lower().startswith("**summary**"):
            summary = re.sub(r"^\*\*summary\*\*:?\s*", "", s, flags=re.I)
        elif title and not summary and s and not s.startswith(("#", "**", "---", ">", "|", "```")):
            summary = s
    return title, re.sub(r"\s+", " ", summary)


def cut(s, n):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def cmd_find(root, words):
    words = [w.lower() for w in words]
    rows = []
    for name, path in pages(root).items():
        text = read(path)
        title, summary = head(text)
        low = text.lower()
        field = (name + " " + title + " " + summary).lower()
        hit_all = all(w in low or w in name.lower() for w in words)
        score = sum(5 * (w in name.lower()) + 3 * (w in title.lower()) + 2 * (w in summary.lower()) + min(low.count(w), 5) for w in words)
        if score and (hit_all or any(w in field for w in words)):
            rows.append((hit_all, score, name, title, summary, low))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    if not rows:
        print("no page matches; try other words or `grep`")
        return
    if not rows[0][0]:
        print("(no page has all the words; closest first)")
    for hit_all, score, name, title, summary, low in rows[:10]:
        print(f"{name} - {cut(summary or title, 150)}")
    if len(rows) > 10:
        print(f"... {len(rows) - 10} more; narrow the words")


def resolve(root, name):
    allp = pages(root)
    key = name.lower().removesuffix(".md").strip("[]")
    exact = [n for n in allp if n.lower() == key]
    if exact:
        return exact[0], allp[exact[0]]
    part = [n for n in allp if key in n.lower()]
    if len(part) == 1:
        return part[0], allp[part[0]]
    sys.exit(("several pages match: " + ", ".join(part[:12])) if part else f"no page called {name}; use `find`")


def headings(lines):
    out = []
    infence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            infence = not infence
        m = None if infence else re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def section_end(hs, k, total):
    level = hs[k][1]
    for j in range(k + 1, len(hs)):
        if hs[j][1] <= level:
            return hs[j][0]
    return total


def show(lines, a, b):
    chunk = lines[a:b]
    if len(chunk) > SECTION_CAP:
        print("\n".join(chunk[:SECTION_CAP]))
        print(f"... {len(chunk) - SECTION_CAP} more lines; use --lines {a + SECTION_CAP + 1}-{b}")
    else:
        print("\n".join(chunk))


def cmd_page(root, name, section, rng):
    real, path = resolve(root, name)
    text = read(path)
    lines = text.splitlines()
    hs = headings(lines)
    if rng:
        a, _, b = rng.partition("-")
        a, b = max(int(a), 1), int(b or a)
        return show(lines, a - 1, b)
    if section:
        want = section.lower().lstrip("# ").strip()
        for k, (i, level, title) in enumerate(hs):
            if title.lower().startswith(want) or want in title.lower():
                return show(lines, i, section_end(hs, k, len(lines)))
        sys.exit("no such heading; the headings are: " + "; ".join(t for _, lv, t in hs if lv <= 3)[:600])
    total = tokens(text)
    if total <= SMALL_PAGE:
        return print(text.rstrip())
    title, summary = head(text)
    print(f"{real}: {len(lines)} lines, ~{total / 1000:.1f}k tokens. {cut(summary, 200)}")
    print("Headings (line, size) - read one with --section HEADING or --lines A-B:")
    for k, (i, level, t) in enumerate(hs):
        if level <= 3:
            size = tokens("\n".join(lines[i:section_end(hs, k, len(lines))]))
            print(f"{'  ' * (level - 1)}L{i + 1} {t} (~{size})")


def log_entries(text):
    parts = re.split(r"(?m)^(?=## )", text)
    return [p for p in parts if p.startswith("## ")]


def cmd_tail(root, n, full):
    log = os.path.join(root, "log.md")
    if not os.path.exists(log):
        sys.exit("no log.md in this wiki")
    entries = log_entries(read(log))
    if not entries:
        return print("the log has no entries")
    dates = [DATE.search(e.splitlines()[0]) for e in entries]
    first, last = next((d.group() for d in dates if d), ""), next((d.group() for d in reversed(dates) if d), "")
    newest_first = first > last
    pick = entries[:n] if newest_first else entries[-n:][::-1]
    for e in pick:
        lines = e.rstrip().splitlines()
        body = [x for x in lines[1:] if x.strip()]
        keep = body[:40] if full else body[:4]
        text = "\n".join(keep)
        print(lines[0])
        if text:
            print(text if full else cut(text, 500))
        print()


def cmd_grep(root, words, limit):
    words = [w.lower() for w in words]
    shown = 0
    allp = dict(pages(root))
    allp["log"] = os.path.join(root, "log.md")
    allp["index"] = os.path.join(root, "index.md")
    for name, path in sorted(allp.items()):
        if not os.path.exists(path):
            continue
        for i, line in enumerate(read(path).splitlines(), 1):
            low = line.lower()
            if all(w in low for w in words):
                print(f"{name}:{i}: {cut(line.strip(), 150)}")
                shown += 1
                if shown >= limit:
                    return print(f"... stopped at {limit}; narrow the words or raise --max")
    if not shown:
        print("no line has all the words")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--wiki")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("words", nargs="+")
    p = sub.add_parser("page")
    p.add_argument("name")
    p.add_argument("--section")
    p.add_argument("--lines")
    t = sub.add_parser("tail")
    t.add_argument("n", nargs="?", type=int, default=3)
    t.add_argument("--full", action="store_true")
    g = sub.add_parser("grep")
    g.add_argument("words", nargs="+")
    g.add_argument("--max", type=int, default=25)
    a = ap.parse_args()
    root = find_wiki(a.wiki)
    if a.cmd == "find":
        cmd_find(root, a.words)
    elif a.cmd == "page":
        cmd_page(root, a.name, a.section, a.lines)
    elif a.cmd == "tail":
        cmd_tail(root, a.n, a.full)
    else:
        cmd_grep(root, a.words, a.max)


if __name__ == "__main__":
    main()
