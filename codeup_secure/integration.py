"""Project-local adapters; upstream Skill files are copied unchanged."""

import hashlib
from pathlib import Path
import shutil
import tempfile
from .errors import CodeupError

ADAPTER = """---
name: aliyun-devops
description: Manage Yunxiao projects, work items, repositories, merge requests, pipelines and artifacts using the official Alibaba Cloud DevOps Skill with secure codeup authentication.
---

# Secure Yunxiao execution

Read [the official Skill](references/official/SKILL.md) for intent classification,
product references, operation discovery, arguments, pagination and verification.
Follow its workflows with these execution and authentication replacements:

1. Check `codeup status`; missing configuration requires the user to run `codeup setup`
   in their terminal. PAT entry belongs only in hidden terminal input.
2. Replace every `aliyun devops <arguments>` invocation with
   `codeup exec -- aliyun devops <arguments>`. Use this for discovery/help too.
   Codeup resolves the active profile automatically; natural-language requests need
   no wrapper syntax. Read-only commands need no additional authorization flags.
3. Read upstream scripts as reference. Execute their discovered official CLI
   commands through codeup; do not invoke scripts which launch raw aliyun.
4. For writes, explain target and effects, obtain explicit user authorization,
   then add `--authorize-write` before `exec`. Destructive operations additionally
   need `--authorize-destructive`; deployments and all Flow/AppStack writes need
   `--authorize-deployment`. Approval applies only to the specified action.
   Example: `codeup --authorize-write exec -- aliyun devops projex-create-workitem ...`.
5. If policy denies execution, report the fixed diagnostic. Credential setup,
   endpoint changes and executable repinning belong in codeup's terminal commands.

Token checks in upstream instructions mean `codeup status`; never inspect stored
PATs, request them in chat, export them, or invoke MCP/mcporter/direct HTTP fallbacks
to bypass this launcher. Upstream owns API workflows; codeup owns authentication
and executable policy. This adapter does not intercept arbitrary shell commands.
"""


def install(agent: str, project: Path, official: Path) -> dict:
    project = project.resolve()
    official = official.resolve()
    if not project.is_dir() or not (official / "SKILL.md").is_file():
        raise CodeupError("integration_source_missing", "Select an existing project and the official alibabacloud-devops Skill directory containing SKILL.md.")
    if any(node.is_symlink() for node in official.rglob("*")):
        raise CodeupError("unsafe_skill_source", "Official Skill source must not contain symlinks.")
    surface = ".agents" if agent == "codex" else ".claude"
    parent = project / surface / "skills"
    # Do not follow an existing link into unrelated/global Skill directories.
    for node in (project / surface, parent):
        if node.is_symlink():
            raise CodeupError("unsafe_integration_path", "Project Skill directories must not be symlinks.")
    target = parent / "aliyun-devops"
    if target.exists() or target.is_symlink():
        raise CodeupError("integration_exists", "Adapter already exists; review/remove it explicitly before reinstalling.")
    if target == official or target in official.parents or official in target.parents:
        raise CodeupError("unsafe_integration_path", "Official source and adapter destination must be separate directories.")
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".codeup-", dir=parent))
    try:
        shutil.copytree(official, temporary / "references" / "official")
        (temporary / "SKILL.md").write_text(ADAPTER, encoding="utf-8")
        source_hash = hashlib.sha256((official / "SKILL.md").read_bytes()).hexdigest()
        (temporary / "UPSTREAM.sha256").write_text(source_hash + "\n", encoding="ascii")
        temporary.rename(target)
    except OSError:
        raise CodeupError("integration_install_failed", "Cannot install project Skill adapter.") from None
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {"agent": agent, "path": str(target), "upstream_skill_sha256": source_hash}
