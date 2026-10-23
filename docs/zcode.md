# ZCode 接入与验证

官方依据：[Skill](https://zcode.z.ai/en/docs/skill)、
[MCP Servers](https://zcode.z.ai/en/docs/mcp-services)。核对日期：2026-10-23。
本项目复用同一份 `skills/logisim-classic-lab-workflow/`，不维护 ZCode 专用副本。

## Skill 安装

用户级位置为 `~/.zcode/skills/logisim-classic-lab-workflow/SKILL.md`。
项目级可放在 `<project>/.zcode/skills/logisim-classic-lab-workflow/SKILL.md`；
本次本机 CLI 已发现这个项目位置。使用安装脚本时把完整目标目录传入
`--destination`，目录已存在时脚本会拒绝覆盖。

```powershell
python scripts/setup.py install-skill --destination "$env:USERPROFILE/.zcode/skills/logisim-classic-lab-workflow"
```

也可在 **Settings → Skills → Import** 中选已经安装到其他 Agent 的 Skill，
选择 Global 或当前 Project，然后选择 Symlink 或 Copy。Symlink 跟随同一源目录
更新；Copy 是独立安装，后续需要自行更新。Refresh 后确认来源和开关。

手动调用时在输入框输入 `$` 并选择 `logisim-classic-lab-workflow`，或从 `/`
菜单的 Skills 分组选择。自然语言请求检查、搭建或仿真经典 `.circ` 时可按
description 自动触发；这取决于模型选择、开关及元数据预算，不能保证每次触发。

## MCP 连接

先完成 [Python/Java/Logisim 安装](installation.md)。在 **Settings → MCP Servers →
New MCP Server** 中选择 User 或 Workspace、类型 stdio，填写实际 Python
可执行文件、`mcp/server.py` 的绝对路径参数，以及自己的 `LOGISIM_HUST_EXE`
和 `LOGISIM_MCP_WORKSPACE` 环境覆盖。使用绝对 Python 路径可避开 GUI 的 PATH 差异。

Full configuration 模式接受 `configs/mcpServers.json` 的结构。直接编辑磁盘原生
配置时使用 `configs/zcode.json` 的 `mcp.servers` 结构：

| 作用域 | 原生文件 |
| --- | --- |
| 用户 | `~/.zcode/cli/config.json` |
| 项目 | `<project>/.zcode/config.json` |

可先生成可合并条目：

```powershell
python scripts/setup.py config --client zcode --workspace .local/circuits --output .local/zcode.json
```

保留文件中其他设置。启用服务后重新连接并开始会话，确认工具数及只读调用。
ZCode 也读取 `.agents/mcp.json` 的 `mcpServers` 兼容格式，但同一作用域原生
`.zcode` 文件定义了任一服务后，会跳过该作用域整份 `.agents/mcp.json`。
同名服务跨作用域时用户级优先。这些规则来自当前官方文档。

## 验证顺序与提示词

1. Skill 列表能看到项目或用户级条目，并能手动加载。
2. MCP Servers 中条目 enabled/connected；会话工具列表包含 29 个本项目工具。
3. 选择一个可用模型，再执行只读调用：

> $logisim-classic-lab-workflow 请通过会话内 MCP 调用 logisim_env_info，
> probe_version=true，再对工作区中的公开半加器副本调用 describe_circuit。
> 先只报告版本和主电路，不修改文件，不用命令行代替 MCP。

通过后使用 [半加器流程](installation.md#register-mcp-then-verify-each-layer)。
检查真实工具调用记录和返回值，不能仅以模型回答“已连接”作为证据。

## 本次实际结果

- ZCode bundled CLI 0.17.0 的 `skills list --json` 发现了项目级标准 Skill。
- 独立 headless 会话在发送请求前返回 `Select a model before sending a message`。
  该次会话没有完成 MCP 工具调用，因此 **ZCode MCP 会话级连接、工具列出、
  模型调用及自动触发均未验证**。不能用独立协议检查代替这几项。
- UI 安装/连接步骤按官方文档核对；本次未自动操作桌面设置。
  原始会话、配置和诊断保留在本地隔离目录，不上传。

排查自动触发时先看 Skill 是否启用、描述是否可见；过多 Skill 会压缩元数据
预算。排查 MCP 时先看原生/兼容配置优先级、Python 路径、选定模型和服务状态。
修复前置条件后按上述顺序重测，不无限重试。

## GitHub 分发

直接克隆并安装 canonical Skill 和 MCP 即可，无须 ZCode Plugin。官方还支持
通过插件 marketplace 的 GitHub/git/本地来源分发 flat `skills/<name>/SKILL.md`
布局。该仓库的 Skill 布局符合这种布局要求，但本次未提供或验证插件
marketplace manifest，不把仓库声明为已测试的 ZCode Plugin。
