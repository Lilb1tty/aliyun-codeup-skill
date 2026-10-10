# codeup

[English](README.md) | [简体中文](README.zh-CN.md)

Secure, cross-platform launcher for official `aliyun devops` operations. Python
3.10+; one runtime dependency, `keyring`. No API client, server or CLI fork.

## Install and configure

```sh
pipx install .
# Or: python -m pip install .
codeup setup
codeup status
codeup doctor
```

Install [Alibaba CLI](https://www.alibabacloud.com/help/en/cli/) and its official
plugin if absent: `aliyun plugin install --names aliyun-cli-devops`. Setup checks
both and gives installation instructions; it does not download unsigned binaries
or run remote installation scripts. Choose English/Chinese, an edition and profile.
The wizard prompts for endpoint/organization, reads PAT through hidden terminal
input, validates it with `base-get-user-by-token --quiet`, then stores it in the
native credential vault. Validation errors suppress response content.
During reconfiguration, blank organization ID/PAT input keeps existing values;
keeping the PAT preserves its credential reference and recorded expiry. Blank CLI
trust confirmation means yes (`[Y/n]`); entering `n` rejects the discovered path.

Region edition requires the instance's **public API hostname**. Central edition
uses the official default endpoint and requires an organization ID. Accepted
URLs use documented Yunxiao hosts (`openapi-rdc.aliyuncs.com` or
`INSTANCE.devops.aliyuncs.com`) without credentials, query, path, fragment or custom ports.
Verify your instance hostname before trusting it.

```sh
codeup setup --name work --edition central --organization-id ORG_ID --cli-path /absolute/path/to/aliyun
codeup setup --name regional --edition region --base-url https://INSTANCE.devops.aliyuncs.com --expires-at 2026-12-01T00:00:00Z
```

Windows example for executable selection: `--cli-path C:\Tools\aliyun.exe`.
Provide flags before the subcommand when they select a profile, authorization or
timeout. Setup never accepts a PAT flag, stdin pipe or permanent environment setup.

The CLI executable is explicitly trusted at setup and pinned by path and SHA-256.
After upgrading the official CLI, verify the installation and run
`codeup config set --cli-path ABSOLUTE_PATH` to repin. Only native executables are
accepted; normal operation never resolves PATH or automatically installs tools.

## Profiles and credentials

```sh
codeup profile list
codeup profile add --name personal
codeup profile use work
codeup --profile personal status
codeup --profile personal doctor
codeup --profile work auth rotate --expires-at 2026-12-01T00:00:00Z
codeup profile remove personal
```

Each profile has its own native credential reference, edition, API base URL,
optional organization ID, optional default project, and optional recorded expiry.
Active profile selection applies automatically to agent calls. `--profile` chooses
a profile for one call. Default project is metadata available to the Skill; the
launcher never invents official command flags from it. Listing/status never prints
PATs. `status` checks local readiness; `doctor` performs a real read-only PAT check.

Windows Credential Manager, macOS Keychain and Linux Secret Service are supported.
Missing, locked or unsupported vaults fail closed. Linux needs a running Secret
Service/session (usually `gnome-keyring` or another compatible provider). Headless
machines without it require an externally provisioned secure service; this tool
has no plaintext fallback. Non-secret metadata lives under user APPDATA on Windows,
Application Support on macOS, or XDG_CONFIG_HOME on Linux, in `aliyun-cli-devops`.

Rotation validates a new PAT, writes a new reference, commits metadata atomically,
then removes the old reference. Revoke old tokens in the Yunxiao console yourself.
`auth revoke` deletes the local stored credential only. Recorded expiry blocks
expired tokens locally; server-side expiry/revocation is detected by `doctor` or
the official CLI. Rotating without `--expires-at` clears previous recorded expiry.
Legacy single-profile settings migrate into `default`; executable pinning is
required before first use. `config reset` requires removing profiles first.

## Official CLI execution

```sh
codeup exec -- aliyun devops --help
codeup exec -- aliyun devops codeup-list-repositories --page 1 --per-page 20
codeup devops codeup-list-repositories --cli-query 'result[]' --all-pages
codeup --profile work --timeout 60 exec -- aliyun devops projex-search-projects
```

`devops` is a compatibility alias. Arguments go directly to the pinned native
executable without a shell. Stdin, stdout/stderr bytes, JSON, query flags,
pagination and ordinary exit codes pass through; exact PAT bytes are redacted
even across stream boundaries. Streaming holds at most one PAT-sized tail, so
only a suffix matching a PAT prefix can be delayed until more bytes arrive or the
process exits. Other bytes, including prompts, pass immediately. Timeout defaults to 300 seconds, maximum 86400. Cancellation forwards
signals, then kills an unresponsive process. No automatic operation retries.

Only official DevOps operations are allowed. Default policy permits known module
read commands explicitly documented in the official Skill/CLI guide, recorded in
`codeup_secure/read_commands.py`. Other/unknown
operations require write authorization. Destructive verbs require an additional
flag. All Flow/AppStack writes and deployment-capable verbs need deployment
authorization because pipeline production effects cannot be inferred locally.

```sh
# Run only after explicitly authorizing the target/effect:
codeup --authorize-write exec -- aliyun devops projex-create-workitem [OFFICIAL_FLAGS]
codeup --authorize-write --authorize-destructive exec -- aliyun devops codeup-delete-repository [OFFICIAL_FLAGS]
codeup --authorize-write --authorize-deployment exec -- aliyun devops flow-create-pipeline-run [OFFICIAL_FLAGS]
codeup policy set --allow 'codeup-*' 'projex-search-*' --deny 'codeup-delete-*'
codeup policy show
codeup policy set  # clear custom patterns; default authorization still applies
```

Denylists win; allowlists never grant write authorization. An empty allowlist
denies all operations. Exact `COMMAND --help` is credential-free discovery.
Credential flags, endpoint/organization overrides, debug/log-level, AI/request
inspection modes and dry-run are refused. Configure selectors through profiles.
Diagnostics use fixed JSON error codes without raw subprocess/keyring exceptions.

## Claude Code and Codex

Use the official [Alibaba Cloud DevOps Skill](https://github.com/aliyun/alibabacloud-aiops-skills/tree/master/skills/developertools/rdc/alibabacloud-devops).
Obtain/verify that repository, then install a **project-local adapter**:

```sh
codeup integrate --agent codex --project /path/to/project --official-skill /path/to/alibabacloud-aiops-skills/skills/developertools/rdc/alibabacloud-devops
codeup integrate --agent claude --project /path/to/project --official-skill /path/to/alibabacloud-aiops-skills/skills/developertools/rdc/alibabacloud-devops
```

The installer writes `.agents/skills/aliyun-devops/` (Codex) or
`.claude/skills/aliyun-devops/` (Claude), copying official files unchanged under
`references/official` and recording the upstream Skill hash. It refuses to
overwrite existing adapters. Review/remove the old adapter explicitly to update.
Restart/reload the agent as required by its Skill discovery mechanism.

Natural-language examples: “List my Yunxiao projects”, “Show unresolved work items
assigned to me”, “Create an issue for the current sprint.” The adapter delegates
discovery/workflows to the official Skill and instructs it to invoke codeup
automatically. Users do not enter `codeup exec` for every request. Upstream token
environment checks and direct scripts/MCP fallbacks are replaced by codeup checks
and execution. Globally installed third-party files and the official binary are
not modified. The repository plugin Skill provides equivalent routing instructions
for environments where the official Skill is already available.

This is **instruction-based Skill integration**, not transparent executable
interception. Automated tests verify adapter installation and subprocess dispatch;
real natural-language agent behavior needs the end-to-end acceptance run below.

## Validation and documentation

```sh
python -m unittest discover -s tests -v
python -m pip wheel --no-deps --no-build-isolation . -w dist
```

Tests mock credentials and external dependencies; simulated child processes check
arguments, streaming, redaction, stdin, exits, timeout and concurrent profiles.
No live write tests. See [research](docs/research.md), [threat model](docs/security.md),
[end-to-end checks](docs/validation.md), and [design/plan](docs/design.md).

Compatibility commands: `config show/set/reset`, `auth status/set/rotate/revoke`,
`upgrade` (GitHub source), `uninstall` (interactive confirmation). Uninstall removes
codeup profiles/credentials, leaves shared Alibaba CLI/plugin and project adapters.
