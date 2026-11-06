#!/bin/bash
# Session improver: Haiku reads the miner report and trajectories of the heaviest sessions and proposes changes.
# No tools (text in, text out), no repository access. Input is already redacted by mine_sessions.py.
# Usage: run_improver.sh <miner-output-dir>    e.g. ./out/session-miner/myproject
# Env: IMPROVER_MODEL (default claude-haiku-5-5)
# Output: <dir>/improver.md. Nothing is applied automatically; the owner approves each proposal by hand.
set -e
D=${1:?miner output dir}
{
cat <<'EOF'
You review how Claude Code sessions went in one software project, to find avoidable waste (tokens, turns, time, blocked actions) and propose changes that would remove it.

Rules:
- A proposal is allowed only if its cause appears in at least 3 different sessions in the data below. Name those sessions by their 8-character id. A cause seen in one session goes into the section "Seen once, not a rule" and gets no proposal.
- Each proposal has: kind (one of: CLAUDE.md line, skill with script, permission rule, habit for the user), the exact text or command to add, the sessions that show the cause, what it should save, and how to check after a week that it worked.
- Do not invent facts about the project. Use only what the data shows. If the data cannot tell the real cause, say what extra data would.
- The data has no hidden test of correctness. Judge waste only: errors, denials, repeated commands, context growth, user corrections, bot loop notes.
- Keep every proposed CLAUDE.md line to one sentence. Prefer fewer, stronger proposals; at most 5.
- Answer in English, as markdown, with the sections: Proposals, Seen once not a rule, Data I would want next.

EOF
echo "=== MINER REPORT ==="
cat $D/report.md
for f in $D/digests/*.txt; do
  echo; echo "=== TRAJECTORY $(basename $f .txt) (U user, C user correction, E tool error, D denied, K compaction, B bot loop note) ==="
  cat $f
done
} > $D/improver-input.md
claude -p --model "${IMPROVER_MODEL:-claude-haiku-5-5}" --effort high --tools "" --output-format text < $D/improver-input.md > $D/improver.md
echo "done: $(wc -c < $D/improver.md) bytes"
