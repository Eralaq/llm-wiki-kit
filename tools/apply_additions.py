#!/usr/bin/env python3
"""Append reviewed lines to a CLAUDE.md, keeping a dated backup. Local files only, no network.

  python apply_additions.py additions.md /path/to/CLAUDE.md [--yes]

Shows what will be appended and asks for confirmation (unless --yes). The backup is <target>.bak-YYYY-MM-DD.
Nothing is changed if the exact text is already present.
"""
import argparse, datetime, shutil, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("additions", type=Path)
ap.add_argument("target", type=Path)
ap.add_argument("--yes", action="store_true")
a = ap.parse_args()
add = a.additions.read_text(encoding="utf-8").strip() + "\n"
cur = a.target.read_text(encoding="utf-8") if a.target.exists() else ""
if add.strip() in cur:
    sys.exit("already present, nothing to do")
print(f"--- will append to {a.target}:\n{add}")
if not a.yes and input("Apply? [y/N] ").strip().lower() != "y":
    sys.exit("cancelled")
if a.target.exists():
    shutil.copy2(a.target, a.target.with_name(a.target.name + f".bak-{datetime.date.today()}"))
a.target.write_text(cur.rstrip() + "\n\n" + add, encoding="utf-8")
print("done")
