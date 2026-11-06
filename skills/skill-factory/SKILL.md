---
name: skill-factory
description: Builds new skills and their Python scripts from what Claude keeps retyping in past sessions, so later sessions spend far fewer tokens. Mines session transcripts for repeated SQL, boilerplate and shell commands, stages a skill + scripts for review, lints it, installs it only after the user approves. Use when the user says make a skill, create a skill for this, skill factory, фабрика скиллов, сделай скилл, он каждый раз набирает одно и то же, reduce tokens in this repo.
---

> **Kit note.** The scripts in `scripts/` are generic (stdlib python). The text of this SKILL.md describes OUR environment (a shared skills repo, a server, skills such as `pm2-ops`, `selfree-db`, `adam-db`, local paths). Adapt the "Patterns" and "Reference example" sections before you rely on them elsewhere.

# skill-factory

Goal: the next session solves the same task in 2-3 short calls instead of 20 long ones. Scripts do the typing, the skill only says which script to call.
Run: `python -I -X utf8 ~/.claude/skills/skill-factory/scripts/<script>`.

## Pipeline (human approves between 3 and 5)
1. **Mine**: `mine_sessions.py <project fragment>` - repeated SQL, repeated code lines (boilerplate), repeated shell commands, and the token cost of the repetition. Read the report; it is a candidate list, not a decision. Then `mine_reads.py <project fragment>` for what comes BACK: the results that cost most (size x later calls that carried them), files read in full again and again, tokens per tool. Long-session cost is mostly here.
2. **Design** the smallest set of scripts. Order of value: (a) one shared library script for connection/auth/boilerplate, (b) one "overview in a single call" script, (c) named reports/queries stored as files, (d) a free-form runner that accepts several statements per call, (e) wrappers for repeated shell commands.
3. **Stage**: `scaffold_skill.py new <name> --description "... Use when the user says ..." --scripts a.py,b.py`. Write the scripts and a SKILL.md under 70 lines. Then `lint_skill.py ~/.claude/skill-factory/staging/<name>`.
4. **Test** every script against the real system with read-only calls; show the user the files and the test output.
5. **Install** only after the user says so: `scaffold_skill.py install <name> --to <project>/.claude/skills` (or `~/.claude/skills`). Never overwrites.
6. **Check triggering** (only when the user says so: it spends subscription): `run_trigger_eval.py evals/<skill>.json --skill <skill> --cwd <project>` runs `claude -p` per phrase and reports whether the first tool call was that skill. Eval sets and folders: `evals/`.

7. **Share** (after install, on the owner's word): a skill many projects can use (servers, deploy, anything not tied to one database) goes into `tanuki-botkit/skills/<name>/` and ships to guts with `skills/install.py`; the others stay in their project. Projects pick each other's skills with skill `skill-hub` (`hub.py list | show | add`, in Telegram `/skills`). Before building, run `hub.py list`: the skill may already exist in another project.

## Patterns that already exist (copy their shape)
- Looking at servers (ssh, pm2, systemd, ss, logs): skill `pm2-ops`, with one `OK/WARN/PROBLEM` line per service from a per-project list `.claude/pm2-ops.json`. Do not make a second one; add the project's services to its list.
- Database questions: a database-skill shape (library + overview + reports + runner).
- Deploy: skill `deploy`, never a new script per project.

## Token rules for the skills you build
- Output compact by default (few rows, short cells, no banners); silent when nothing to warn about. Big results go to a timestamped file, the agent reads the head.
- Several results per call (multiple statements, `--stats`-style groups). Cache slow static facts (schema) for hours.
- Description = trigger phrases in the user's real words (RU and EN). A vague description means the skill never fires.
- Keep SKILL.md short; put long background in a wiki/reference file linked from it.
- Read-only by default; secrets only from env or an existing credentials file, never in code, never printed. Scripts in Python, `-I -X utf8`.
- Generic bot/library code goes to its shared library first (see the global CLAUDE.md botkit rule); this factory is for repo/agent skills.

## Design rules learned from real sessions (2026-10-30)
- **A script that depends on a channel (ssh, http, a database) must explain its own failure** and name the next probe, not just exit. Example: `pm2lib` says "run reach.py HOST"; `project_check.py` goes on to the other hosts and reports the dead one as NOT checked.
- **A verdict states what was measured.** "ssh timed out" is not "the processes are fine" and not "the server is down"; the output must keep the two apart (`reach.py`).
- **Search by name is ONE script over all tables with a name column** (`find_by_name.py`), ending with the tables that had no hit. Otherwise the agent queries table after table and misses rows.
- **Output says how many rows exist, not only how many it printed**; never cut a cell that the answer needs (short results get wide cells).
- **Names for the owner are roles** ("prod database"), not ssh aliases.
- The agent in a session may build a NEW skill with this factory and install it into its own project after approval. A generic skill (servers, deploy) or a fix of a shipped one goes to `tanuki-botkit/skills/` with tests: a session edit of a shipped skill is overwritten by the next `skills/install.py --update`.

## Reference example
A database skill from one of our projects (library, overview, reports, runner, sampler); not included in this kit.

## Rules
- Never build or install a skill before the owner says so; a proposal is one line, not a finished skill.
- Never claim a command is "typed N times" without the count from `suggest_skills.py` or the miner.
- Never put a secret, a host password or a key into a script or a proposal; the examples are masked, keep them masked.

## Proposals at the end of a session (built 2026-11-02)
`suggest_skills.py` finds command shapes typed 3+ times in one session (no model calls, secrets masked, skill-script calls and plain reading commands skipped):
- `--transcript FILE` prints them; `--hook` (for a SessionEnd hook) reads the hook JSON on stdin, prints nothing and appends to `~/.claude/skill-factory/proposals.md`, once per session; `--pending` shows what is waiting; `--clear` empties it. The hook itself is NOT installed by default: the owner adds it to settings.
- Across many sessions use the session miner (`PM/ideas/session-miner/mine_sessions.py`, section "Skill candidates"): the same shapes, needing 3+ sessions. Then take one candidate through the pipeline above.
- When the user starts a session and `--pending` is not empty, offer the top item in one line: "typed N times in <session>: make a skill?" Never build before they say so.
