# codeup design and execution plan

Purpose: keep PATs in native credential storage, delegate API work to the official
CLI, and let Claude Code/Codex use the upstream Skill through a small adapter.
The pasted specification authorizes autonomous decisions and implementation.

Python 3.10+, standard library plus keyring. Separate configuration, native
credentials, policy, execution, integration, and command handling. No service,
HTTP client, CLI fork, or executable interception. Retain `devops`, `config`,
`auth`, `upgrade`, and `uninstall` aliases from the existing workspace CLI.

Configuration uses atomic replacement and cross-process mutation locking. Each
profile has an independent credential reference. Rotation writes a fresh reference
before switching metadata. Setup validates through `base-get-user-by-token` before
persisting a PAT. Missing keyring backends fail closed.

Setup pins an explicitly selected/resolved native executable's absolute path and
SHA-256. Normal execution never resolves PATH. Reject credential/endpoint/debug
overrides; scrub inherited Yunxiao and debug variables. Child output uses bounded
byte-stream redaction. Signals and finite timeouts terminate the child; no retries.

Policy defaults to known read commands. Unknown operations require explicit write
authorization; destructive operations require additional authorization. All Flow
and AppStack writes require deployment authorization because pipeline effects
cannot be determined locally. Denylists override allowlists and authorizations.

Adapters install in documented project Skill locations, reference an unchanged
upstream Skill copy, and replace CLI invocation instructions only. This is a Skill
adapter, not transparent shell interception or isolation from same-user agents.

## Execution checklist

- [x] Document official capabilities and pinned source revisions.
- [x] Implement configuration, native credentials, profiles, setup, rotation.
- [x] Implement executable validation, policy, streaming, timeout and signals.
- [x] Install minimal project adapters and document security boundary.
- [x] Run unit/integration tests, real credential-free CLI smoke tests, build checks.
- [x] Obtain fresh-context security review, fix findings, record validation limits.

## Implementation rulings

- Explicitly documented read-operation catalog replaces prefix classification so
  future unknown operations cannot bypass write authorization.
- Restrict endpoints to exact central service or documented single-label regional
  `INSTANCE.devops.aliyuncs.com`; broad provider namespaces can contain tenant services.
- Windows Job Objects attach suspended children before execution. Validation probes
  reuse the same streaming process-tree lifecycle; Job handle cleanup is serialized.
- Preserve only actual PAT prefixes in redaction buffers so non-secret prompts pass
  immediately. Console callable propagates terminating POSIX signals, including SIGKILL.
- Profile mutations use optimistic checks after validation; rotation doesn't switch
  active profile. Vault deletion failures preserve removal/revocation metadata.
- Installation offers official instructions; no unsigned automatic binary downloads.
- CLI/API/agent behavior is not claimed validated beyond the recorded evidence in
  docs/validation.md. Live verification uses read-only operations and the secure
  launcher; no PAT values exposed or live mutations performed.

No live writes in tests. Mock credential stores and subprocesses; use a fake native
CLI entry through the Python executable for subprocess integration. Real platform
and authenticated agent tests require explicitly configured disposable profiles.
