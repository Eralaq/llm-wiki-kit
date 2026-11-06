# Skills

Claude Code skills that make a wiki and a codebase cheap to read. Copy a folder into `~/.claude/skills/` (global) or `<project>/.claude/skills/` (one project); `install.py` does this for you.

| Skill | What it does | Portable? |
|---|---|---|
| `wiki-peek` | Reads a wiki in small pieces (find a page, outline, one section, newest log entries, grep) instead of reading `index.md` or whole pages. | yes |
| `code-peek` | Same idea for big source files: outline with line ranges, then one function. | yes |
| `source-code-context` | Tells an agent to search real source references instead of guessing API names. | yes |
| `skill-factory` | Mines past sessions for what the agent keeps retyping and drafts a skill plus script; lints the result. | **scripts yes, SKILL.md no**: its text describes our environment (see the kit note at the top of it). Not installed by `install.py`. |
| `skill-hub` | Finds, shows, copies and creates skills across projects. | **adapt first**: it scans project skill folders under HOME and a `tanuki-botkit/skills` folder; change `found = [...]` in `scripts/hub.py` to your layout. |

Notes
- `skill-factory/evals/` keeps only its own example eval; evals of our private skills were left out on purpose.
- Skills here have not been re-verified outside the machine they were written on. Run each skill's own tests (`skill-factory/tests`) after installing.
