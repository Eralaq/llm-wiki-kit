"""
hub.py - list, show, copy and create Claude Code skills across the projects of this machine.

  python3 -I -X utf8 hub.py list [--project P]
  python3 -I -X utf8 hub.py show NAME [--from P]
  python3 -I -X utf8 hub.py add NAME [--from P] [--to global|here] [--update]
  python3 -I -X utf8 hub.py new NAME --desc "..." [--to global|here]

Skills are folders with a SKILL.md in ~/.claude/skills, ~/<project>/.claude/skills and ~/tanuki-botkit/skills.
Nothing is overwritten without --update (the old copy is kept); files that look like secrets are never copied.
"""
import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

SECRET_NAMES = re.compile(r"(^\.env|\.pem$|\.key$|id_rsa|credentials|secret|token)", re.I)
SKIP_DIRS = {"node_modules", ".git", "__pycache__"}


def home():
    return Path.home()


def roots():
    """(label, skills folder) for the global folder, the shipped sources and every project folder under HOME."""
    found = [("global", home() / ".claude" / "skills"), ("botkit", home() / "tanuki-botkit" / "skills")]
    for p in sorted(home().iterdir()):
        if p.is_dir() and not p.name.startswith(".") and (p / ".claude" / "skills").is_dir():
            found.append((p.name, p / ".claude" / "skills"))
    return found


def description(skill_md):
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def all_skills():
    out = []
    for label, base in roots():
        if base.is_dir():
            out += [(label, d.name, d) for d in sorted(base.iterdir())
                    if d.is_dir() and (d / "SKILL.md").exists() and ".bak-" not in d.name]
    return out


def find(name, project=None):
    return [(lab, d) for lab, n, d in all_skills() if n == name and (project is None or lab == project)]


def cmd_list(a):
    for label, name, d in all_skills():
        if a.project and label != a.project:
            continue
        print(f"{name:32} {label:14} {description(d / 'SKILL.md')[:110]}")


def pick(a):
    hits = find(a.name, a.frm)
    if not hits:
        sys.exit(f"no skill {a.name!r}" + (f" in {a.frm}" if a.frm else ""))
    return hits


def cmd_show(a):
    hits = pick(a)
    label, d = hits[0]
    if len(hits) > 1:
        print("also in: " + ", ".join(lab for lab, _ in hits[1:]))
    print(f"# {a.name} ({label}: {d})\n")
    print((d / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
    print("\nfiles: " + ", ".join(str(p.relative_to(d)) for p in sorted(d.rglob("*")) if p.is_file() and not set(p.parts) & SKIP_DIRS))


def target_base(where):
    return home() / ".claude" / "skills" if where == "global" else Path.cwd() / ".claude" / "skills"


def cmd_add(a):
    label, src = pick(a)[0]
    dest = target_base(a.to) / a.name
    if dest.resolve() == src.resolve():
        sys.exit("source and target are the same folder")
    refused = [str(p.relative_to(src)) for p in src.rglob("*")
               if p.is_file() and SECRET_NAMES.search(p.name) and not set(p.parts) & SKIP_DIRS]
    if refused:
        sys.exit("refused: these files look like secrets, take the skill by hand: " + ", ".join(refused))
    if dest.exists():
        if not a.update:
            sys.exit(f"already there: {dest} (use --update to replace; the old copy is kept)")
        dest.rename(dest.with_name(f"{a.name}.bak-{datetime.now():%Y%m%d-%H%M%S}"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "node_modules"))
    print(f"copied {a.name} from {label} to {dest}; send /reload so the agent reads it")


def cmd_new(a):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", a.name):
        sys.exit("name: lowercase letters, digits and hyphens")
    dest = target_base(a.to) / a.name
    if dest.exists():
        sys.exit(f"already there: {dest}")
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(
        f"---\nname: {a.name}\ndescription: {a.desc} Don't use for - (fill in).\n---\n\n# {a.name}\n\n"
        "## When\n(one or two lines)\n\n## Steps\n1. \n\n## Never\n- \n", encoding="utf-8")
    print(f"created {dest / 'SKILL.md'}; fill it in, then send /reload")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("--project")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show")
    p.add_argument("name")
    p.add_argument("--from", dest="frm")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("add")
    p.add_argument("name")
    p.add_argument("--from", dest="frm")
    p.add_argument("--to", choices=["global", "here"], default="here")
    p.add_argument("--update", action="store_true")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("new")
    p.add_argument("name")
    p.add_argument("--desc", required=True)
    p.add_argument("--to", choices=["global", "here"], default="here")
    p.set_defaults(fn=cmd_new)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
