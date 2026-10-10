"""Setup, profiles, diagnostics and secure official CLI execution."""

import argparse
import getpass
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import warnings
from . import __version__, integration, policy, runner
from .config import (ConfigStore, DEFAULT_URL, check_expiry, pin_executable,
                     selected, validate_name, validate_profile, validate_url,
                     verified_executable)
from .credentials import Credentials
from .errors import CodeupError
from .ui import select_option


def output(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=True, indent=2))


def secret_prompt(label: str = "Yunxiao PAT (hidden): ", allow_empty: bool = False) -> str:
    # getpass's echoed stdin fallback is forbidden.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass(label)
    except (getpass.GetPassWarning, EOFError):
        raise CodeupError("secure_input_unavailable", "Hidden terminal input unavailable. Run setup/auth in an interactive terminal; never paste PAT into chat or arguments.") from None
    if not token and allow_empty:
        return token
    if not token or len(token) > 4096 or any(c.isspace() or not c.isprintable() for c in token):
        raise CodeupError("invalid_token", "PAT must be nonempty, printable, without whitespace (maximum 4096 characters).")
    return token


def choose_executable(args, config: dict) -> dict:
    candidate = args.cli_path or (config.get("executable") or {}).get("path")
    if not candidate:
        candidate = shutil.which("aliyun")
        if not candidate:
            print("Install Alibaba CLI: https://www.alibabacloud.com/help/en/cli/")
            print("Install plugin: aliyun plugin install --names aliyun-cli-devops")
            raise CodeupError("cli_missing", "Install official CLI, then rerun setup with --cli-path ABSOLUTE_PATH.")
        print("Discovered CLI:", candidate)
        if input("Verify official CLI and trust this path? [Y/n]: ").lower().strip() not in ("", "y", "yes"):
            raise CodeupError("executable_untrusted", "Select a verified official CLI path using --cli-path.")
    pin = pin_executable(candidate)
    runner.validate_dependencies(pin["path"])
    return pin


def store_profile(store, credentials, name: str, profile: dict, token: str,
                  pin: dict | None = None, replace: bool = False,
                  expected: dict | None = None, activate: bool = True) -> None:
    reference = credentials.put(token)
    previous = None
    try:
        with store.transaction() as config:
            if expected is not None and config["profiles"].get(name, {}) != expected:
                raise CodeupError("profile_changed", "Profile changed during credential validation. Retry; existing configuration was preserved.")
            if name in config["profiles"] and not replace:
                raise CodeupError("profile_exists", "Profile exists; use setup or auth rotate to update it.")
            previous = config["profiles"].get(name, {}).get("credential_ref")
            config["profiles"][name] = {**profile, "credential_ref": reference}
            if activate:
                config["active"] = name
            if pin:
                config["executable"] = pin
    except Exception:
        credentials.delete(reference)
        raise
    if previous and previous != reference:
        credentials.delete(previous)


def setup(args, store, add: bool = False) -> int:
    config = store.read()
    proposed = args.name or args.profile
    if add and not proposed:
        proposed = input("New profile name: ").strip()
    name = validate_name(proposed or config.get("active") or "default")
    if add and name in config["profiles"]:
        raise CodeupError("profile_exists", "Profile already exists.")
    old = config["profiles"].get(name, {})
    language = select_option("Language / 语言", [("en", "English"), ("cn", "中文")])
    edition = args.edition or select_option("Edition / 版本", [("region", "Region / 区域版"), ("central", "Central / 中心版")], 1 if old.get("edition") == "central" else 0)
    pin = choose_executable(args, config)
    credentials = Credentials()
    profile = {"edition": edition}
    if edition == "region":
        url = args.base_url or input("Regional public API Base URL [" + old.get("base_url", "") + "]: ").strip() or old.get("base_url", "")
        profile["base_url"] = validate_url(url)
        org = args.organization_id or old.get("organization_id")
    else:
        org = args.organization_id or input("Organization ID [" + old.get("organization_id", "") + "]: ").strip() or old.get("organization_id")
    if org:
        profile["organization_id"] = org
    if args.default_project or old.get("default_project"):
        profile["default_project"] = args.default_project or old["default_project"]
    if args.expires_at:
        profile["expires_at"] = args.expires_at
    validate_profile(profile)
    check_expiry(profile)
    label = "云效 PAT（输入隐藏；留空保留原值）: " if language == "cn" else "Yunxiao PAT (hidden; blank keeps current): "
    token = secret_prompt(label, allow_empty=True)
    keep_token = not token
    if keep_token:
        reference = old.get("credential_ref")
        token = credentials.get(reference) if reference else None
        if not token:
            raise CodeupError("credential_missing", "No existing PAT to keep. Enter a PAT through hidden terminal input.")
        profile["credential_ref"] = reference
        if not args.expires_at and old.get("expires_at"):
            profile["expires_at"] = old["expires_at"]
        check_expiry(profile)
    runner.validate_token(pin["path"], profile, token)
    if pin_executable(pin["path"]) != pin:
        raise CodeupError("executable_changed", "CLI changed during setup; no credential saved.")
    if keep_token:
        with store.transaction() as current:
            if current["profiles"].get(name, {}) != old:
                raise CodeupError("profile_changed", "Profile changed during credential validation. Retry; existing configuration was preserved.")
            current["profiles"][name] = profile
            current["active"] = name
            current["executable"] = pin
    else:
        store_profile(store, credentials, name, profile, token, pin, replace=not add, expected=old)
    output({"profile": name, "credential": "stored securely", "validation": "read-only check passed"})
    return 0


