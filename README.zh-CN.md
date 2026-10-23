# Logisim Classic Lab Tools

[English](README.md) · [安装教程](docs/installation.md) · [兼容性矩阵](docs/compatibility.md) · [故障排查](docs/troubleshooting.md)

**一个通用 stdio MCP Server + 一套标准 Agent Skill + 各 AI 的轻量配置**，用于读取、
搭建、编辑、校验、仿真和导出经典 Logisim `.circ` 电路。当前服务 **1.4.1，29 个工具**：
保留公开 1.3.2 的全部 28 个工具，并整合本地已有的传播瞬态采样功能。

支持目标为经典 Logisim 2.3.x、2.6.x、2.7.x 的 `version="1.0"` 工程，以及实测
Logisim-HUST 2.15.0.2。**不是 Logisim-evolution 4.x 工具包。** 项目独立维护，
不代表任何学校、原 Logisim 作者或 AI 厂商。

## 已有能力与本次升级

- 读取工程、引脚、元件、子电路与库映射；检查结构和真实运行时连线。
- 新建单/多电路工程，添加组件、连线和端口网络；候选校验、dry-run、备份和原子提交。
- 带超时与输出上限的 TTY 仿真；解析输出变化表，保留 `get_truth_table` 兼容别名。
- 原生 PNG、局部元件/区域导图；检查仿真后的布局和真实 `pin_values`。
- 本地 1.4 新增的 `trace_propagation`：真实引擎事件 CSV、信号稳定时间、输入边沿对齐及可选瞬态图片。
- HUST GUI 的 `.exe` 来源后缀、可选精简构建返回；新增协议、编码、子电路分类、运行时路径和 Windows 文件锁修复。

详见 [29 个工具清单](docs/tools.md) 和 [本地/远程审计](docs/audit.md)。
现有 `mcp/`、`skills/`、`examples/`、`docs/` 均保留；不需要个人工程或课程文件。

## 各 AI 实际状态

官方文档支持某项标准，不等于本项目已在该客户端实测。完整矩阵分别记录 Skill 发现、
MCP 连接、工具列出、模型调用和 Logisim 执行。

| 客户端 | 本次项目证据 |
| --- | --- |
| OpenAI Codex | 已观察现有本地 1.4.0 工具的环境调用；提供 1.4.1 配置，新会话尚未测试 |
| Claude Code | 已核对官方配置及 Skill 路径；会话未验证 |
| Cursor | 已核对官方配置及 Skill 路径；会话未验证 |
| Gemini CLI | 已核对官方配置及 Skill 路径；会话未验证 |
| OpenCode | 已核对官方配置及 Skill 路径；会话未验证 |
| ZCode | CLI 0.17.0 已发现项目 Skill；MCP 会话测试受“未选择模型”前置条件阻断 |
| DeepSeek Harness | 真实 headless 会话加载 Skill、可见 29 个工具并直接调用只读 MCP 工具 |
| VS Code / GitHub Copilot | 提供原生/portable 配置说明；会话未验证 |
| 其他兼容客户端 | 提供标准入口示例，需自行验证宿主能力 |

[ZCode 教程](docs/zcode.md) · [Harness 教程](docs/deepseek-harness.md) ·
[逐层测试矩阵](docs/compatibility.md)。不会把“有配置文件”写成“已测试成功”。

## Windows 安装到首次调用

依赖 **Python 3.8+、Java 和自己安装的兼容经典 Logisim**；编译桥接类需要 JDK。
服务和安装脚本只用 Python 标准库，无须 pip、Node、WSL 或 Docker。
**仓库不附带 Logisim 可执行文件、JAR 或第三方资源。**

```powershell
git clone https://github.com/Tebie888/logisim-classic-lab-tools.git
Set-Location logisim-classic-lab-tools
# 以下为示意路径，换成你自己的经典 Logisim 程序或 JAR
$env:LOGISIM_HUST_EXE = 'C:/path/to/your/logisim.exe'
python scripts/setup.py compile
python scripts/setup.py doctor
New-Item -ItemType Directory -Force .local/circuits | Out-Null
python scripts/setup.py install-skill --destination "$env:USERPROFILE/.agents/skills/logisim-classic-lab-workflow"
python scripts/setup.py config --client codex --workspace .local/circuits --output .local/codex.toml
```

将生成条目合并到客户端配置，保留其他设置，再重连 MCP、刷新 Skill。
换客户端时修改 `--client` 和 Skill 目标目录，见 [安装步骤](docs/installation.md)
及 [配置位置表](configs/README.md)。脚本拒绝覆盖已有 Skill 和输出配置文件；
生成配置含本机绝对路径，只留本地。

Linux/macOS 使用 `python3`、自己的兼容 JAR、`export LOGISIM_HUST_EXE=...` 和 `$HOME`。
Java 查找与 classpath 使用跨平台方式；本次没有 Linux/macOS 的真实运行时测试，
Windows GUI/Word 脚本仍仅适用于 Windows。依赖和限制见 [兼容性](docs/compatibility.md)。

先让 AI 加载 `logisim-classic-lab-workflow`，确认能列出工具并真正调用
`logisim_env_info(probe_version=true)`。环境通过后可发送：

> 在配置的电路工作区里新建半加器：输入 A/B，输出 SUM=A XOR B、CARRY=A AND B。
> 先查询真实端口并 dry-run，再创建不覆盖已有文件的工程。保留 connection_manifest，
> 执行 runtime 校验和预期连线检查，用 00、01、10、11 四组输入导出不同 PNG，
> 断言 (SUM,CARRY) 分别为 (0,0)、(1,0)、(1,0)、(0,1)。

完整画图流程见 [使用教程](skills/logisim-classic-lab-workflow/tutorial.md)。
TTY 只运行文件的 `<main>`，表格工具**不自动枚举输入**；超时不是通过。
传播时间是引擎事件时间，不直接换算为 ns。

## 验证与隐私

候选验证、原始字节备份、原子替换和并发修改检查均保留。新建工程、PNG 和采样目录
拒绝覆盖。`LOGISIM_MCP_WORKSPACE` 限制文件和外部电路库路径；围栏内外部 JAR
需显式信任。围栏不是系统沙箱，Java/Logisim 和受信任库仍以当前用户权限运行。

```powershell
python -m unittest discover -s mcp -p "test*.py" -v
python mcp/build_examples.py .local/generated-examples
```

无运行时/桥接类时相关测试会 skip，不能算仿真通过。最新真实结果见
[VALIDATION.json](VALIDATION.json)，不继承历史 47 项通过结论。
发布前采用 [明确白名单](scripts/publish-allowlist.txt)，运行
`python scripts/check_release.py` 及 `--staged` 检查，并人工逐项复核。
[隐私审计](docs/privacy-audit.md) 说明排除文件与扫描范围；不上传个人电路、作业、
报告、真实配置、会话、凭据或第三方程序。

## 许可证

MIT，适用于本仓库原始源码、文档、脚本及匿名合成示例。Logisim 及其他第三方组件
不在分发包内，仍适用各自许可证。
