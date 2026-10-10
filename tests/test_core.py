import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock

from codeup_secure import cli, config, credentials, integration, policy, runner
from codeup_secure.errors import CodeupError

TEMP_ROOT = Path(__file__).resolve().parents[1] / ".research" / "test-tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP_ROOT)
TOKEN = "fake-PAT-DO-NOT-USE"
REGION = {"edition": "region", "base_url": "https://example.devops.aliyuncs.com"}
CENTRAL = {"edition": "central", "organization_id": "org-one"}


class MemoryCredentials:
    def __init__(self):
        self.values = {}
        self.sequence = 0
    def put(self, token):
        self.sequence += 1
        ref = "profile-" + f"{self.sequence:032x}"
        self.values[ref] = token
        return ref
    def get(self, ref):
        return self.values.get(ref)
    def delete(self, ref):
        self.values.pop(ref, None)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = config.ConfigStore(Path(self.temp.name) / "config.json")
        self.memory = MemoryCredentials()

    def test_profiles_have_separate_refs_no_plaintext(self):
        cli.store_profile(self.store, self.memory, "region", REGION, TOKEN)
        cli.store_profile(self.store, self.memory, "central", CENTRAL, "other-fake-pat")
        value = self.store.read()
        self.assertNotEqual(value["profiles"]["region"]["credential_ref"], value["profiles"]["central"]["credential_ref"])
        self.assertNotIn(TOKEN, self.store.path.read_text())
        self.assertEqual(value["active"], "central")

    def test_rotation_removes_old_after_commit(self):
        cli.store_profile(self.store, self.memory, "one", REGION, TOKEN)
        old = self.store.read()["profiles"]["one"]["credential_ref"]
        cli.store_profile(self.store, self.memory, "one", REGION, "new-fake-pat", replace=True)
        self.assertNotIn(old, self.memory.values)
        self.assertEqual(list(self.memory.values.values()), ["new-fake-pat"])

    def test_failed_save_preserves_old_reference(self):
        cli.store_profile(self.store, self.memory, "one", REGION, TOKEN)
        before = self.store.read()
        with patch.object(self.store, "save", side_effect=CodeupError("config_write_failed", "Cannot save.")):
            with self.assertRaises(CodeupError):
                cli.store_profile(self.store, self.memory, "one", REGION, "new-fake-pat", replace=True)
        self.assertEqual(self.store.read(), before)
        self.assertEqual(list(self.memory.values.values()), [TOKEN])

    def test_duplicate_add_leaves_no_orphan(self):
        cli.store_profile(self.store, self.memory, "one", REGION, TOKEN)
        with self.assertRaises(CodeupError):
            cli.store_profile(self.store, self.memory, "one", REGION, "other-fake-pat")
        self.assertEqual(list(self.memory.values.values()), [TOKEN])

    def test_corrupt_metadata_is_not_silently_reset(self):
        self.store.path.write_text("broken-json")
        with self.assertRaises(CodeupError):
            self.store.read()
        self.assertEqual(self.store.path.read_text(), "broken-json")

    def test_reject_secret_fields(self):
        value = {"version": 2, "active": "one", "profiles": {"one": {**REGION, "token": TOKEN}}}
        with self.assertRaises(CodeupError):
            self.store.save(value)
        self.assertFalse(self.store.path.exists())

    def test_legacy_migration_keeps_native_reference(self):
        self.store.path.write_text(json.dumps(CENTRAL))
        value = self.store.read()
        self.assertEqual(value["profiles"]["default"]["credential_ref"], "yunxiao-access-token")
        self.assertNotIn("executable", value)

    def test_remove_active_switches_and_deletes_only_its_credential(self):
        cli.store_profile(self.store, self.memory, "one", REGION, TOKEN)
        cli.store_profile(self.store, self.memory, "two", CENTRAL, "other-fake-pat")
        args = cli.parser().parse_args(["profile", "remove", "two"])
        with patch.object(cli, "Credentials", return_value=self.memory), contextlib.redirect_stdout(io.StringIO()):
            cli.profiles(args, self.store)
        self.assertEqual(self.store.read()["active"], "one")
        self.assertEqual(list(self.memory.values.values()), [TOKEN])

    def test_locked_mutations_preserve_other_profiles(self):
        failures = []
        def add(n):
            try:
                with self.store.transaction() as value:
                    value["profiles"][f"profile{n}"] = dict(REGION)
            except Exception as error:
                failures.append(error)
        threads = [threading.Thread(target=add, args=(n,)) for n in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(len(self.store.read()["profiles"]), 8)

    @unittest.skipIf(os.name == "nt", "POSIX mode check")
    def test_metadata_mode_private(self):
        self.store.save(self.store.read())
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)