def status(args, store) -> int:
    config = store.read()
    name, profile = selected(config, args.profile)
    result = {"profile": name, **profile, "credential": "missing"}
    result.pop("credential_ref", None)
    ready = True
    try:
        verified_executable(config)
        result["executable"] = "pinned and unchanged"
    except CodeupError as error:
        result["executable"] = error.code
        ready = False
    try:
        credentials = Credentials()
        result["credential"] = "configured" if profile.get("credential_ref") and credentials.get(profile["credential_ref"]) else "missing"
        ready = ready and result["credential"] == "configured"
        check_expiry(profile)
    except CodeupError as error:
        result["credential"] = error.code
        ready = False
    result["authentication"] = "not checked; use codeup doctor"
    output(result)
    return 0 if ready else 1


def doctor(args, store) -> int:
    config = store.read()
    name, profile = selected(config, args.profile)
    executable = verified_executable(config)
    runner.validate_dependencies(executable)
    check_expiry(profile)
    token = Credentials().get(profile["credential_ref"]) if profile.get("credential_ref") else None
    if not token:
        raise CodeupError("credential_missing", "PAT missing. Run codeup setup or codeup auth rotate.")
    runner.validate_token(executable, profile, token)
    output({"profile": name, "cli": "verified", "plugin": "available", "authentication": "read-only check passed"})
    return 0


def execute(args, store) -> int:
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if args.action == "exec":
        if command[:2] != ["aliyun", "devops"]:
            raise CodeupError("invalid_command", "Usage: codeup exec -- aliyun devops COMMAND [ARGUMENTS]. No shell or other executable accepted.")
        command = command[2:]
    config = store.read()
    help_only = policy.check(command, config.get("policy"), policy.Authorization(args.authorize_write, args.authorize_destructive, args.authorize_deployment))
    executable = verified_executable(config)
    if help_only:
        return runner.stream(executable, ["devops", *command], timeout=args.timeout)
    _, profile = selected(config, args.profile)
    check_expiry(profile)
    token = Credentials().get(profile["credential_ref"]) if profile.get("credential_ref") else None
    if not token:
        raise CodeupError("credential_missing", "PAT missing. Run codeup setup or codeup auth rotate.")
    return runner.stream(executable, ["devops", *command], profile, token, args.timeout)


def profiles(args, store) -> int:
    if args.profile_action == "add":
        return setup(args, store, add=True)
    if args.profile_action == "list":
        config = store.read()
        output({"active": config.get("active"), "profiles": config["profiles"]})
        return 0
    name = validate_name(args.name)
    with store.transaction() as config:
        if name not in config["profiles"]:
            raise CodeupError("profile_missing", "Named profile does not exist.")
        if args.profile_action == "use":
            config["active"] = name
        else:
            reference = config["profiles"][name].get("credential_ref")
            if reference:
                Credentials().delete(reference)
            config["profiles"].pop(name)
            if config["active"] == name:
                config["active"] = next(iter(config["profiles"]), None)
    output({"profile": name, "action": args.profile_action})
    return 0


