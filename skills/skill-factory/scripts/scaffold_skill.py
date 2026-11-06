"""
scaffold_skill.py - create a new skill skeleton in a STAGING folder, never straight into a live skills dir.

  scaffold_skill.py new my-skill --description "Does X ... Use when the user says ..." [--scripts a.py,b.py]
  scaffold_skill.py install my-skill --to /path/to/project/.claude/skills        # copy staging -> target after lint passes
  scaffold_skill.py install my-skill --to ~/.claude/skills                        # global

Staging: ~/.claude/skill-factory/staging/<name>/ . `install` refuses to overwrite an existing skill and refuses a
skill that fails lint_skill.py. A human reads the staged files and says "install" - the factory never installs on its own.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

STAGING = Path.home() / ".claude" / "skill-factory" / "staging"
HERE = Path(__file__).resolve().parent

SKILL_TMPL = """---
name: {name}
description: {description}
---

# {name}

Run scripts with `python -I -X utf8 <skill dir>/scripts/<script>` (keep this skill short: every line is read by the model each time).

## Workflow (fewest calls possible)
1. TODO: the one call that gives the overview.
2. TODO: the call that answers the usual question.

## Scripts
| Script | Use |
|---|---|
{rows}

## Rules
- Secrets are never written in code or in this file: read them from env or a credentials file.
- Prefer one script call that returns several results over several calls that return one.
- Output stays compact; large results are saved to a timestamped file under `out/`, never overwritten.
- Say only what a script printed. Count what was found before you answer ("5 hits", not the 3 you happened to print); a failed or empty
  call is "not checked", never "fine" or "none". Name things by their role for the owner, not by an internal alias.
- Do not write your own ssh/sql/curl next to this skill. If a script cannot answer, say which one and why, and ask; missing power is a
  reason to extend the skill, not to bypass it.
"""

SCRIPT_TMPL = '''"""
{name} - TODO one line: what it does and how to call it.

  python -I -X utf8 {name} --help
"""

import argparse
import sys


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    raise SystemExit("TODO: implement")


if __name__ == "__main__":
    main()
'''


def new(a):
    d = STAGING / a.name
    if d.exists():
        raise SystemExit(f"{d} already exists in staging; pick another name or delete it.")
    scripts = [s.strip() for s in a.scripts.split(",") if s.strip()]
    (d / "scripts").mkdir(parents=True)
    rows = "\n".join(f"| `{s}` | TODO |" for s in scripts) or "| (none yet) | |"
    (d / "SKILL.md").write_text(SKILL_TMPL.format(name=a.name, description=a.description, rows=rows), encoding="utf-8")
    for s in scripts:
        (d / "scripts" / s).write_text(SCRIPT_TMPL.format(name=s), encoding="utf-8")
    print(f"Staged: {d}\nNext: fill the TODOs, run lint_skill.py {d}, show it to the user, then `install`.")


def install(a):
    src = STAGING / a.name
    if not src.exists():
        raise SystemExit(f"Nothing staged at {src}")
    dst = Path(a.to).expanduser() / a.name
    if dst.exists():
        raise SystemExit(f"{dst} already exists - not overwriting. Remove or rename it yourself.")
    r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(HERE / "lint_skill.py"), str(src)])
    if r.returncode != 0:
        raise SystemExit("Lint failed - fix the staged skill first.")
    shutil.copytree(src, dst)
    print(f"Installed to {dst}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("name")
    n.add_argument("--description", required=True)
    n.add_argument("--scripts", default="")
    n.set_defaults(fn=new)
    i = sub.add_parser("install")
    i.add_argument("name")
    i.add_argument("--to", required=True)
    i.set_defaults(fn=install)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
