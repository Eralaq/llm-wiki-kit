---
name: skill-hub
description: Finds, shows, copies and creates Claude Code skills across all projects on guts. Use when the user says what skills exist, show the skill from project X, take the skill from another project, apply or install a skill here, share a skill, make a new skill, покажи скилы, какие есть скилы, возьми скил из проекта, поставь скил, создай скил. Don't use for - editing what a skill does inside its own project, or the deploy skill's own scripts.
---

# skill-hub

Skills live in `~/.claude/skills` (global), `~/<project>/.claude/skills` (one project) and `~/tanuki-botkit/skills` (shipped sources). `H` = `~/.claude/skills/skill-hub/scripts/hub.py`. Call it as one plain command: `python3 -I -X utf8 $H <command>`.

## Commands
| Command | What it does |
|---|---|
| `list [--project P]` | every skill on this machine: name, where, one-line description |
| `show NAME [--from P]` | prints that skill's SKILL.md and lists its files |
| `add NAME [--from P] [--to global\|here]` | copies the skill; `here` = this project's `.claude/skills` (default), `global` = `~/.claude/skills`; `--update` replaces an older copy and keeps `NAME.bak-<time>` |
| `new NAME --desc "..." [--to global\|here]` | a skeleton SKILL.md with the right front matter, ready to fill |

`P` is a folder name under `~` (or `global`, `botkit`). Without `--from`, the first copy found is used and the others are listed.

## Rules
- Never overwrite without `--update`; never copy a file that holds a secret (the script refuses: `.env`, keys, tokens). Tell the owner which file it refused.
- After `add` or `new`, say: "send `/reload` so the agent reads it". Do not edit a skill that belongs to another project: copy it first, then change the copy.
- A new skill: description starts with what it does and when to use it (RU and EN trigger words), ends with "Don't use for ...". SKILL.md stays short; details go to `references/`.
- This skill only reads and copies skill folders. It does not run another project's scripts.
