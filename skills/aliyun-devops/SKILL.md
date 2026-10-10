---
name: aliyun-devops
description: Manage Yunxiao projects, work items, repositories, merge requests, pipelines and artifacts through the official Alibaba Cloud DevOps Skill with codeup secure profile authentication.
---

# Secure Yunxiao execution adapter

Use the official `alibabacloud-devops` Skill for intent classification, product
mapping, command discovery, operation arguments, pagination and result verification.
Read its relevant product references before selecting an operation.

Locate the installed official Skill. If absent, obtain the verified source at
[Alibaba Cloud Skills](https://github.com/aliyun/alibabacloud-aiops-skills/tree/master/skills/developertools/rdc/alibabacloud-devops)
and install a project adapter with `codeup integrate --agent codex|claude
--official-skill PATH_TO_OFFICIAL_SKILL`. The installer places unchanged upstream
references alongside its adapter in the documented agent Skill directory. Treat
upstream files as workflow references; these authentication/execution instructions
take precedence for this integration.

1. Use `codeup status` for authentication presence. Missing setup requires the user
   to run `codeup setup` in their terminal. PAT entry uses hidden terminal input.
2. Replace every upstream `aliyun devops <arguments>` invocation with
   `codeup exec -- aliyun devops <arguments>`, including help/discovery. Active
   profile resolves automatically; users make ordinary natural-language requests.
3. Read upstream scripts as reference and execute their discovered commands through
   codeup. Do not run raw-CLI scripts, environment token checks, MCP/mcporter or HTTP
   fallbacks that bypass the launcher.
4. For writes, show the concrete target/effect and obtain explicit user authorization.
   Add `--authorize-write` before `exec` only for the approved action. Destructive
   operations additionally need `--authorize-destructive`; deployments and all
   Flow/AppStack writes need `--authorize-deployment`. Report policy denials.

Never request PATs in chat, inspect vault contents, export credentials or place
them in command arguments. Profiles, endpoints and executable trust are configured
through codeup's terminal commands. This adapter does not intercept arbitrary shells
or isolate credentials from same-user agents with unrestricted shell access.
