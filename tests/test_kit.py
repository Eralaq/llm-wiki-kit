"""Tests for the kit. Run: python -X utf8 -I -m unittest discover -s tests -v   (stdlib only, no network, no model)."""
import ast
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "tools"))


def assigned(path, name):
    for n in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(n, ast.Assign) and any(getattr(x, "id", None) == name for x in n.targets):
            return ast.literal_eval(n.value)


class Compile(unittest.TestCase):
    def test_all_python_compiles(self):
        for p in list((KIT / "tools").glob("*.py")) + [KIT / "install.py"]:
            ast.parse(p.read_text(encoding="utf-8"), str(p))


class Prompts(unittest.TestCase):
    def test_prompt_files_match_source(self):
        for md, py, name in [("bench-agent.md", "run_bench.py", "PROMPT"), ("alias-generation.md", "gen_aliases.py", "PROMPT"),
                             ("answer-judge.md", "judge_answers.py", "PRESENCE_PROMPT"), ("answer-judge.md", "judge_answers.py", "GROUNDING_PROMPT")]:
            text = (KIT / "prompts" / md).read_text(encoding="utf-8")
            self.assertIn(assigned(KIT / "tools" / py, name).rstrip(), text, f"{md} is out of sync with {py}")


class Search(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        w = Path(self.tmp.name) / "wiki"
        w.mkdir()
        pages = {"db-backup-runbook": "# Database backup runbook\n\n**Summary**: How to run and restore the nightly database backup.\n\nPg dump nightly.",
                 "login-flow": "# Login flow\n\n**Summary**: How sessions and redirects work after sign in.\n\nCookies.",
                 "_page-template": "# Title\n\n**Summary**: template backup backup backup"}
        for k, v in pages.items():
            (w / f"{k}.md").write_text(v, encoding="utf-8")
        self.wiki = w

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_page_and_skips_template(self):
        from wiki_search import load, search
        docs = load(self.wiki, {"login-flow": {"aliases": ["sign in"], "questions": ["why does login redirect twice"]}})
        self.assertNotIn("_page-template", docs)
        self.assertEqual(search(docs, "restore the backup", 3)[0][1], "db-backup-runbook")
        self.assertEqual(search(docs, "why does login redirect twice", 3)[0][1], "login-flow")


class MinerPath(unittest.TestCase):
    def test_relative_wiki_path_does_not_match_every_wiki(self):
        from wiki_miner import Wiki
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "wiki").mkdir()
            old = os.getcwd()
            os.chdir(d)
            try:
                key = Wiki(Path("wiki")).key
            finally:
                os.chdir(old)
            self.assertNotEqual(key, "/wiki/")
            self.assertTrue(key.endswith("/wiki/") and len(key) > len("/wiki/"))


PAGE = "# {t}\n\n**Summary**: {s}\n\n**Sources**: `raw/x.md`\n\n**Last updated**: {d}\n\n---\n\n{b}\n\n## Related pages\n\n{r}\n"
BODY = "Some real content about the topic. " * 12


def make_wiki(root: Path, pages: dict, index: str | None = None) -> Path:
    w = root / "wiki"
    w.mkdir(exist_ok=True)
    for slug, kw in pages.items():
        full = {"t": slug.title(), "s": "A summary.", "d": "2026-01-01", "b": BODY, "r": "- [[other]]"}
        full.update(kw)
        (w / f"{slug}.md").write_text(PAGE.format(**full), encoding="utf-8")
    (w / "index.md").write_text(index if index is not None else "\n".join(f"- [[{k}]]" for k in pages), encoding="utf-8")
    return w


class Show(unittest.TestCase):
    def test_show_reads_a_slug_and_refuses_paths(self):
        from wiki_search import show_page
        with tempfile.TemporaryDirectory() as d:
            w = make_wiki(Path(d), {"alpha": {}, "beta": {}})
            self.assertEqual(show_page(w, "alpha")[0], 0)
            self.assertEqual(show_page(w, "alpha.md")[0], 0)
            self.assertEqual(show_page(w, "../CLAUDE")[0], 2)
            self.assertEqual(show_page(w, "..\\x")[0], 2)
            code, msg = show_page(w, "alpa")
            self.assertEqual(code, 1)
            self.assertIn("alpha", msg)


class Stemmers(unittest.TestCase):
    def test_suffix_stemmer_joins_word_forms(self):
        from wiki_search import stem_ru
        self.assertEqual(stem_ru("страницами"), stem_ru("страницы"))
        self.assertEqual(stem_ru("бэкапов"), stem_ru("бэкапы"))
        self.assertEqual(stem_ru("три"), "три")  # never cut below 3 letters


