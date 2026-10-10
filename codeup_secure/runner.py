"""Argument-array subprocesses, per-call credentials, bounded byte redaction."""

import os
import signal
import subprocess
import sys
import threading
from .errors import CodeupError

ENV_TOKEN = "ALIBABA_CLOUD_YUNXIAO_ACCESS_TOKEN"
ENV_URL = "ALIBABA_CLOUD_YUNXIAO_API_BASE_URL"
ENV_ORG = "ALIBABA_CLOUD_YUNXIAO_ORGANIZATION_ID"


def environment(profile: dict | None = None, token: str | None = None) -> dict[str, str]:
    # No mutation of os.environ. Scrub inherited CLI selectors, credentials and debug.
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("ALIBABA_CLOUD_", "ALIYUN_", "YUNXIAO_", "DYLD_"))
           and k.upper() not in {"DEBUG", "LOG_LEVEL", "LD_PRELOAD", "LD_LIBRARY_PATH"}}
    if profile:
        if profile.get("edition") == "region":
            env[ENV_URL] = profile["base_url"]
        if profile.get("organization_id"):
            env[ENV_ORG] = profile["organization_id"]
    if token:
        env[ENV_TOKEN] = token
    return env


class Redactor:
    """Keep only a token-sized suffix; handle occurrences split across chunks."""
    def __init__(self, token: str):
        self.secret = token.encode("utf-8")
        self.pending = b""

    def feed(self, data: bytes, final: bool = False) -> bytes:
        if not self.secret:
            return data
        self.pending += data
        safe = bytearray()
        while True:
            index = self.pending.find(self.secret)
            if index < 0:
                break
            safe.extend(self.pending[:index])
            safe.extend(b"[REDACTED]")
            self.pending = self.pending[index + len(self.secret):]
        # Only an actual PAT prefix at the end can belong to the next chunk.
        keep = 0
        if not final:
            for size in range(min(len(self.pending), len(self.secret) - 1), 0, -1):
                if self.pending.endswith(self.secret[:size]):
                    keep = size
                    break
        boundary = len(self.pending) - keep
        safe.extend(self.pending[:boundary])
        self.pending = self.pending[boundary:]
        return bytes(safe)


def probe(executable: str, args: list[str], profile: dict | None = None,
          token: str | None = None, timeout: float = 30) -> subprocess.CompletedProcess:
    """Discard credential-bearing responses, including all error diagnostics."""
    try:
        with open(os.devnull, "wb") as discarded:
            result = stream(executable, args, profile, token or "", timeout,
                            stdout=discarded, stderr=discarded, stdin=subprocess.DEVNULL)
        return subprocess.CompletedProcess([executable, *args], result)
    except CodeupError as error:
        if error.code == "execution_timeout":
            raise CodeupError("validation_timeout", "Official CLI validation timed out; no credential was saved.") from None
        raise


def validate_dependencies(executable: str) -> None:
    if probe(executable, ["version"]).returncode != 0:
        raise CodeupError("cli_missing", "Official Alibaba CLI is unavailable. Install it using Alibaba documentation.")
    if probe(executable, ["devops", "--help"]).returncode != 0:
        raise CodeupError("plugin_missing", "Install official plugin: aliyun plugin install --names aliyun-cli-devops. Then rerun setup.")


def validate_token(executable: str, profile: dict, token: str) -> None:
    if probe(executable, ["devops", "base-get-user-by-token", "--quiet"], profile, token).returncode != 0:
        raise CodeupError("authentication_failed", "Read-only PAT validation failed. Check token validity, scopes, edition and endpoint; response suppressed.")


def stream(executable: str, args: list[str], profile: dict | None = None,
           token: str = "", timeout: float = 300,
           stdout=None, stderr=None, stdin=None) -> int:
    stdout = stdout or sys.stdout.buffer
    stderr = stderr or sys.stderr.buffer
    job = None
    if os.name == "nt":
        from .windows_process import Job
        job = Job()
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004}
    else:
        options = {"start_new_session": True}
    try:
        child = subprocess.Popen([executable, *args], env=environment(profile, token),
                                 stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 shell=False, **options)
        if job:
            job.attach_and_resume(child)
    except OSError:
        if job:
            job.close()
        raise CodeupError("cli_start_failed", "Cannot start the pinned official CLI.") from None
    failed = threading.Event()
    timed_out = threading.Event()
    interrupted = []

    def terminate(sig=signal.SIGTERM):
        try:
            if os.name == "nt":
                if sig == signal.SIGINT:
                    child.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    job.terminate()
            else:
                os.killpg(child.pid, sig)
        except (OSError, ProcessLookupError):
            pass

    def kill():
        try:
            if os.name == "nt":
                job.terminate()
            else:
                os.killpg(child.pid, signal.SIGKILL)
        except OSError:
            pass

    killers = []

    def stop(sig=signal.SIGTERM):
        terminate(sig)
        timer = threading.Timer(2, kill)
        timer.daemon = True
        killers.append(timer)
        timer.start()

    def expire():
        timed_out.set()
        stop()

    def forward(source, target):
        redactor = Redactor(token)
        try:
            while True:
                data = source.read1(4096)
                safe = redactor.feed(data, final=not data)
                if safe:
                    target.write(safe)
                    target.flush()
                if not data:
                    break
        except (OSError, ValueError):
            failed.set()
            stop()
        finally:
            source.close()

    previous = {}
    if threading.current_thread() is threading.main_thread():
        def handle(sig, frame):
            interrupted.append(sig)
            stop(sig)
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, handle)
    threads = [threading.Thread(target=forward, args=(child.stdout, stdout), daemon=True),
               threading.Thread(target=forward, args=(child.stderr, stderr), daemon=True)]
    timer = threading.Timer(timeout, expire)
    timer.daemon = True
    try:
        for thread in threads:
            thread.start()
        timer.start()
        result = child.wait()
        for thread in threads:
            thread.join(timeout=3)
        if any(thread.is_alive() for thread in threads):
            raise CodeupError("stream_failed", "CLI output streams did not close cleanly.")
    finally:
        timer.cancel()
        for killer in killers:
            killer.cancel()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        kill()
        if job:
            job.close()
    if timed_out.is_set():
        raise CodeupError("execution_timeout", "Official CLI timed out; operation state may be unknown. No automatic retry.")
    if failed.is_set():
        raise CodeupError("stream_failed", "Cannot forward official CLI output.")
    return 128 + interrupted[0] if interrupted else result
