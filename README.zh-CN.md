# codeup

[English](README.md) | [简体中文](README.zh-CN.md)

面向官方 `aliyun devops` 命令的安全、跨平台启动器。需要 Python 3.10+，
运行时仅依赖 `keyring`。不另建 API 客户端或服务，也不修改官方 CLI。

## 安装与配置

在仓库目录中运行：

```sh
pipx install .
# 或：python -m pip install .
codeup setup
codeup status
codeup doctor
```

如果尚未安装，请先安装 [Alibaba Cloud CLI](https://www.alibabacloud.com/help/en/cli/)，
再执行 `aliyun plugin install --names aliyun-cli-devops` 安装官方云效插件。
初始化向导会检查 CLI 和插件，并在缺失时给出安装说明；不会自动下载未签名的
二进制文件，也不会执行远程安装脚本。

向导支持选择中文或英文、云效版本和配置名称，然后输入 API 地址、组织 ID，
并通过终端隐藏输入读取个人访问令牌（PAT）。令牌经
`base-get-user-by-token --quiet` 只读接口验证后，保存到系统原生凭据库。
验证失败时不会显示原始响应内容。

初始化前会检查当前选中的本地配置。配置已存在时，先询问是否重新配置；直接回车
默认保留现有配置并退出，不读取凭据库或验证令牌。选择“重新配置”后才继续向导。
指定新的配置名称时，不会显示此确认。

重新配置时，组织 ID 或 PAT 留空会保留原值。保留 PAT 时，也保留其凭据引用和
已记录的过期时间。CLI 路径信任提示为 `[Y/n]`：直接回车表示同意，输入 `n` 表示拒绝。

区域版需要实例的**公网 API 域名**；中心版使用官方默认地址，并要求提供组织 ID。
仅接受文档明确支持的 HTTPS 云效域名：`openapi-rdc.aliyuncs.com` 或
`INSTANCE.devops.aliyuncs.com`。地址不能包含用户名、密码、路径、查询参数、
片段或自定义端口。配置前请确认实例域名。

```sh
codeup setup --name work --edition central --organization-id ORG_ID --cli-path /absolute/path/to/aliyun
codeup setup --name regional --edition region --base-url https://INSTANCE.devops.aliyuncs.com --expires-at 2026-12-01T00:00:00Z
```

Windows 路径示例：`--cli-path C:\Tools\aliyun.exe`。
用于选择配置、授权操作或设置超时的全局参数应放在子命令之前。
初始化不接受命令行 PAT 参数、通过标准输入管道传入 PAT，或永久保存凭据环境变量。

初始化时会明确确认 CLI 路径，并记录绝对路径与 SHA-256 校验值。
升级官方 CLI 后，请先确认安装来源，再执行
`codeup config set --cli-path ABSOLUTE_PATH` 更新校验记录。
仅支持原生可执行文件；常规执行不会重新从 PATH 查找 CLI，也不会自动安装工具。

## 多配置与凭据管理

```sh
codeup profile list
codeup profile add --name personal
codeup profile use work
codeup --profile personal status
codeup --profile personal doctor
codeup --profile work auth rotate --expires-at 2026-12-01T00:00:00Z
codeup profile remove personal
```

每个配置独立保存凭据引用、云效版本、API 地址，以及可选的组织 ID、默认项目和
令牌过期时间。Agent 调用自动使用当前配置；`--profile` 仅为本次调用指定配置。
默认项目作为元数据供 Skill 使用，启动器不会据此生成未经官方定义的命令参数。
配置列表和状态检查不会显示 PAT。`status` 检查本地配置是否就绪；`doctor` 会执行
真实的只读请求，验证 PAT 是否可用。

支持 Windows Credential Manager、macOS Keychain 和 Linux Secret Service。
凭据库缺失、锁定或不受支持时，操作会失败，不会降级为明文存储。
Linux 需要可用的 Secret Service 会话，例如 `gnome-keyring` 或兼容服务。
无此服务的无界面机器需要另行配置安全凭据服务。

非敏感元数据保存在用户目录下的 `aliyun-cli-devops` 文件夹中：

- Windows：APPDATA。
- macOS：Application Support。
- Linux：XDG_CONFIG_HOME。

令牌轮换会先验证新 PAT，再创建新的凭据引用，原子提交元数据，最后删除旧引用。
请另行在云效控制台撤销旧令牌。`auth revoke` 只删除本地保存的凭据，不会撤销
服务端 PAT。已记录的过期时间用于本地拦截；服务端过期或撤销状态由 `doctor`
或官方 CLI 检测。不带 `--expires-at` 轮换令牌时，会清除旧的过期时间记录。

旧版单配置设置会迁移到 `default`，首次使用前需要确认 CLI 路径与校验值。
执行 `config reset` 前，需先删除已有配置。

## 执行官方 CLI 命令

```sh
codeup exec -- aliyun devops --help
codeup exec -- aliyun devops codeup-list-repositories --page 1 --per-page 20
codeup devops codeup-list-repositories --cli-query 'result[]' --all-pages
codeup --profile work --timeout 60 exec -- aliyun devops projex-search-projects
```

`devops` 是兼容入口。参数直接传给已校验的原生可执行文件，不经过 shell 解析。
标准输入、标准输出与错误输出的字节、JSON、查询参数、分页和常规退出码均透传。
即使 PAT 被拆分到多个输出块，其原始字节也会被脱敏。

输出缓冲最多保留一个 PAT 长度的尾部；只有与 PAT 前缀匹配的尾部可能延迟到后续
输出到达或进程结束。其他内容，包括交互提示，立即透传。
默认超时为 300 秒，最大为 86400 秒。取消时转发信号，并终止无响应的进程。
操作不会自动重试。

启动器只允许官方 DevOps 命令。默认放行官方 Skill 或 CLI 文档中明确列出的只读
操作，清单位于 `codeup_secure/read_commands.py`。其他操作及未知命令需要写入授权；
破坏性操作需要额外授权。所有 Flow/AppStack 写入和可能触发部署的操作，还需要
部署授权，因为启动器无法在本地判断流水线是否影响生产环境。

```sh
# 仅在明确授权具体目标和操作效果后执行：
codeup --authorize-write exec -- aliyun devops projex-create-workitem [OFFICIAL_FLAGS]
codeup --authorize-write --authorize-destructive exec -- aliyun devops codeup-delete-repository [OFFICIAL_FLAGS]
codeup --authorize-write --authorize-deployment exec -- aliyun devops flow-create-pipeline-run [OFFICIAL_FLAGS]
codeup policy set --allow 'codeup-*' 'projex-search-*' --deny 'codeup-delete-*'
codeup policy show
codeup policy set  # 清除自定义匹配规则，默认授权检查仍然生效
```

拒绝列表优先于允许列表；允许列表不会授予写入权限。空允许列表会拒绝所有操作。
单独使用 `COMMAND --help` 查询命令帮助时不注入凭据。

不允许通过命令参数传入凭据、覆盖 API 地址或组织 ID，也不允许开启 debug、
log-level、AI/请求检查模式或 dry-run。相关配置应通过配置管理命令设置。
诊断使用固定 JSON 错误码，不输出原始子进程或 keyring 异常。

## Claude Code 与 Codex 集成

使用官方 [Alibaba Cloud DevOps Skill](https://github.com/aliyun/alibabacloud-aiops-skills/tree/master/skills/developertools/rdc/alibabacloud-devops)。
获取并确认官方仓库来源后，安装**项目级适配器**：

```sh
codeup integrate --agent codex --project /path/to/project --official-skill /path/to/alibabacloud-aiops-skills/skills/developertools/rdc/alibabacloud-devops
codeup integrate --agent claude --project /path/to/project --official-skill /path/to/alibabacloud-aiops-skills/skills/developertools/rdc/alibabacloud-devops
```

Codex 适配器写入 `.agents/skills/aliyun-devops/`，Claude Code 适配器写入
`.claude/skills/aliyun-devops/`。官方文件原样复制到 `references/official`，
同时记录上游 Skill 的哈希值。安装器不会覆盖已有适配器；更新前需明确检查并移除
旧版本。按对应 Agent 的 Skill 加载机制重启或重新加载会话。

安装后可以直接提出自然语言请求：

- “列出我的云效项目。”
- “查看分配给我且尚未解决的工作项。”
- “在当前迭代中创建一个问题。”

适配器将命令发现和业务流程交给官方 Skill，并指示 Agent 自动通过 `codeup` 执行，
用户无需每次输入 `codeup exec`。上游的令牌环境变量检查、直接执行脚本和 MCP
回退调用，由 `codeup` 的配置检查和执行流程替代。不会修改全局安装的第三方文件
或官方 CLI 二进制文件。仓库中的插件 Skill 为已安装官方 Skill 的环境提供相同的
执行指引。

此集成依靠 Skill 指令引导执行，不是对任意可执行命令的透明拦截。
自动化测试验证适配器安装和子进程调用；真实自然语言行为仍需按端到端验收步骤
检查。凭据注入不构成对拥有同一系统用户任意 shell 权限的 Agent 的隔离。

## 验证与文档

```sh
python -m unittest discover -s tests -v
python -m pip wheel --no-deps --no-build-isolation . -w dist
```

测试模拟凭据库和外部依赖，使用模拟子进程检查参数、流式输出、脱敏、标准输入、
退出码、超时及并发配置隔离，不执行真实写入操作。

更多说明见 [官方能力调研](docs/research.md)、[安全边界与威胁模型](docs/security.md)、
[端到端验证](docs/validation.md) 和 [设计与实施计划](docs/design.md)。

兼容命令包括 `config show/set/reset`、`auth status/set/rotate/revoke`、
`upgrade`（从 GitHub 源码升级）和 `uninstall`（需要交互确认）。
卸载会移除 codeup 的配置和凭据，保留共享的 Alibaba CLI、云效插件及项目适配器。
