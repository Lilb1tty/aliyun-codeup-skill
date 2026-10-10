"""Whole CLI tests with simulated OS vault and official CLI, never live API writes."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from codeup_secure.config import ConfigStore
from codeup_secure.integration import install

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / ".research" / "test-tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
FAKE_TOKEN = "e2e-fake-PAT-not-a-real-credential"
REFERENCE = "profile-" + "a" * 32

FAKE_CLI = '''import json,os,sys,time
token = os.environ.get("ALIBABA_CLOUD_YUNXIAO_ACCESS_TOKEN", "")
args = sys.argv[1:]
if "--help" in args:
    assert not token
    print("official-help")
else:
    data = sys.stdin.buffer.read().decode()
    print(json.dumps({"args":args,"input":data,"org":os.environ.get("ALIBABA_CLOUD_YUNXIAO_ORGANIZATION_ID")}))
    for char in token:
        sys.stderr.write(char); sys.stderr.flush()
    sys.exit(9 if "--fail" in args else 0)
'''

BOOTSTRAP = '''import sys
from pathlib import Path
from codeup_secure import cli
from codeup_secure.config import ConfigStore
class FakeVault:
    def get(self, reference):
        assert reference == "profile-" + "a" * 32
        return "e2e-fake-PAT-not-a-real-credential"
cli.Credentials = FakeVault
cli.ConfigStore = lambda: ConfigStore(Path("metadata.json"))
# Explicit fixture replacement, not a production flag or environment bypass.
cli.verified_executable = lambda config: sys.executable
raise SystemExit(cli.main(sys.argv[1:]))
'''


class WholeCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / "devops").write_text(FAKE_CLI, encoding="utf-8")
        (self.project / "bootstrap.py").write_text(BOOTSTRAP, encoding="utf-8")
        ConfigStore(self.project / "metadata.json").save({"version": 2, "active": "test",
            "profiles": {"test": {"edition": "central", "organization_id": "test-org", "credential_ref": REFERENCE}}})

    def execute(self, *args, input=""):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        return subprocess.run([sys.executable, "bootstrap.py", *args], cwd=self.project,
            input=input, capture_output=True, text=True, env=env, timeout=15)

    def test_both_adapters_and_command_dispatch_work_together(self):
        official = self.project / "official"
        official.mkdir()
        (official / "SKILL.md").write_text("Official workflow: list projects through aliyun devops projex-search-projects.\n")
        for agent in ("claude", "codex"):
            adapter = Path(install(agent, self.project, official)["path"])
            instructions = (adapter / "SKILL.md").read_text()
            self.assertIn("codeup exec -- aliyun devops", instructions)
            result = self.execute("exec", "--", "aliyun", "devops", "projex-search-projects", "--page", "1", "--cli-query", "result[]", input="stdin intact")
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual(value["args"], ["projex-search-projects", "--page", "1", "--cli-query", "result[]"])
            self.assertEqual(value["input"], "stdin intact")
            self.assertEqual(value["org"], "test-org")
            self.assertNotIn(FAKE_TOKEN, result.stdout + result.stderr)
            self.assertTrue(result.stderr.endswith("[REDACTED]"))

    def test_help_requires_no_vault_access(self):
        result = self.execute("devops", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "official-help")
        self.assertNotIn("[REDACTED]", result.stderr)

    def test_exit_code_preserved(self):
        result = self.execute("exec", "--", "aliyun", "devops", "codeup-list-repositories", "--fail")
        self.assertEqual(result.returncode, 9)

    def test_write_and_secret_flag_denied_before_fake_cli(self):
        for args in (("codeup-delete-repository",), ("codeup-list-repositories", "--yunxiao-access-token=" + FAKE_TOKEN)):
            result = self.execute("exec", "--", "aliyun", "devops", *args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn(FAKE_TOKEN, result.stderr)


if __name__ == "__main__":
    unittest.main()
