import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from run_trigger_eval import classify, evaluate, stream_events  # noqa: E402


def start(name):
    return {"type": "stream_event", "event": {"type": "content_block_start", "content_block": {"type": "tool_use", "name": name}}}


def delta(text):
    return {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": text}}}


def stop(kind="content_block_stop"):
    return {"type": "stream_event", "event": {"type": kind}}


def test_the_named_skill_called_first_is_a_trigger():
    assert classify([start("Skill"), delta('{"skill": "sel'), delta('free-db"}')], "my-skill") is True


def test_another_skill_or_another_tool_is_not_a_trigger():
    assert classify([start("Skill"), delta('{"skill": "goal"}'), stop()], "my-skill") is False
    assert classify([start("Bash")], "my-skill") is False
    assert classify([stop("message_stop")], "my-skill") is False


def test_the_full_message_fallback_and_unknown_end():
    msg = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "skill-factory"}}]}}
    assert classify([msg], "skill-factory") is True
    assert classify([{"type": "result"}], "skill-factory") is False
    assert classify([], "skill-factory") is None


def test_pass_fail_follow_should_trigger():
    items = [{"query": "yes", "should_trigger": True}, {"query": "no", "should_trigger": False},
             {"query": "wrong", "should_trigger": True}]
    fired = {"yes": True, "no": False, "wrong": False}
    out = evaluate(items, "s", ".", runs=2, timeout=1, workers=2, runner=lambda q, *_: fired[q])
    assert out["summary"] == {"total": 3, "passed": 2, "failed": 1}
    assert [r["pass"] for r in out["results"]] == [True, True, False] and out["results"][0]["runs"] == 2


def test_a_failing_run_counts_as_not_triggered():
    def boom(*_):
        raise RuntimeError("no claude")

    out = evaluate([{"query": "q", "should_trigger": False}], "s", ".", runs=1, timeout=1, workers=1, runner=boom)
    assert out["summary"]["passed"] == 1


def test_stream_events_reads_a_process_and_stops_at_the_timeout():
    code = "import sys,json,time\nprint(json.dumps({'type':'x'}),flush=True)\nprint('not json',flush=True)\nprint(json.dumps({'type':'y'}),flush=True)"
    assert [e["type"] for e in stream_events([sys.executable, "-c", code], ".", 10)] == ["x", "y"]
    started = __import__("time").time()
    list(stream_events([sys.executable, "-c", "import time; time.sleep(30)"], ".", 2))
    assert __import__("time").time() - started < 10                      # a silent process is killed at the timeout