def auth(args, store) -> int:
    if args.auth_action == "status":
        return status(args, store)
    config = store.read()
    name, profile = selected(config, args.profile)
    credentials = Credentials()
    if args.auth_action == "revoke":
        with store.transaction() as current:
            current_name, current_profile = selected(current, name)
            reference = current_profile.get("credential_ref")
            if reference:
                credentials.delete(reference)
            current_profile.pop("credential_ref", None)
            current["profiles"][current_name] = current_profile
        output({"profile": name, "credential": "removed locally; revoke PAT in Yunxiao console too"})
        return 0
    expected = dict(profile)
    token = secret_prompt()
    profile.pop("credential_ref", None)
    profile.pop("expires_at", None)
    if args.expires_at:
        profile["expires_at"] = args.expires_at
    check_expiry(profile)
    executable = verified_executable(config)
    runner.validate_token(executable, profile, token)
    if pin_executable(executable) != config["executable"]:
        raise CodeupError("executable_changed", "CLI changed during validation; no credential saved.")
    store_profile(store, credentials, name, profile, token, replace=True, expected=expected, activate=False)
    output({"profile": name, "credential": "rotated securely; revoke old PAT in Yunxiao console"})
    return 0


def configure(args, store) -> int:
    if args.config_action == "show":
        output(store.read())
        return 0
    if args.config_action == "reset":
        with store.transaction() as config:
            if config["profiles"]:
                raise CodeupError("profiles_exist", "Remove profiles first with codeup profile remove NAME, which deletes their stored credentials.")
            config.clear()
            config.update({"version": 2, "active": None, "profiles": {}})
        return 0
    pin = pin_executable(args.cli_path) if args.cli_path else None
    if pin:
        runner.validate_dependencies(pin["path"])
    with store.transaction() as config:
        if pin:
            config["executable"] = pin
        fields = ("edition", "base_url", "organization_id", "default_project")
        if any(getattr(args, field) is not None for field in fields):
            name, profile = selected(config, args.profile)
            for field in fields:
                value = getattr(args, field)
                if value is not None:
                    if value:
                        profile[field] = validate_url(value) if field == "base_url" else value
                    else:
                        profile.pop(field, None)
            if profile["edition"] == "central":
                profile.pop("base_url", None)
            validate_profile(profile)
            config["profiles"][name] = profile
    output({"configuration": "updated"})
    return 0


def set_policy(args, store) -> int:
    if args.policy_action == "show":
        output(store.read().get("policy", {}))
        return 0
    with store.transaction() as config:
        rules = {}
        if args.allow is not None:
            rules["allow"] = args.allow
        if args.deny is not None:
            rules["deny"] = args.deny
        config["policy"] = rules
    output({"policy": rules})
    return 0


def package_action(action: str, store) -> int:
    try:
        importlib.metadata.distribution("aliyun-codeup-cli")
    except importlib.metadata.PackageNotFoundError:
        raise CodeupError("package_not_installed", "Run from installed package or use pipx/pip directly.") from None
    if action == "uninstall":
        if not sys.stdin.isatty() or input("Uninstall codeup and remove all saved profiles/credentials? [y/N]: ").strip().lower() not in ("y", "yes"):
            raise CodeupError("uninstall_cancelled", "Uninstall requires interactive confirmation.")
        with store.transaction() as current:
            credentials = Credentials() if current["profiles"] else None
            for profile in current["profiles"].values():
                if profile.get("credential_ref"):
                    credentials.delete(profile["credential_ref"])
            current.clear()
            current.update({"version": 2, "active": None, "profiles": {}})
    prefix = str(Path(sys.prefix)).replace("\\", "/").lower()
    if "/pipx/venvs/" in prefix:
        pipx = shutil.which("pipx")
        if not pipx:
            raise CodeupError("package_manager_missing", "Use pipx to upgrade/uninstall this installation.")
        command = [pipx, "install", "--force", "git+https://github.com/Lilb1tty/aliyun-codeup-skill.git"] if action == "upgrade" else [pipx, "uninstall", "aliyun-codeup-cli"]
    else:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", "git+https://github.com/Lilb1tty/aliyun-codeup-skill.git"] if action == "upgrade" else [sys.executable, "-m", "pip", "uninstall", "--yes", "aliyun-codeup-cli"]
    return subprocess.run(command, env=runner.environment(), check=False).returncode


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default errors repeat rejected values, including pasted PATs.
        self.print_usage(sys.stderr)
        self.exit(2, '{"error":"invalid_usage","message":"Invalid arguments. Use codeup --help; credentials are accepted only through hidden terminal input."}\n')


