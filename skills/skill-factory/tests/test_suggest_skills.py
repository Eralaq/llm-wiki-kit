import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import suggest_skills as ss  # noqa: E402


def transcript(tmp_path, commands):
    rows = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": c}}]}} for c in commands]
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_the_same_shape_three_times_is_a_candidate(tmp_path):
    cmds = [f"cd /home/x && mongosh --quiet --eval 'db.a.find({{n:{i}}})'" for i in range(3)]
    found = ss.candidates(transcript(tmp_path, cmds))
    assert len(found) == 1 and found[0][1] == 3 and found[0][0].startswith("mongosh --quiet --eval")


def test_reading_commands_skill_calls_and_rare_commands_are_skipped(tmp_path):
    cmds = ["ls -la /tmp/aaaa"] * 4 + ["python3 -I /home/u/.claude/skills/pm2-ops/scripts/x.py --all"] * 4 + ["curl -s http://example.org/x"] * 2
    assert ss.candidates(transcript(tmp_path, cmds)) == []


def test_secrets_are_masked_in_the_example(tmp_path):
    cmds = ["curl -H 'Authorization: Bearer abcdef123456789' https://api.example.org/v1/items"] * 3
    found = ss.candidates(transcript(tmp_path, cmds))
    assert found and "abcdef123456789" not in found[0][2]


def test_hook_writes_once_per_session_and_prints_nothing(tmp_path, monkeypatch, capsys):
    t = transcript(tmp_path, ["python3 -I -X utf8 /home/u/q.py 1 2 3"] * 3)
    store = tmp_path / "proposals.md"
    payload = json.dumps({"transcript_path": str(t), "session_id": "abcdef12-0000"})
    for _ in range(2):
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
        assert ss.main(["--hook", "--proposals", str(store)]) == 0
    assert capsys.readouterr().out == ""
    assert store.read_text(encoding="utf-8").count("## session abcdef12") == 1


def test_a_broken_hook_input_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert ss.main(["--hook", "--proposals", str(tmp_path / "p.md")]) == 0
