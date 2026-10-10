# Security boundary and threat model

Assets: PATs, authenticated operation targets, profile isolation and command output.
Trusted components: OS/user account, Python installation, keyring native backend,
explicitly selected Alibaba CLI, its installed plugin/configuration, verified
upstream Skill source, and the user's authorization decisions.

## Enforced protections

- PATs stored only by native OS vault backends; no plaintext, environment persistence,
  argv, HTTP client, implicit dependency installation or fallback credential backend.
- Per-profile random references; transaction locks, unique temporary files, fsync,
  atomic metadata replacement. Secret fields and corrupt configuration rejected.
- Hidden terminal entry fails on getpass's echoed-input fallback. New PAT validated
  before storage. Recorded expiry checked locally. Old reference deleted after commit.
- Credential-free exact help; policy checked before vault access. Read-only default,
  deny/allow patterns, explicit write/destructive/deployment flags. Unknown commands
  require authorization; command classification is conservative, not an API schema.
- Native absolute executable path and SHA-256 checked on each invocation. POSIX file
  and parent directory write permissions and root/current-user ownership checked. Windows uses per-user installation
  and OS access controls; it does not audit every ACL or verify Authenticode identity.
  A hash confirms continuity of a user-approved binary, not vendor provenance.
- No shell evaluation. Only `aliyun devops` allowed; no arbitrary programs, URL or
  token flags. Debug, log-level, dry-run and request-inspection options blocked.
- Inherited Alibaba/Yunxiao selectors and common debug/loader variables scrubbed.
  Only selected profile credentials are injected into a fresh child environment.
- Byte-stream exact PAT redaction, bounded suffix retention, fixed diagnostics,
  validation output discarded, finite timeout, cancellation and no automatic retries.

## Limits: same-user agents are trusted principals

Environment injection **does not isolate PATs from an agent with arbitrary shell
access under the same OS user**. Such an agent can call native keyring APIs itself,
inspect accessible process memory/environments, change metadata or source, replace
same-user plugins, invoke the official CLI directly, or supply authorization flags.
These flags enforce a required explicit signal; they do not cryptographically prove
a human approved an action. Instruction adapters can be ignored by an agent.

Protecting PATs from an untrusted agent requires a different OS identity plus a
privileged broker or sandbox restricting vault/process access and executables. This
project deliberately has no such service and makes no isolation claim. PAT scopes,
short lifetimes and Yunxiao-side permissions remain essential.

Executable hashing has a check/use race against a same-user malicious replacement.
The plugin is trusted as part of the official CLI installation and is not separately
pinned. POSIX checks reject installations below writable shared directories, even
when a sticky directory might be safe. Windows relies on installation ACLs.

Profiles accept only the exact central hostname and documented single-label
`INSTANCE.devops.aliyuncs.com` regional hostnames. Other Alibaba namespaces contain
tenant-controlled services and are rejected. Hostname checking alone cannot
establish the intended organization; verify the instance during setup. Proxy, TLS trust and
DNS behavior remain the official CLI/OS responsibility. Operation payloads and
resource-level authorization are passed to the official CLI unchanged.

Redaction masks the exact raw PAT on stdout/stderr. It cannot reliably recognize
encoded, transformed, fragmented-with-extra-content secrets, vault aliases, or
unrelated secrets returned by an API. Avoid enabling diagnostics outside this
wrapper. Normal unrelated JSON fields/bytes are intentionally preserved.

Signal forwarding on POSIX covers the process group. Windows starts the official
CLI suspended, assigns it to a Job Object, then resumes its primary thread so plugin
descendants inherit the job. Closing/terminating the job kills its process tree.
Timeout/cancellation may leave a remote write's result unknown. Inspect state
through a read before deciding whether to retry.

## Operational handling

If rotation commits new metadata but native cleanup fails, the fixed error names
the non-secret previous reference for OS vault cleanup. Do not export it. Removal
and local revocation delete credentials under the mutation lock before metadata
removal, preserving the reference when vault deletion fails. If deletion succeeds
but metadata save fails, repeating the operation safely handles the missing entry.
Rotation/removal concurrent with an invocation may make an older reference missing;
retry the read operation after the mutation completes. Credentials cannot cross
profiles. Credential vault locking, token revocation and expiration are surfaced
without replaying backend exceptions.

Never publish debug dumps, environment dumps or vault exports. Revoke suspected
leaks in Yunxiao. Local `auth revoke` is not server-side PAT revocation. Validate
CLI/plugin upgrades from official sources, then explicitly repin the CLI executable.
