"""Smoke tests for the kit. Run: python -I -m unittest discover -s tests -v   (stdlib only, no network, no model)."""
import ast, json, subprocess, sys, tempfile, unittest
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
        for md, py, name in [("bench-agent.md", "run_bench.py", "PROMPT"), ("alias-generation.md", "gen_aliases.py", "PROMPT")]:
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
        import os
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
