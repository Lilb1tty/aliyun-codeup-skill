# Official functionality research (2026-10-10)

Inspected local source checkouts (not bundled in distribution):

- [Official Skills](https://github.com/aliyun/alibabacloud-aiops-skills), revision
  `a6e9df9e2cda67684a6af1f512288b4f9272ccea`,
  `skills/developertools/rdc/alibabacloud-devops/`. Skill owns intent classification,
  ambiguity resolution, product mapping, command discovery, pagination and result
  verification. Its scripts call `aliyun devops`; it prefers CLI before MCP fallback.
  Authentication instructions expect environment variables. Its workflow is reused,
  while adapter instructions replace secret setup and command execution.
- [Official MCP](https://github.com/aliyun/alibabacloud-devops-mcp-server), revision
  `0b3734940c57273235de939bd7103b0869566f56`. `index.ts` accepts transport/session
  authentication and `YUNXIAO_ACCESS_TOKEN`; `common/utils.ts` retrieves request-local
  token via AsyncLocalStorage. Tool catalogs and toolset selection already exist.
  A second MCP server or API client would duplicate official functionality.
- [CLI guide](https://www.alibabacloud.com/help/en/yunxiao/developer-reference/how-to-install-initialize-and-use-the-apsara-devops-cli):
  official plugin provides operation discovery, pagination, JMESPath, JSON output,
  PAT environment authentication, and endpoint selectors. This wrapper adds only
  secure credential lifecycle, profiles, pinning, and executable policy.
- [PAT guide](https://www.alibabacloud.com/help/en/yunxiao/developer-reference/obtain-personal-access-token):
  least privilege, finite expiry, rotation, revoke leaked tokens. Never use PAT flags.

Installed CLI inspected without credentials: Alibaba CLI 3.5.1, DevOps plugin 0.9.1,
API version 2026-05-25. Help confirms `base-get-user-by-token --quiet` as a read-only
validation operation. Global flags include `--cli-dry-run`, `--log-level`,
`--endpoint`, `--api-base-url`, `--region`, and `--yunxiao-access-token`.
Request inspection/debug modes and endpoint selectors therefore need explicit
blocking before credential injection. The launcher does not reimplement pagination.

Integration references: [Codex Skills](https://developers.openai.com/codex/skills/)
and [Claude Code Skills](https://code.claude.com/docs/en/skills).
Use project `.agents/skills/` and `.claude/skills/` directories respectively;
do not patch installed upstream packages or the Alibaba CLI binary.
