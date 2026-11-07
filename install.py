#!/usr/bin/env python3
"""Install the kit into a project. Never overwrites a file; shows what it would do first.

  python install.py --target /path/to/wiki-root [--project NAME] [--scope "one line"] [--language English]
                    [--skills none|global|project] [--tools] [--dry-run] [--yes]

What it does
  template/  -> <target>/   CLAUDE.md (as CLAUDE.template.md if CLAUDE.md already exists, with a diff), wiki/index.md,
                            wiki/log.md, wiki/_page-template.md, aliases.example.json, DECISIONS.md is NOT copied
  tools/     -> <target>/tools/            (only with --tools)
  skills/    -> ~/.claude/skills/ (global) or <target>/.claude/skills/ (project): wiki-peek, code-peek, source-code-context
Existing files are kept as they are and listed as "skipped". Placeholders {{PROJECT}}, {{ONE_LINE_SCOPE}},
{{WIKI_LANGUAGE}} are filled from the options.
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
TEMPLATE_FILES = ["CLAUDE.md", "wiki/index.md", "wiki/log.md", "wiki/_page-template.md", "aliases.example.json"]
PORTABLE_SKILLS = ["wiki-peek", "code-peek", "source-code-context"]  # skill-factory and skill-hub need adapting first, see skills/README.md


def fill(text: str, project: str, scope: str, language: str) -> str:
    return text.replace("{{PROJECT}}", project).replace("{{ONE_LINE_SCOPE}}", scope).replace("{{WIKI_LANGUAGE}}", language)


def plan(a) -> list[tuple[str, Path, str | bytes | None, str]]:
    """(action, destination, content, note). action: write | skip | alt"""
    acts = []
    for rel in TEMPLATE_FILES:
        src = KIT / "template" / rel
        dst = a.target / rel
        text = fill(src.read_text(encoding="utf-8"), a.project, a.scope, a.language)
        if dst.exists():
            if rel == "CLAUDE.md":
                alt = a.target / "CLAUDE.template.md"
                acts.append(("alt", alt, text, f"CLAUDE.md exists; the template is written to {alt.name}, compare below"))
            else:
                acts.append(("skip", dst, None, "exists"))
        else:
            acts.append(("write", dst, text, ""))
    if a.tools:
        for src in sorted((KIT / "tools").glob("*")):
            if src.is_file() and src.suffix in (".py", ".sh"):
                dst = a.target / "tools" / src.name
                acts.append(("skip", dst, None, "exists") if dst.exists() else ("write", dst, src.read_bytes(), ""))
    if a.skills != "none":
        base = (Path.home() / ".claude" / "skills") if a.skills == "global" else (a.target / ".claude" / "skills")
        for name in PORTABLE_SKILLS:
            for src in sorted((KIT / "skills" / name).rglob("*")):
                if src.is_file() and "__pycache__" not in src.parts:
                    dst = base / name / src.relative_to(KIT / "skills" / name)
                    acts.append(("skip", dst, None, "exists") if dst.exists() else ("write", dst, src.read_bytes(), ""))
    return acts


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # a cp1251/cp866 console must not crash on a path or a line of the user's CLAUDE.md
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # keep the console encoding, show ? instead of crashing
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--project", default="this project")
    ap.add_argument("--scope", default="project knowledge")
    ap.add_argument("--language", default="English")
    ap.add_argument("--skills", choices=["none", "global", "project"], default="none")
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    a.target = a.target.resolve()
    acts = plan(a)
    for act, dst, content, note in acts:
        print(f"{act:5} {dst}" + (f"   ({note})" if note else ""))
        if act == "alt" and (a.target / "CLAUDE.md").exists():
            old = (a.target / "CLAUDE.md").read_text(encoding="utf-8", errors="replace").splitlines()
            diff = list(difflib.unified_diff(old, content.splitlines(), "CLAUDE.md (yours)", "template", lineterm="", n=0))
            print("\n".join(diff[:60]) + ("\n... diff cut ..." if len(diff) > 60 else ""))
    todo = [x for x in acts if x[0] in ("write", "alt")]
    if a.dry_run or not todo:
        print("\n" + ("dry run, nothing written" if a.dry_run else "nothing to write"))
        return 0
    if not a.yes and input(f"\nWrite {len(todo)} file(s)? [y/N] ").strip().lower() != "y":
        print("cancelled")
        return 1
    for act, dst, content, _ in todo:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    (a.target / "wiki").mkdir(exist_ok=True)
    print(f"wrote {len(todo)} file(s). Next: fill CLAUDE.md, then `python tools/wiki_miner.py --wiki {a.target / 'wiki'} --out out` (see README).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
