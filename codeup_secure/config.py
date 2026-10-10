"""Non-secret profile metadata, atomic writes and cross-process mutation lock."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from urllib.parse import urlsplit
from .errors import CodeupError

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
DEFAULT_URL = "https://openapi-rdc.aliyuncs.com"


def data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "aliyun-cli-devops"


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise CodeupError("invalid_profile", "Profile name: 1-64 letters, digits, dots, underscores or hyphens; start with letter/digit.")
    return name


def validate_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        # Provider namespaces also contain tenant-controlled non-DevOps services.
        # Restrict credentials to documented Yunxiao service hostname forms.
        valid_host = host == "openapi-rdc.aliyuncs.com" or bool(re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.devops\.aliyuncs\.com", host))
        valid = (parsed.scheme == "https" and valid_host and parsed.port in (None, 443)
                 and not parsed.username and not parsed.password and parsed.path in ("", "/")
                 and not parsed.query and not parsed.fragment and not re.search(r"[\s\\%]", value)
                 and all(c.isprintable() for c in value))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise CodeupError("invalid_endpoint", "Use the official central endpoint or https://INSTANCE.devops.aliyuncs.com without credentials, path, query, fragment or custom port.")
    return value.rstrip("/")


def expiry(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (ValueError, AttributeError):
        raise CodeupError("invalid_expiry", "Expiration must be an ISO 8601 timestamp with timezone, e.g. 2026-12-01T00:00:00Z.") from None


def check_expiry(profile: dict) -> None:
    end = expiry(profile.get("expires_at"))
    if end and end <= datetime.now(timezone.utc):
        raise CodeupError("credential_expired", "Recorded PAT expiration reached. Run codeup auth rotate.")


def validate_profile(profile: dict) -> None:
    fields = {"edition", "base_url", "organization_id", "credential_ref", "expires_at", "default_project"}
    if not isinstance(profile, dict) or set(profile) - fields:
        raise CodeupError("invalid_config", "Profile contains unsupported metadata fields.")
    if profile.get("edition") not in ("central", "region"):
        raise CodeupError("invalid_config", "Profile edition must be central or region.")
    validate_url(profile.get("base_url", DEFAULT_URL))
    if profile["edition"] == "region" and not profile.get("base_url"):
        raise CodeupError("invalid_config", "Regional profile requires API base URL.")
    if profile["edition"] == "region" and profile["base_url"].rstrip("/").lower() == DEFAULT_URL:
        raise CodeupError("invalid_config", "Regional profile requires its documented instance endpoint, not the central endpoint.")
    if profile["edition"] == "central" and profile.get("base_url", DEFAULT_URL) != DEFAULT_URL:
        raise CodeupError("invalid_config", "Central profile uses the official default API endpoint.")
    org = profile.get("organization_id")
    if profile["edition"] == "central" and not org:
        raise CodeupError("invalid_config", "Central profile requires organization ID.")
    for field in ("organization_id", "default_project", "credential_ref"):
        value = profile.get(field)
        if value is not None and (not isinstance(value, str) or not value or len(value) > 256
                                  or any(c.isspace() or not c.isprintable() for c in value)):
            raise CodeupError("invalid_config", "Invalid non-sensitive profile metadata.")
    if profile.get("credential_ref") and not re.fullmatch(r"profile-[0-9a-f]{32}|yunxiao-access-token", profile["credential_ref"]):
        raise CodeupError("invalid_config", "Unsupported credential reference.")
    expiry(profile.get("expires_at"))


def validate_config(config: dict) -> None:
    if (not isinstance(config, dict) or config.get("version") != 2
            or set(config) - {"version", "active", "profiles", "executable", "policy"}
            or not isinstance(config.get("profiles"), dict)):
        raise CodeupError("invalid_config", "Invalid configuration schema; inspect non-secret metadata or rerun setup.")
    for name, profile in config["profiles"].items():
        validate_name(name)
        validate_profile(profile)
    if config.get("active") is not None and config["active"] not in config["profiles"]:
        raise CodeupError("invalid_config", "Active profile does not exist.")
    executable = config.get("executable")
    if executable is not None:
        if (not isinstance(executable, dict) or set(executable) != {"path", "sha256"}
                or not isinstance(executable["path"], str) or not Path(executable["path"]).is_absolute()
                or not isinstance(executable["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", executable["sha256"])):
            raise CodeupError("invalid_config", "Executable must have an absolute path and SHA-256 pin.")
    policy = config.get("policy", {})
    if not isinstance(policy, dict) or set(policy) - {"allow", "deny"}:
        raise CodeupError("invalid_config", "Policy supports only allow and deny command patterns.")
    for patterns in policy.values():
        if not isinstance(patterns, list) or any(not isinstance(p, str) or not re.fullmatch(r"[a-z0-9*?-]{1,160}", p) for p in patterns):
            raise CodeupError("invalid_config", "Policy patterns must be command names or glob patterns.")


def selected(config: dict, name: str | None = None) -> tuple[str, dict]:
    name = name or config.get("active")
    if name is None or name not in config["profiles"]:
        raise CodeupError("profile_missing", "No selected profile. Run codeup setup or codeup profile use NAME.")
    return name, dict(config["profiles"][name])


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "config.json"

    def read(self) -> dict:
        if not self.path.exists():
            return {"version": 2, "active": None, "profiles": {}}
        if self.path.is_symlink():
            raise CodeupError("unsafe_config", "Configuration must not be a symbolic link.")
        try:
            if self.path.stat().st_size > 1_048_576:
                raise ValueError()
            config = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise CodeupError("invalid_config", "Cannot read profile metadata; configuration was not changed.") from None
        if isinstance(config, dict) and "version" not in config and config.get("edition"):
            legacy = {k: config[k] for k in ("edition", "base_url", "organization_id") if k in config}
            if legacy["edition"] == "central":
                legacy.pop("base_url", None)
            legacy["credential_ref"] = "yunxiao-access-token"
            config = {"version": 2, "active": "default", "profiles": {"default": legacy}}
        validate_config(config)
        return config

    def save(self, config: dict) -> None:
        validate_config(config)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self.path.parent.chmod(0o700)
        fd, name = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(config, target, indent=2)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(name, self.path)
        except OSError:
            raise CodeupError("config_write_failed", "Cannot atomically save profile metadata.") from None
        finally:
            Path(name).unlink(missing_ok=True)

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.path.with_suffix(".lock")
        if lock_path.is_symlink():
            raise CodeupError("unsafe_config", "Configuration lock must not be a symbolic link.")
        with lock_path.open("a+b") as lock:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            deadline = time.monotonic() + 10
            while True:
                try:
                    lock.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise CodeupError("config_busy", "Profile metadata is busy; retry later.") from None
                    time.sleep(0.05)
            try:
                config = self.read()
                yield config
                self.save(config)
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(131072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pin_executable(value: str) -> dict:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise CodeupError("unsafe_executable", "Select an absolute native Alibaba CLI executable path, not a symlink or shell script.")
    try:
        path = path.resolve(strict=True)
        info = path.stat()
        with path.open("rb") as source:
            header = source.read(4)
        native = header[:2] == b"MZ" if os.name == "nt" else header == b"\x7fELF" or header in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf")
        if not stat.S_ISREG(info.st_mode) or not native or (os.name != "nt" and not os.access(path, os.X_OK)):
            raise ValueError()
        if os.name != "nt":
            for node in (path, *path.parents):
                node_info = node.stat()
                if node_info.st_mode & 0o022 or node_info.st_uid not in (0, os.geteuid()):
                    raise ValueError()
        return {"path": str(path), "sha256": file_hash(path)}
    except (OSError, ValueError):
        raise CodeupError("unsafe_executable", "CLI must be native, executable, and protected from other-user replacement.") from None


def verified_executable(config: dict) -> str:
    expected = config.get("executable")
    if not expected:
        raise CodeupError("executable_unpinned", "CLI executable is not pinned. Run codeup setup or codeup config set --cli-path ABSOLUTE_PATH.")
    actual = pin_executable(expected["path"])
    if actual != expected:
        raise CodeupError("executable_changed", "CLI executable changed. Verify official installation, then explicitly repin with codeup config set --cli-path.")
    return actual["path"]