class EvalMetrics(unittest.TestCase):
    def test_hit_recall_junk(self):
        import wiki_search
        from eval_search import evaluate
        with tempfile.TemporaryDirectory() as d:
            w = make_wiki(Path(d), {"backup-runbook": {"t": "Backup runbook", "s": "Restore the nightly backup."},
                                    "login-flow": {"t": "Login flow", "s": "Sessions after sign in."}})
            docs = wiki_search.load(w, {})
            out = evaluate(docs, [{"id": 1, "question": "restore the backup", "gold_pages": ["backup-runbook", "missing-page"]}])
        s = out["summary"]
        self.assertEqual(s["hit@1"], 1.0)
        self.assertEqual(s["recall@1"], 0.5)  # one of two gold pages found
        self.assertLessEqual(s["junk@5"], 1.0)


class Lint(unittest.TestCase):
    def test_finds_the_planted_problems(self):
        from wiki_lint import lint
        with tempfile.TemporaryDirectory() as d:
            w = make_wiki(Path(d), {"a": {"r": "- [[b]]"}, "b": {"r": "- [[a]]\n- [[ghost]]"}, "lonely": {"r": "- [[a]]"}},
                          index="- [[a]]\n- [[b]]\n- [[gone]]")
            (w / "nofields.md").write_text("# Nofields\n\nJust text.\n", encoding="utf-8")
            (w / "ru.md").write_text(PAGE.format(t="Ru", s="s", d="2026-01-01", b="Привет мир. " * 30, r="- [[a]]"), encoding="utf-8")
            kinds = {(i["kind"], i["page"]) for i in lint(w, stale_days=30, english_only=True, today=datetime.date(2026, 6, 1))}
        self.assertIn(("broken-link", "b"), kinds)
        self.assertIn(("index-dangling", "index"), kinds)
        self.assertIn(("missing-field", "nofields"), kinds)
        self.assertIn(("orphan", "lonely"), kinds)
        self.assertIn(("not-in-index", "lonely"), kinds)
        self.assertIn(("stale", "a"), kinds)
        self.assertIn(("non-english", "ru"), kinds)
        self.assertNotIn(("broken-link", "a"), kinds)

    def test_clean_wiki_has_no_errors(self):
        from wiki_lint import lint
        with tempfile.TemporaryDirectory() as d:
            w = make_wiki(Path(d), {"a": {"r": "- [[b]]"}, "b": {"r": "- [[a]]"}})
            self.assertEqual([i for i in lint(w, today=datetime.date(2026, 6, 1)) if i["level"] == "error"], [])


class AliasHash(unittest.TestCase):
    def test_only_changed_pages_are_stale(self):
        from gen_aliases import classify, page_hash
        with tempfile.TemporaryDirectory() as d:
            w = make_wiki(Path(d), {"a": {}, "b": {}, "c": {}, "d": {}})
            res = {"a": {"aliases": [], "questions": [], "hash": page_hash(w / "a.md")},
                   "b": {"aliases": [], "questions": [], "hash": page_hash(w / "b.md")},
                   "c": {"aliases": [], "questions": []}, "zz": {"aliases": [], "questions": [], "hash": "x"}}
            (w / "a.md").write_text((w / "a.md").read_text(encoding="utf-8") + "\nbody-only edit\n", encoding="utf-8")
            (w / "b.md").write_text((w / "b.md").read_text(encoding="utf-8").replace("A summary.", "A new summary."), encoding="utf-8")
            st = classify(w, res)
        self.assertEqual(st["fresh"], ["a"])  # a body-only edit does not change what the model saw
        self.assertEqual(st["changed"], ["b"])
        self.assertEqual(st["unhashed"], ["c"])
        self.assertEqual(st["new"], ["d"])
        self.assertEqual(st["orphaned"], ["zz"])


def stream(*events):
    return "\n".join(json.dumps(e) for e in events)


