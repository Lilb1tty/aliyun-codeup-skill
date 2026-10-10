"""Authorization is executable policy, independent of agent instructions."""

from dataclasses import dataclass
from fnmatch import fnmatchcase
import re
from .errors import CodeupError
from .read_commands import READ_COMMANDS

COMMAND = re.compile(r"(?:base|codeup|flow|projex|app-stack|test-hub|packages|insight|lingma)-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
DESTRUCTIVE = re.compile(r"(?:^|-)(?:delete|remove|revoke|destroy|reset|clear|drop|cancel|stop|terminate|purge)(?:-|$)")
DEPLOYMENT = re.compile(r"(?:^|-)(?:deploy|deployment|release|execute|run|start|trigger|publish)(?:-|$)")
BLOCKED = {"--yunxiao-access-token", "--access-token", "--token", "--authorization",
           "--api-base-url", "--endpoint", "--region", "--organization-id",
           "--cli-dry-run", "--cli-ai-mode", "--debug", "--verbose", "--log-level",
           "--profile", "--config-path", "--config-file"}


@dataclass(frozen=True)
class Authorization:
    write: bool = False
    destructive: bool = False
    deployment: bool = False


def check(args: list[str], policy: dict | None = None,
          authorization: Authorization = Authorization()) -> bool:
    """Validate devops arguments; return True only for exact, credential-free help."""
    if not args:
        raise CodeupError("invalid_command", "Expected an official aliyun devops command or --help.")
    for arg in args:
        if not isinstance(arg, str) or "\x00" in arg:
            raise CodeupError("invalid_arguments", "CLI arguments must be strings without NUL bytes.")
        flag = arg.split("=", 1)[0].lower()
        if flag in BLOCKED or (flag.startswith("--") and any(word in flag for word in ("token", "credential", "password", "secret", "debug", "endpoint"))):
            raise CodeupError("unsafe_flag", "Credential, endpoint, profile and diagnostic overrides are refused; use codeup setup/config instead.")
    if args in (["--help"], ["-h"], ["version"]):
        return True
    command = args[0]
    if not COMMAND.fullmatch(command):
        raise CodeupError("invalid_command", "Only the official aliyun devops operation family is supported.")
    if args[1:] in (["--help"], ["-h"]):
        return True
    # False-valued and combined help flags must not bypass authorization.
    if any(arg.split("=", 1)[0] in ("--help", "-h") for arg in args[1:]):
        raise CodeupError("invalid_help", "Use COMMAND --help alone for credential-free help.")
    rules = policy or {}
    if any(fnmatchcase(command, pattern) for pattern in rules.get("deny", [])):
        raise CodeupError("policy_denied", "Operation denied by configured policy.")
    if "allow" in rules and not any(fnmatchcase(command, pattern) for pattern in rules["allow"]):
        raise CodeupError("policy_denied", "Operation is outside the configured allowlist.")
    if command in READ_COMMANDS:
        return False
    if not authorization.write:
        raise CodeupError("write_authorization_required", "Write or unknown operation requires --authorize-write after explicit user authorization.")
    if DESTRUCTIVE.search(command) and not authorization.destructive:
        raise CodeupError("destructive_authorization_required", "Destructive operation also requires --authorize-destructive.")
    if (command.startswith(("flow-", "app-stack-")) or DEPLOYMENT.search(command)) and not authorization.deployment:
        raise CodeupError("deployment_authorization_required", "Deployment-capable operation also requires --authorize-deployment.")
    return False
