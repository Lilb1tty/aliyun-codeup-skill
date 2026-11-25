---
name: aliyun-devops
description: Manage Yunxiao projects, work items, repositories, merge requests, pipelines and artifacts through the official Alibaba Cloud DevOps Skill with codeup secure profile authentication. Also writes the body of any Yunxiao work item before filing - bug, defect, issue, story, feature, requirement (需求/工单/工作项/缺陷). Use whenever the user asks to create, file, write, draft or log one, or asks "what should I file?".
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

1. Use `codeup status` for authentication presence. If `codeup` is not found, ask the
   user to install it with
   `pipx install git+https://github.com/Lilb1tty/aliyun-codeup-skill.git`.
   Missing setup requires the user to run `codeup setup` in their terminal. PAT entry
   uses hidden terminal input.
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
5. For every Project work item you create, set the iteration to the project's open
   iteration, unless the user names another one. Find the open iteration with
   `projex-list-sprints --id <projectId>`, picking the sprint whose status is `DOING`
   (the `--status DOING` filter can return an empty list), and pass its ID as `--sprint`
   on `projex-create-workitem`. The lookup is read-only and needs no authorization flag.
   Show the iteration when you know it, and check it on read-back. If zero or several
   iterations are `DOING`, ask the user which to use. Do not create or change an
   iteration to satisfy this rule.
6. Before creating a work item, write its body from
   [references/workitem-body.md](references/workitem-body.md): pick bug or story,
   ask for missing details, fill every placeholder, show the body as a fenced
   block, then confirm the create (rule 4). Body format is MARKDOWN, Chinese only.

Never request PATs in chat, inspect vault contents, export credentials or place
them in command arguments. Profiles, endpoints and executable trust are configured
through codeup's terminal commands. This adapter does not intercept arbitrary shells
or isolate credentials from same-user agents with unrestricted shell access.