def parser() -> argparse.ArgumentParser:
    result = SafeParser(prog="codeup", allow_abbrev=False, description="Secure native credentials and official Yunxiao CLI execution")
    result.add_argument("--version", action="version", version=__version__)
    result.add_argument("--profile", help="Per-call profile; otherwise use active profile")
    result.add_argument("--authorize-write", action="store_true")
    result.add_argument("--authorize-destructive", action="store_true")
    result.add_argument("--authorize-deployment", action="store_true")
    result.add_argument("--timeout", type=float, default=300, help="Seconds (default 300, max 86400)")
    sub = result.add_subparsers(dest="action", required=True)

    def setup_options(target):
        target.add_argument("--name")
        target.add_argument("--edition", choices=("region", "central"))
        for name in ("base-url", "organization-id", "default-project", "cli-path", "expires-at"):
            target.add_argument("--" + name)

    setup_options(sub.add_parser("setup", help="Hidden PAT entry and read-only validation"))
    for name in ("status", "doctor", "upgrade", "uninstall"):
        sub.add_parser(name)
    for name in ("exec", "devops"):
        delegated = sub.add_parser(name, add_help=False, help="Delegate official devops arguments verbatim")
        delegated.add_argument("command", nargs=argparse.REMAINDER)
    profile = sub.add_parser("profile").add_subparsers(dest="profile_action", required=True)
    profile.add_parser("list")
    setup_options(profile.add_parser("add"))
    for name in ("use", "remove"):
        profile.add_parser(name).add_argument("name")
    auth_sub = sub.add_parser("auth").add_subparsers(dest="auth_action", required=True)
    for name in ("status", "revoke"):
        auth_sub.add_parser(name)
    for name in ("set", "rotate"):
        auth_sub.add_parser(name).add_argument("--expires-at")
    configuration = sub.add_parser("config").add_subparsers(dest="config_action", required=True)
    configuration.add_parser("show")
    configuration.add_parser("reset")
    settings = configuration.add_parser("set")
    for name in ("base-url", "organization-id", "default-project", "cli-path"):
        settings.add_argument("--" + name)
    settings.add_argument("--edition", choices=("region", "central"))
    rules = sub.add_parser("policy").add_subparsers(dest="policy_action", required=True)
    rules.add_parser("show")
    rules_set = rules.add_parser("set")
    rules_set.add_argument("--allow", nargs="*")
    rules_set.add_argument("--deny", nargs="*")
    adapter = sub.add_parser("integrate", help="Install project-local Skill adapter")
    adapter.add_argument("--agent", choices=("codex", "claude"), required=True)
    adapter.add_argument("--project", type=Path, default=Path.cwd())
    adapter.add_argument("--official-skill", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        raw = list(sys.argv[1:] if argv is None else argv)
        index = 0
        while index < len(raw):
            if raw[index] in ("--profile", "--timeout"):
                index += 2
            elif raw[index].startswith("-"):
                index += 1
            else:
                break
        if index < len(raw) and raw[index] in ("exec", "devops"):
            args = parser().parse_args(raw[:index + 1])
            args.command = raw[index + 1:]
        else:
            args = parser().parse_args(raw)
        if not math.isfinite(args.timeout) or not 0 < args.timeout <= 86400:
            raise CodeupError("invalid_timeout", "Timeout must be greater than zero and at most 86400 seconds.")
        store = ConfigStore()
        actions = {"setup": setup, "status": status, "doctor": doctor,
                   "profile": profiles, "auth": auth, "config": configure,
                   "policy": set_policy, "exec": execute, "devops": execute}
        if args.action in actions:
            return actions[args.action](args, store)
        if args.action == "integrate":
            output(integration.install(args.agent, args.project, args.official_skill))
            return 0
        return package_action(args.action, store)
    except CodeupError as error:
        print(json.dumps({"error": error.code, "message": str(error)}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except EOFError:
        print('{"error":"input_required","message":"Run interactive setup in a terminal."}', file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print('{"error":"local_failure","message":"Local operation failed; sensitive diagnostics suppressed."}', file=sys.stderr)
        return 2
