# Validation and release acceptance

## Recorded local evidence (2026-10-10)

- Windows / Python 3.14.6: 62 automated unit and subprocess integration tests,
  57 passed; 5 POSIX-only tests skipped. Includes tree termination for execution and
  token-validation probes, concurrent Job cleanup, rotation rollback, vault deletion
  failure recovery, mock native-store refusal, secret-safe errors and stream prefixes.
- Alibaba CLI 3.5.1 executable SHA-256:
  `d2a3ab7608ee8371cbd79ecc56c762978caba79109c4444c5a095ddf1877f82b`.
  Matched the executable inside the official release archive. Archive checksum
  `e35c0f66727df399c996646a4c33f64cd5b69f66eee3e33e1c4f51d41c603997`
  matched [published release checksums](https://github.com/aliyun/aliyun-cli/releases/tag/v3.5.1).
- Official DevOps plugin 0.9.1: wrapper stdout, stderr and exit status matched raw
  CLI byte-for-byte for root help, repository-list help, token-user help and version.
  Environment cleared of inherited credentials; no PAT or API operation used.
- Actual official Skill source installed into isolated Claude/Codex adapter projects;
  upstream files unchanged. Simulated CLI tests exercised stdin, args, selected
  organization, output redaction, policy and nonzero exit through adapter dispatch.
- Wheel built and installed into a fresh temporary target; required modules and
  console version verified. Research/test artifacts excluded from wheel.
- Fresh-context security review findings corrected; final reviewer found no remaining
  actionable findings.
- Setup input regressions: blank organization ID/PAT preserves existing values,
  native credential reference and expiry; blank CLI trust confirmation accepts the
  path, explicit `n` rejects it.
- Live Windows verification: the installed `codeup` retrieved its configured native
  credential and successfully read project and work-item lists through the official
  CLI. A natural-language request in this Codex session reached those reads without
  the user entering wrapper syntax. No PAT values exposed or live mutations performed.

Live setup/rotation, fresh-session natural-language Claude/Codex adapter discovery,
and macOS/Linux execution are **not locally verified**. Matrix CI and the checks
below cover those remaining release-validation tasks. This evidence does not claim
transparent shell interception or isolation from unrestricted same-user agents.

Run unit/subprocess integration tests with `python -m unittest discover -s tests -v`.
They use fake PATs, a memory vault and fake CLI fixtures; no live credentials or API
writes. POSIX-only mode/signal tests skip on Windows. Run on Windows, macOS and Linux
in CI before release. Native vault behavior requires a separate session on each OS.

Build a wheel: `python -m pip wheel --no-deps --no-build-isolation . -w dist`.
Install it in a fresh virtual environment, run `codeup --version`, `codeup --help`,
and `codeup profile list`; inspect wheel contents for all codeup_secure modules.

## Real, read-only setup acceptance

In your own terminal, create a finite-lived, least-privileged disposable PAT. Never
send it to chat or put it in CLI arguments. Run:

1. `codeup setup --name acceptance --cli-path ABSOLUTE_OFFICIAL_CLI_PATH`.
2. `codeup status` and `codeup doctor`; confirm read-only authentication passes.
3. `codeup exec -- aliyun devops codeup-list-repositories --page 1 --per-page 1`.
4. Repeat with a second disposable profile, switch active profiles, and verify the
   correct organizations and endpoint selectors are used.
5. Rotate the PAT through `auth rotate`, record its expiry, verify old native entry
   is removed, and revoke the old PAT in Yunxiao.
6. Confirm invalid/expired PAT setup fails without committing new credentials.
7. Attempt a destructive command without authorization flags; it must be blocked
   locally before an API request. Do not supply approval flags during this check.
8. Inspect only non-secret metadata/output for accidentally stored token fields;
   do not inspect or export real vault values.

## Natural-language agent acceptance

Install each adapter with `codeup integrate`, using a verified official Skill source.
Start a fresh Claude Code/Codex session in the project. Ensure codeup is on that
agent's PATH and the adapter is discovered. Avoid enabling a competing raw DevOps
Skill with higher-precedence instructions in that session.

- Ask “List my Yunxiao projects.” Confirm the tool call uses
  `codeup exec -- aliyun devops projex-search-projects ...`, active profile is selected,
  and the agent returns results without asking for environment variables or PATs.
- Ask “Show unresolved work items assigned to me.” Confirm official help/references
  determine actual flags, lookup and pagination, all operations routed through codeup.
- Ask to create an issue. Confirm the agent requests explicit approval after showing
  a concrete target/effect. Decline; no write should execute.
- Ask for an unauthorized deletion/deployment. Confirm executable policy rejects it.
  Do not approve live write operations as part of ordinary acceptance.

Automated adapter/subprocess tests verify generated instructions and actual launcher
dispatch. They do not prove an independent LLM follows the Skill. Natural-language
acceptance, live PAT validation and macOS/Linux native-vault runs are separate checks;
record them honestly before declaring a production deployment validated.
