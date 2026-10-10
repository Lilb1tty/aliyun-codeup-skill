import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
from codeup_secure import runner
from codeup_secure.errors import CodeupError

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / ".research" / "test-tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class ProcessTreeTests(unittest.TestCase):
    def test_job_handle_close_cannot_race_termination(self):
        from codeup_secure.windows_process import Job
        job = Job.__new__(Job)
        job.handle = 123
        job.lock = threading.Lock()
        job.kernel = Mock()
        entered, release = threading.Event(), threading.Event()
        def terminate(handle, code):
            entered.set()
            self.assertTrue(release.wait(2))
        job.kernel.TerminateJobObject.side_effect = terminate
        terminating = threading.Thread(target=job.terminate)
        closing = threading.Thread(target=job.close)
        terminating.start()
        self.assertTrue(entered.wait(2))
        closing.start()
        try:
            time.sleep(0.05)
            job.kernel.CloseHandle.assert_not_called()
        finally:
            release.set()
            terminating.join(2)
            closing.join(2)
        self.assertFalse(terminating.is_alive())
        self.assertFalse(closing.is_alive())
        job.kernel.CloseHandle.assert_called_once_with(123)
        job.terminate()
        job.kernel.TerminateJobObject.assert_called_once_with(123, 1)
        self.assertIsNone(job.handle)

    def test_credential_validation_timeout_kills_descendant(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            marker = Path(temporary) / "validation-descendant-survived"
            child_code = "import os,time; from pathlib import Path; assert os.environ['ALIBABA_CLOUD_YUNXIAO_ACCESS_TOKEN']=='fake-validation-PAT'; time.sleep(1.5); Path(" + repr(str(marker)) + ").write_text('survived')"
            parent_code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]); time.sleep(10)"
            with self.assertRaises(CodeupError) as found:
                runner.probe(sys.executable, ["-c", parent_code], token="fake-validation-PAT", timeout=0.4)
            self.assertEqual(found.exception.code, "validation_timeout")
            time.sleep(1.8)
            self.assertFalse(marker.exists())

    def test_timeout_kills_descendant(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            marker = Path(temporary) / "descendant-survived"
            child_code = "import time; from pathlib import Path; time.sleep(1.5); Path(" + repr(str(marker)) + ").write_text('survived')"
            parent_code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]); print('spawned',flush=True); time.sleep(10)"
            out = io.BytesIO()
            with self.assertRaises(CodeupError) as found:
                runner.stream(sys.executable, ["-c", parent_code], timeout=0.4, stdout=out, stderr=io.BytesIO())
            self.assertEqual(found.exception.code, "execution_timeout")
            self.assertIn(b"spawned", out.getvalue())
            time.sleep(1.8)
            self.assertFalse(marker.exists(), "Descendant continued after timeout")

    def test_cleanup_kills_descendant_after_parent_exits(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            marker = Path(temporary) / "descendant-survived"
            child_code = "import time; from pathlib import Path; time.sleep(1.5); Path(" + repr(str(marker)) + ").write_text('survived')"
            parent_code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]); print('parent-exit',flush=True)"
            # Timeout remains armed while descendant holds inherited streams.
            with self.assertRaises(CodeupError):
                runner.stream(sys.executable, ["-c", parent_code], timeout=0.4, stdout=io.BytesIO(), stderr=io.BytesIO())
            time.sleep(1.8)
            self.assertFalse(marker.exists())

    @unittest.skipIf(os.name == "nt", "POSIX console signals")
    def test_console_callable_reraises_child_signal(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(sig=sig):
                script = "import codeup_cli; codeup_cli.cli_main=lambda:" + str(-sig) + "; raise SystemExit(codeup_cli.main())"
                result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, -sig)

    @unittest.skipIf(os.name == "nt", "POSIX signal forwarding")
    def test_wrapper_sigterm_forwards_to_child(self):
        script = "from codeup_secure.runner import stream; import sys; raise SystemExit(stream(sys.executable,['-c','import time; print(\"ready\",flush=True); time.sleep(20)']))"
        process = subprocess.Popen([sys.executable, "-c", script], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(process.stdout.readline().strip(), b"ready")
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=5), 128 + signal.SIGTERM)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()