def tool(name, **inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def result(text, is_error=False):
    return {"type": "result", "result": text, "is_error": is_error, "usage": {"input_tokens": 10, "output_tokens": 5}, "total_cost_usd": 0.01}


class ParseStream(unittest.TestCase):
    def test_counts_read_and_show_and_junk(self):
        from run_bench import parse_stream
        out = stream(tool("Read", file_path="Z:/w/wiki/index.md"), tool("Bash", command="python tools/wiki_search.py --show gold-page"),
                     tool("Read", file_path="Z:/w/wiki/other.md"), result("The answer."))
        r = parse_stream(out, "", ["gold-page"])
        self.assertIsNone(r["error"])
        self.assertTrue(r["all_gold"])
        self.assertEqual(r["steps_to_first_gold"], 2)
        self.assertEqual(r["junk_pages"], ["other"])  # index is not junk
        self.assertTrue(r["index_first"])

    def test_usage_limit_is_an_error_not_a_miss(self):
        from run_bench import parse_stream
        r = parse_stream(stream(result("You've hit your limit. Resets at 5pm.", is_error=True)), "", ["g"])
        self.assertEqual(r["error"], "limit")
        self.assertEqual(r["steps"], 0)

    def test_empty_output_is_a_network_error(self):
        from run_bench import parse_stream
        self.assertEqual(parse_stream("", "HTTP 403 network not allowed", ["g"])["error"], "network")

    def test_a_real_miss_is_not_an_error(self):
        from run_bench import parse_stream
        r = parse_stream(stream(tool("Grep", pattern="x"), result("I could not find it.")), "", ["g"])
        self.assertIsNone(r["error"])
        self.assertFalse(r["any_gold"])


class Judge(unittest.TestCase):
    def test_parse_flags(self):
        from judge_answers import parse_flags
        self.assertEqual(parse_flags('x {"facts":[{"n":1,"present":true},{"n":2,"present":false}]} y', "present", 3), [True, False, None])
        self.assertEqual(parse_flags("no json", "present", 2), [None, None])

    def test_two_judges_and_scores(self):
        from judge_answers import judge_one
        q = {"id": 1, "question": "q", "facts": ["f1", "f2"]}
        r = {"id": 1, "answer": "a", "opened": []}
        calls = []

        def fake(prompt, model):
            calls.append(prompt)
            if "ANSWER" in prompt:
                return '{"facts":[{"n":1,"present":true},{"n":2,"present":true}]}'
            return '{"facts":[{"n":1,"supported":true},{"n":2,"supported":false}]}'
        with tempfile.TemporaryDirectory() as d:
            row = judge_one(q, r, Path(d), "m", False, fake)
        self.assertEqual((row["score_present"], row["score_grounded"]), (1.0, 0.5))
        self.assertEqual(len(calls), 2)
        self.assertNotIn("ANSWER", calls[1])  # the grounding judge never sees the answer

    def test_limit_stops_and_offline_needs_no_model(self):
        from judge_answers import judge_one
        q = {"id": 1, "question": "q", "facts": [{"text": "f", "any": ["Port 8002"]}, "no-any"]}
        r = {"id": 1, "answer": "it runs on port 8002", "opened": []}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(judge_one(q, r, Path(d), "m", False, lambda p, m: "You've hit your limit")["error"], "limit")
            row = judge_one(q, r, Path(d), "m", True)
        self.assertEqual(row["present"], [True, None])
        self.assertEqual(row["score_present"], 1.0)


class Consoles(unittest.TestCase):
    """Windows consoles with a legacy code page (cp1251) used to crash the tools on characters outside it."""

    def run_py(self, args, encoding):
        env = {**os.environ, "PYTHONIOENCODING": encoding}
        env.pop("PYTHONUTF8", None)
        return subprocess.run([sys.executable, *args], capture_output=True, env=env)

    def test_install_survives_cp1251_and_ascii_consoles(self):
        for enc in ("cp1251", "ascii"):
            with tempfile.TemporaryDirectory() as d:
                t = Path(d) / "проект"
                t.mkdir()
                (t / "CLAUDE.md").write_text("Правила → строгие 🙂\n", encoding="utf-8")
                r = self.run_py([str(KIT / "install.py"), "--target", str(t), "--project", "Мой проект", "--dry-run"], enc)
                self.assertEqual(r.returncode, 0, (enc, r.stderr.decode("utf-8", "replace")))

    def test_lint_survives_cp1251(self):
        with tempfile.TemporaryDirectory() as d:
            w = make_wiki(Path(d), {"a": {"s": "Сводка → пример 🙂", "r": "- [[a]]"}})
            r = self.run_py([str(KIT / "tools" / "wiki_lint.py"), "--wiki", str(w), "--english-only"], "cp1251")
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))


class Style(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ruff"), "ruff is not installed")
    def test_ruff_default_rules_pass_without_a_config(self):
        r = subprocess.run(["ruff", "check", "--isolated", "tools", "install.py", "tests"], cwd=KIT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout)


class Install(unittest.TestCase):
    def test_install_writes_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d)
            (t / "CLAUDE.md").write_text("mine\n", encoding="utf-8")
            r = subprocess.run([sys.executable, "-I", str(KIT / "install.py"), "--target", d, "--project", "Demo", "--tools", "--yes"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual((t / "CLAUDE.md").read_text(encoding="utf-8"), "mine\n")
            self.assertTrue((t / "CLAUDE.template.md").exists())
            self.assertNotIn("{{PROJECT}}", (t / "CLAUDE.template.md").read_text(encoding="utf-8"))
            self.assertTrue((t / "tools" / "wiki_search.py").exists())
            self.assertTrue((t / "wiki" / "index.md").exists())


class NoSecrets(unittest.TestCase):
    def test_no_obvious_secrets_or_hosts(self):
        import re
        bad = re.compile(r"(?i)(BEGIN [A-Z ]*PRIVATE KEY|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|git\.ctll|BabylenMagnus|guts@|password\s*[:=]\s*\S{4,})")
        hits = []
        for p in KIT.rglob("*"):
            if p.is_file() and ".git" not in p.parts and p.suffix in (".py", ".md", ".json", ".sh", ".txt") and p.name != "test_kit.py":
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    line = line.replace("git.ctll.ru/Babylen/llm-wiki-kit", "") if p.name == "INSTALL.md" else line  # the public clone address
                    if bad.search(line):
                        hits.append(f"{p.relative_to(KIT)}:{i}")
        self.assertEqual(hits, [], "possible secret or private host")


if __name__ == "__main__":
    unittest.main()