class ValidationTests(unittest.TestCase):
    def test_endpoint_rejection(self):
        bad = ["http://example.aliyuncs.com", "https://evil.test", "https://aliyuncs.com.evil.test",
               "https://user:password@example.aliyuncs.com", "https://example.aliyuncs.com/token",
               "https://example.aliyuncs.com/?token=x", "https://example.aliyuncs.com#fragment",
               "https://example.aliyuncs.com:8443", "https://example.aliyuncs.com\\@evil.test",
               "https://tenant.oss-cn-beijing.aliyuncs.com", "https://tenant.aliyuncs.com",
               "https://test.devops.aliyun.com", "https://test.alibabacloud.com",
               "https://nested.instance.devops.aliyuncs.com"]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(CodeupError):
                config.validate_url(value)

    def test_known_alibaba_hosts(self):
        for value in [config.DEFAULT_URL, "https://test.devops.aliyuncs.com", "https://test-region.devops.aliyuncs.com/"]:
            self.assertEqual(config.validate_url(value), value.rstrip("/"))

    def test_expiration(self):
        with self.assertRaises(CodeupError):
            config.check_expiry({**REGION, "expires_at": "2000-01-01T00:00:00Z"})
        with self.assertRaises(CodeupError):
            config.expiry("2026-01-01")
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        config.check_expiry({**REGION, "expires_at": future})

    def test_native_executable_pinning_and_change(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ("aliyun.exe" if os.name == "nt" else "aliyun")
            path.write_bytes(b"MZfake" if os.name == "nt" else b"\x7fELFfake")
            path.chmod(0o700)
            safe_parents = os.name == "nt" or all(
                not (node.stat().st_mode & 0o022) and node.stat().st_uid in (0, os.geteuid())
                for node in (path, *path.parents))
            if safe_parents:
                pin = config.pin_executable(str(path))
                self.assertEqual(config.verified_executable({"executable": pin}), str(path))
                path.write_bytes(path.read_bytes() + b"changed")
                with self.assertRaises(CodeupError):
                    config.verified_executable({"executable": pin})
            else:
                with self.assertRaises(CodeupError):
                    config.pin_executable(str(path))

    def test_no_scripts_or_relative_executable(self):
        with self.assertRaises(CodeupError):
            config.pin_executable("aliyun")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aliyun.cmd"
            path.write_text("echo hi")
            with self.assertRaises(CodeupError):
                config.pin_executable(str(path))

    @unittest.skipIf(os.name == "nt", "POSIX ownership")
    def test_other_user_owner_is_rejected(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aliyun"
            path.write_bytes(b"\x7fELFfixture")
            path.chmod(0o700)
            original_stat = type(path).stat
            for untrusted in (path, path.parent):
                def altered_stat(node, *args, **kwargs):
                    info = original_stat(node, *args, **kwargs)
                    if node == untrusted:
                        return SimpleNamespace(st_mode=info.st_mode, st_uid=os.geteuid() + 12345)
                    return info
                with patch.object(type(path), "stat", new=altered_stat), self.assertRaises(CodeupError):
                    config.pin_executable(str(path))

    def test_getpass_fallback_refused(self):
        with patch.object(getpass_module := cli.getpass, "getpass", side_effect=getpass_module.GetPassWarning("echo")):
            with self.assertRaises(CodeupError):
                cli.secret_prompt()

    def test_no_automatic_keyring_install(self):
        with patch("keyring.get_keyring", return_value=Mock(priority=1)):
            with self.assertRaises(CodeupError):
                credentials.Credentials()

    def test_keyring_exception_hides_secret(self):
        vault = credentials.Credentials.__new__(credentials.Credentials)
        vault.backend = Mock()
        vault.backend.get_password.side_effect = RuntimeError(TOKEN)
        with self.assertRaises(CodeupError) as found:
            vault.get("profile-test")
        self.assertNotIn(TOKEN, str(found.exception))


class PolicyTests(unittest.TestCase):
    def test_reads_pass(self):
        for command in ("codeup-list-repositories", "projex-search-workitems", "base-get-user-by-token", "flow-get-pipeline-run"):
            self.assertFalse(policy.check([command, "--page", "1"]))

    def test_writes_and_unknown_blocked(self):
        for command in ("projex-create-workitem", "codeup-merge-merge-request", "flow-start-pipeline", "codeup-unknown-operation", "flow-get-run-pipeline", "codeup-get-delete-repository", "codeup-list-unknown-operation"):
            with self.subTest(command=command), self.assertRaises(CodeupError):
                policy.check([command])

    def test_destructive_needs_both_flags(self):
        with self.assertRaises(CodeupError):
            policy.check(["codeup-delete-repository"], authorization=policy.Authorization(write=True))
        self.assertFalse(policy.check(["codeup-delete-repository"], authorization=policy.Authorization(write=True, destructive=True)))

    def test_flow_and_appstack_writes_require_deployment(self):
        for command in ("flow-create-pipeline-run", "app-stack-create-change-order", "flow-update-pipeline"):
            with self.subTest(command=command), self.assertRaises(CodeupError):
                policy.check([command], authorization=policy.Authorization(write=True))
            self.assertFalse(policy.check([command], authorization=policy.Authorization(write=True, deployment=True)))

    def test_allow_does_not_grant_write_and_deny_wins(self):
        with self.assertRaises(CodeupError):
            policy.check(["codeup-create-repository"], {"allow": ["codeup-*"]})
        with self.assertRaises(CodeupError):
            policy.check(["codeup-delete-repository"], {"allow": ["*"], "deny": ["codeup-delete-*"]}, policy.Authorization(True, True, True))
        with self.assertRaises(CodeupError):
            policy.check(["codeup-list-repositories"], {"allow": []})

    def test_unsafe_flags_in_split_equal_and_case_forms(self):
        for flag in policy.BLOCKED:
            for value in (flag, flag + "=danger", flag.upper()):
                with self.subTest(flag=value), self.assertRaises(CodeupError):
                    policy.check(["codeup-list-repositories", value])

    def test_help_exact_only(self):
        self.assertTrue(policy.check(["--help"]))
        self.assertTrue(policy.check(["codeup-delete-repository", "--help"]))
        for flags in (["--help=false"], ["--help", "--repository-id", "42"], ["-h=false"]):
            with self.assertRaises(CodeupError):
                policy.check(["codeup-delete-repository", *flags])

    def test_no_arbitrary_shell_or_foreign_family(self):
        for args in (["bash", "-c", "echo secret"], ["ecs", "DescribeInstances"], ["help", "--token", TOKEN], ["codeup-list-repositories\x00"]):
            with self.assertRaises(CodeupError):
                policy.check(args)


class RunnerTests(unittest.TestCase):
    def test_environment_is_local_and_scrubbed(self):
        polluted = {runner.ENV_TOKEN: "inherited-token", runner.ENV_URL: "https://evil.test", runner.ENV_ORG: "wrong-org", "ALIYUN_DEBUG": "1", "LD_PRELOAD": "evil.so"}
        with patch.dict(os.environ, polluted):
            original = dict(os.environ)
            env = runner.environment(REGION, TOKEN)
            self.assertEqual(env[runner.ENV_TOKEN], TOKEN)
            self.assertNotIn(runner.ENV_ORG, env)
            self.assertNotIn("ALIYUN_DEBUG", env)
            self.assertNotIn("LD_PRELOAD", env)
            self.assertEqual(dict(os.environ), original)
            self.assertNotIn(runner.ENV_TOKEN, runner.environment())

    def test_redacts_every_chunk_boundary_binary_safe(self):
        raw = b"prefix\x00" + TOKEN.encode() + TOKEN.encode() + b"\xffsuffix"
        for size in range(1, len(raw) + 1):
            redactor = runner.Redactor(TOKEN)
            result = b"".join(redactor.feed(raw[n:n + size]) for n in range(0, len(raw), size)) + redactor.feed(b"", final=True)
            self.assertEqual(result, b"prefix\x00[REDACTED][REDACTED]\xffsuffix")

    def test_large_line_bounded_and_no_json_changes(self):
        redactor = runner.Redactor(TOKEN)
        data = b'x' * 100000
        self.assertEqual(redactor.feed(data) + redactor.feed(b"", final=True), data)
        self.assertEqual(runner.Redactor(TOKEN).feed(b'{"token":"unrelated-output"}\n', final=True), b'{"token":"unrelated-output"}\n')

    def test_nonsecret_interactive_prompt_is_immediate(self):
        self.assertEqual(runner.Redactor(TOKEN).feed(b"Continue? "), b"Continue? ")

    def test_overlapping_token_prefixes_do_not_leak(self):
        for token in ("abab", "aaaa", "abcab", "aba"):
            data = (token * 3 + "tail").encode()
            for size in range(1, len(data)):
                redactor = runner.Redactor(token)
                result = b"".join(redactor.feed(data[i:i + size]) for i in range(0, len(data), size)) + redactor.feed(b"", final=True)
                self.assertEqual(result, b"[REDACTED]" * 3 + b"tail")

    def test_stream_preserves_argv_stdin_bytes_and_exit(self):
        script = "import os,sys,json; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); print(json.dumps(sys.argv[1:])); sys.stderr.write(os.environ['ALIBABA_CLOUD_YUNXIAO_ACCESS_TOKEN']); sys.exit(7)"
        with tempfile.TemporaryFile() as input_file:
            input_file.write(b"input\x00\xff\n"); input_file.seek(0)
            out, err = io.BytesIO(), io.BytesIO()
            code = runner.stream(sys.executable, ["-c", script, "space value", 'quote"value', "$(no-shell)", "--page", "3"], REGION, TOKEN, stdout=out, stderr=err, stdin=input_file)
        self.assertEqual(code, 7)
        self.assertTrue(out.getvalue().startswith(b"input\x00\xff\n"))
        self.assertIn(b"$(no-shell)", out.getvalue())
        self.assertTrue(err.getvalue().endswith(b"[REDACTED]"))
        self.assertNotIn(TOKEN.encode(), err.getvalue())

    def test_timeout_no_retry(self):
        with self.assertRaises(CodeupError) as error:
            runner.stream(sys.executable, ["-c", "import time; time.sleep(20)"], timeout=0.1, stdout=io.BytesIO(), stderr=io.BytesIO())
        self.assertEqual(error.exception.code, "execution_timeout")

    def test_probe_never_captures_sensitive_diagnostics(self):
        with patch.object(runner, "stream", return_value=0) as call:
            runner.validate_token("pinned-aliyun", REGION, TOKEN)
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["stdout"].name, os.devnull)
        self.assertEqual(kwargs["stderr"].name, os.devnull)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn(TOKEN, call.call_args.args[1])

    def test_concurrent_environments_do_not_mix_profiles(self):
        results = {}
        def execute(n):
            out = io.BytesIO()
            token = f"fake-token-{n}"
            runner.stream(sys.executable, ["-c", "import os; print(os.environ['ALIBABA_CLOUD_YUNXIAO_ORGANIZATION_ID']); print(os.environ['ALIBABA_CLOUD_YUNXIAO_ACCESS_TOKEN'])"], {**CENTRAL, "organization_id": f"org-{n}"}, token, stdout=out, stderr=io.BytesIO())
            results[n] = out.getvalue()
        threads = [threading.Thread(target=execute, args=(n,)) for n in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        normalized = {n: value.replace(b"\r\n", b"\n") for n, value in results.items()}
        self.assertEqual(normalized, {n: f"org-{n}\n[REDACTED]\n".encode() for n in range(4)})

    @unittest.skipIf(os.name == "nt", "POSIX signal semantics")
    def test_child_signal_is_preserved(self):
        result = runner.stream(sys.executable, ["-c", "import os,signal; os.kill(os.getpid(),signal.SIGTERM)"], stdout=io.BytesIO(), stderr=io.BytesIO())
        self.assertEqual(result, -signal.SIGTERM)


class CliTests(unittest.TestCase):
    def setUp(self):
        ConfigTests.setUp(self)
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "ConfigStore", return_value=self.store), patch.object(cli, "Credentials", return_value=self.memory), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_delegation_preserves_help_and_flags(self):
        with patch.object(cli, "verified_executable", return_value="trusted-aliyun"), patch.object(runner, "stream", return_value=0) as stream:
            self.assertEqual(self.run_cli(["devops", "--help"])[0], 0)
            self.assertEqual(stream.call_args.args[:2], ("trusted-aliyun", ["devops", "--help"]))
            self.assertEqual(self.run_cli(["exec", "--", "aliyun", "devops", "codeup-list-repositories", "--help"])[0], 0)
            self.assertEqual(stream.call_args.args[1], ["devops", "codeup-list-repositories", "--help"])

    def test_policy_before_credential_retrieval(self):
        with patch.object(cli, "Credentials") as vault:
            code, _, err = self.run_cli(["exec", "--", "aliyun", "devops", "codeup-delete-repository"])
        self.assertEqual(code, 2)
        self.assertIn("write_authorization_required", err)
        vault.assert_not_called()

    def test_selected_profile_injected_automatically(self):
        cli.store_profile(self.store, self.memory, "one", REGION, TOKEN)
        with patch.object(cli, "verified_executable", return_value="trusted-aliyun"), patch.object(runner, "stream", return_value=0) as stream:
            code, _, _ = self.run_cli(["exec", "--", "aliyun", "devops", "codeup-list-repositories", "--cli-query", "result[]", "--all-pages"])
        self.assertEqual(code, 0)
        self.assertEqual(stream.call_args.args[3], TOKEN)
        self.assertEqual(stream.call_args.args[2]["base_url"], REGION["base_url"])

    def test_invalid_exec_and_token_errors_are_sanitized(self):
        for argv in (["exec", "--", "powershell", "-Command", TOKEN], ["devops", "codeup-list-repositories", "--yunxiao-access-token=" + TOKEN]):
            code, out, err = self.run_cli(argv)
            self.assertEqual(code, 2)
            self.assertNotIn(TOKEN, out + err)
        with self.assertRaises(SystemExit):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                cli.main(["--unknown-token", TOKEN])
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())

    def test_nonfinite_timeout_refused(self):
        for value in ("nan", "inf", "0", "-1"):
            self.assertEqual(self.run_cli(["--timeout", value, "devops", "--help"])[0], 2)

    def test_failed_setup_validation_saves_nothing(self):
        args = cli.parser().parse_args(["setup", "--edition", "region", "--base-url", REGION["base_url"], "--name", "one"])
        with patch.object(cli, "select_option", return_value="en"), patch.object(cli, "choose_executable", return_value={"path": "fake", "sha256": "0" * 64}), patch.object(cli, "Credentials", return_value=self.memory), patch.object(cli, "secret_prompt", return_value=TOKEN), patch.object(runner, "validate_token", side_effect=CodeupError("authentication_failed", "Failed.")):
            with self.assertRaises(CodeupError):
                cli.setup(args, self.store)
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.memory.values, {})

    def test_successful_setup_validates_before_storage(self):
        args = cli.parser().parse_args(["setup", "--edition", "region", "--base-url", REGION["base_url"], "--name", "one"])
        pin = {"path": str(Path(self.temp.name) / "aliyun"), "sha256": "0" * 64}
        def validated(*arguments):
            self.assertEqual(self.memory.values, {})
            self.assertFalse(self.store.path.exists())
        with patch.object(cli, "select_option", return_value="en"), patch.object(cli, "choose_executable", return_value=pin), patch.object(cli, "pin_executable", return_value=pin), patch.object(cli, "Credentials", return_value=self.memory), patch.object(cli, "secret_prompt", return_value=TOKEN), patch.object(runner, "validate_token", side_effect=validated), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.setup(args, self.store), 0)
        self.assertEqual(self.store.read()["active"], "one")
        self.assertEqual(list(self.memory.values.values()), [TOKEN])

    def test_setup_blank_input_keeps_org_pat_reference_and_expiry(self):
        original_profile = {**CENTRAL, "expires_at": "2099-01-01T00:00:00Z"}
        cli.store_profile(self.store, self.memory, "one", original_profile, TOKEN)
        original = self.store.read()["profiles"]["one"]
        args = cli.parser().parse_args(["setup", "--edition", "central", "--name", "one"])
        pin = {"path": str(Path(self.temp.name) / "aliyun"), "sha256": "0" * 64}
        with patch.object(cli, "select_option", return_value="en"), patch.object(cli, "choose_executable", return_value=pin), patch.object(cli, "pin_executable", return_value=pin), patch.object(cli, "Credentials", return_value=self.memory), patch.object(cli.getpass, "getpass", return_value=""), patch("builtins.input", return_value=""), patch.object(runner, "validate_token") as validation, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.setup(args, self.store), 0)
        self.assertEqual(self.store.read()["profiles"]["one"], original)
        self.assertEqual(list(self.memory.values.values()), [TOKEN])
        self.assertEqual(self.memory.sequence, 1)
        self.assertEqual(validation.call_args.args[2], TOKEN)
        self.assertEqual(validation.call_args.args[1]["organization_id"], CENTRAL["organization_id"])

    def test_blank_pat_without_stored_credential_is_rejected(self):
        args = cli.parser().parse_args(["setup", "--edition", "region", "--base-url", REGION["base_url"]])
        pin = {"path": "unused", "sha256": "0" * 64}
        with patch.object(cli, "select_option", return_value="en"), patch.object(cli, "choose_executable", return_value=pin), patch.object(cli, "Credentials", return_value=self.memory), patch.object(cli.getpass, "getpass", return_value=""), patch.object(runner, "validate_token") as validation:
            with self.assertRaises(CodeupError):
                cli.setup(args, self.store)
        validation.assert_not_called()
        self.assertFalse(self.store.path.exists())

    def test_empty_cli_trust_answer_means_yes(self):
        args = cli.parser().parse_args(["setup"])
        pin = {"path": str(Path(self.temp.name) / "aliyun"), "sha256": "0" * 64}
        with patch.object(cli.shutil, "which", return_value=pin["path"]), patch.object(cli, "pin_executable", return_value=pin), patch.object(runner, "validate_dependencies") as validation, patch("builtins.input", return_value=""), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.choose_executable(args, {}), pin)
        validation.assert_called_once_with(pin["path"])

    def test_explicit_no_cli_trust_answer_still_rejected(self):
        args = cli.parser().parse_args(["setup"])
        with patch.object(cli.shutil, "which", return_value="discovered-cli"), patch.object(runner, "validate_dependencies") as validation, patch("builtins.input", return_value="n"), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(CodeupError):
                cli.choose_executable(args, {})
        validation.assert_not_called()

    def test_auth_rotation_does_not_switch_active_profile(self):
        cli.store_profile(self.store, self.memory, "one", REGION, TOKEN)
        expected = self.store.read()["profiles"]["one"]
        cli.store_profile(self.store, self.memory, "two", CENTRAL, "other-fake-pat")
        cli.store_profile(self.store, self.memory, "one", REGION, "new-fake-pat", replace=True, expected=expected, activate=False)
        self.assertEqual(self.store.read()["active"], "two")

    def test_optimistic_rotation_preserves_concurrent_profile_changes(self):
        cli.store_profile(self.store, self.memory, "one", REGION, TOKEN)
        expected = self.store.read()["profiles"]["one"]
        with self.store.transaction() as value:
            value["profiles"]["one"]["default_project"] = "changed"
        with self.assertRaises(CodeupError):
            cli.store_profile(self.store, self.memory, "one", REGION, "new-fake-pat", replace=True, expected=expected)
        self.assertEqual(self.store.read()["profiles"]["one"]["default_project"], "changed")
        self.assertEqual(list(self.memory.values.values()), [TOKEN])

    def test_delete_failure_keeps_profile_and_reference(self):
        cli.store_profile(self.store, self.memory, "one", REGION, TOKEN)
        original = self.store.read()
        for argv in (["profile", "remove", "one"], ["auth", "revoke"]):
            with patch.object(self.memory, "delete", side_effect=CodeupError("credential_delete_failed", "Cannot delete.")):
                self.assertEqual(self.run_cli(argv)[0], 2)
            self.assertEqual(self.store.read(), original)


class IntegrationTests(unittest.TestCase):
    def test_both_project_adapters_reuse_unchanged_upstream(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "upstream"
            official.mkdir()
            (official / "SKILL.md").write_text("---\nname: alibabacloud-devops\n---\nOfficial workflow\n")
            (official / "reference.txt").write_bytes(b"reference\x00")
            for agent, surface in (("claude", ".claude"), ("codex", ".agents")):
                result = integration.install(agent, root, official)
                target = root / surface / "skills" / "aliyun-devops"
                self.assertEqual(Path(result["path"]), target)
                self.assertEqual((target / "references" / "official" / "SKILL.md").read_bytes(), (official / "SKILL.md").read_bytes())
                self.assertEqual((target / "references" / "official" / "reference.txt").read_bytes(), b"reference\x00")
                text = (target / "SKILL.md").read_text()
                self.assertIn("codeup exec -- aliyun devops", text)
                self.assertIn("active profile automatically", text)
                with self.assertRaises(CodeupError):
                    integration.install(agent, root, official)


if __name__ == "__main__":
    unittest.main()
