"""
lint_skill.py - check a skill folder before it is installed. Exit code 1 if any ERROR.

  lint_skill.py <skill dir>

ERROR   : no/invalid frontmatter, name not kebab-case or differs from the folder, empty description, description
          > 1000 chars, hard-coded secret in any file, a script that does not compile, SKILL.md that names a
          script file which does not exist, leftover TODO in SKILL.md.
WARN    : description without a trigger phrase ("Use when ..."), SKILL.md longer than 70 lines (token cost: it is
          read in full every time the skill fires), a script not mentioned in SKILL.md, script without --help doc,
          a script that runs ssh/curl/requests with no timeout, no Rules/Never section in SKILL.md (what the agent must not claim or do).
"""

import py_compile
import re
import sys
from pathlib import Path

NETWORK = re.compile(r"""['"](ssh|curl)['"]|urlopen|requests\.(get|post)|create_connection""")
TIMEOUT = re.compile(r"ConnectTimeout|timeout\s*=|-m\s+\d|--max-time")
SECRET = re.compile(r"""(?ix)(password|passwd|pwd|secret|token|api[_-]?key|PGPASSWORD)\s*[=:]\s*(['"])(?!\*\*\*|<|\$|\{|%|\s*\2)[^'"\s]{6,}\2""")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    d = Path(sys.argv[1])
    errors, warns = [], []
    sk = d / "SKILL.md"
    if not sk.exists():
        raise SystemExit(f"ERROR no SKILL.md in {d}")
    text = sk.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        errors.append("SKILL.md has no frontmatter block")
        fm = {}
    else:
        fm = dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M))
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        errors.append(f"name '{name}' must be kebab-case")
    elif name != d.name:
        errors.append(f"name '{name}' differs from folder '{d.name}'")
    if not desc:
        errors.append("description is empty")
    elif len(desc) > 1000:
        errors.append(f"description is {len(desc)} chars (max 1000)")
    elif not re.search(r"(?i)\buse when\b|\bиспользуй\b|\bwhen the user\b", desc):
        warns.append("description has no trigger phrase ('Use when the user says ...') - the model may never pick this skill")
    if "TODO" in text:
        errors.append("SKILL.md still contains TODO")
    n_lines = len(text.splitlines())
    if n_lines > 70:
        warns.append(f"SKILL.md is {n_lines} lines; move detail into a reference file read on demand")

    scripts = sorted((d / "scripts").glob("*.py")) if (d / "scripts").exists() else []
    for s in scripts:
        try:
            py_compile.compile(str(s), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{s.name} does not compile: {e.msg.strip().splitlines()[-1]}")
        if s.name not in text:
            warns.append(f"{s.name} is not mentioned in SKILL.md")
        body = s.read_text(encoding="utf-8")
        if '"""' not in body[:400]:
            warns.append(f"{s.name} has no module docstring (--help text)")
        if NETWORK.search(body) and not TIMEOUT.search(body):
            warns.append(f"{s.name} talks to a network/ssh and sets no timeout: a dead host would hang the agent (ConnectTimeout / timeout=)")
    if not re.search(r"(?im)^#{1,3}\s*(rules|never)\b", text):
        warns.append("SKILL.md has no '## Rules' / '## Never' section: say what the agent must not claim or do (for example 'do not call a server fine when only ssh was tried')")
    # only the scripts table counts as a promise; prose may mention scripts of other skills as examples
    for ref in set(re.findall(r"^\|\s*`(\w+\.py)\b", text, re.M)):
        if not any(s.name == ref for s in scripts):
            errors.append(f"SKILL.md names {ref} but scripts/{ref} does not exist")
    for f in d.rglob("*"):
        if f.is_file() and f.suffix in {".py", ".md", ".sql", ".sh", ".json", ".txt", ".env"} and "out" not in f.relative_to(d).parts:
            try:
                body = f.read_text(encoding="utf-8")
            except Exception:
                continue
            if SECRET.search(body):
                errors.append(f"possible hard-coded secret in {f.relative_to(d)}")

    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    print(f"{d.name}: {len(errors)} error(s), {len(warns)} warning(s), SKILL.md {n_lines} lines, {len(scripts)} script(s)")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
