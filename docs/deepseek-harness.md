# 在 DeepSeek Harness 中接入

本仓库包含一份 Agent Skill 和一个独立的 stdio MCP 服务。Harness 需要分别发现 Skill、启动 MCP 服务：仅把仓库克隆到电脑上不会自动把工具加入会话。MCP 是可执行的本地服务，请只连接你信任的源码。

## 1. 安装 Skill

把仓库中的 `skills/logisim-classic-lab-workflow/` 复制到项目的 `.agents/skills/logisim-classic-lab-workflow/`，保留整个目录。Harness 的 Skill 发现范围以当前版本文档为准；`.agents/skills/` 是受支持的项目级位置。打开项目后重新开始会话，并让模型读取 `logisim-classic-lab-workflow`。

## 2. 准备 MCP 服务

确保已安装 Python 3.8+、兼容的经典 Logisim 程序和 Java。仓库不附带 Logisim 程序或 JAR。Windows PowerShell 中先设置当前用户自己的路径，再编译 Java 8 桥接类：

```powershell
$env:LOGISIM_HUST_EXE = 'C:/path/to/your/logisim.exe'
Set-Location 'C:/path/to/logisim-classic-lab-tools/mcp'
javac --release 8 -encoding UTF-8 -classpath $env:LOGISIM_HUST_EXE PortProbe.java CircuitImage.java
python server.py --version
python server.py --print-config
```

编译只需执行一次，或在 Java 源码变化后重新执行。`--print-config` 只展示客户端配置，不会注册服务或检查 Logisim 是否可运行。

## 3. 注册 Harness 的 MCP 客户端

Harness 使用官方 `@deepseek-ai/dsh-mcp-client`，不是 README 通用章节中的 `mcpServers` JSON。确保该客户端已安装到你启动的 Harness profile；如果缺失，参照[官方 MCP 客户端说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)安装与当前 DSH 兼容的版本。安装客户端包本身不会自动启用任何 MCP 服务，也不需要把它作为单独的 bundle 注册；MCP server 条目仍须写入 Cordis patch。

将下面配置合并进该 profile 的 `cordis.patch.yml`。通常文件位于 `$DSH_HOME/profiles/<profile>/cordis.patch.yml`；不要覆盖已有 patch，保留其他条目，并确保 `id` 和 `serverName` 在当前配置中唯一。

```yaml
- insert:
    - id: mcp-logisim-classic-lab
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: logisim-classic-lab
        transport: stdio
        command: python
        args:
          - 'C:/path/to/logisim-classic-lab-tools/mcp/server.py'
        env:
          LOGISIM_HUST_EXE: 'C:/path/to/your/logisim.exe'
          LOGISIM_MCP_WORKSPACE: 'C:/path/to/your/circuit-workspace'
```

把两个示例路径改成真实路径。`command` 必须能由 Harness 进程启动；若 `python` 不在它的 `PATH` 中，填入 `python.exe` 的完整路径。`LOGISIM_HUST_EXE` 是环境覆盖名，为兼容保留；它应指向你自己安装的经典 Logisim 程序。若缺失，环境检查会返回 `exe_exists=false`。服务默认不搜索整台电脑；也可在 `env` 中设置 `LOGISIM_SEARCH_ROOT` 指向一个目录，让服务递归查找 `logisim-hust-*.exe`。

该条目是 profile patch 数组中的一项，应与文件中现有的 `- insert:` 等 patch 项合并，不要复制覆盖整份 profile 配置。完成后重启或重新加载对应 Harness profile，并新建会话。

## 4. 验证会话接入

先要求模型读取 Skill，再发出：

> 请调用 `mcp__logisim-classic-lab__logisim_env_info` 检查 Logisim 和 Java，并确认工具列表包含 `build_project`、`check_connections` 和 `export_circuit_image`。先只报告检测结果，不要创建或修改文件。

如果会话里看不到 `mcp__logisim-classic-lab__...` 工具，检查 profile patch 是否已加载、客户端包是否安装到同一 profile、Python 命令和脚本路径是否有效，然后重启该 profile。若工具可见但 `exe_exists=false`，修复 `LOGISIM_HUST_EXE` 或 `LOGISIM_SEARCH_ROOT`。

验证通过后，可让它在新的临时目录中创建半加器，逐向量调用构建/导图，并通过返回的 `pin_values` 核对结果。不要只凭电路图片判断功能正确。

## 工具边界

- Skill 负责指导模型按步骤工作；MCP 服务才会执行读取、构建、校验、仿真和图像导出。
- `simulate_tty` 和 `get_simulation_table` 接受工程文件路径，运行其中的 `<main>`；它们没有选择子电路的 `circuit` 参数。要单独测试某个非主电路，准备以该电路为 `<main>` 的测试工程。
- 没有 `halt` Pin 的 `simulate_tty` 可能运行到超时，这是保护机制，不代表工具接入失败。超时后通过测试工程或 `export_circuit_image` 的输入刺激验证逻辑。
- `get_simulation_table` 和兼容别名 `get_truth_table` 解析运行输出，不自动枚举全部输入。要证明逻辑功能，必须明确提供并检查测试向量。

## 2026-10-23 重新验证与简化安装

真实 headless profile 已完成 Skill 加载、29 个模型可见 Logisim 工具的发现，
以及环境和电路读取调用；不是在 shell 中手写 JSON-RPC。CLI 与
`@deepseek-ai/dsh-mcp-client`、`@deepseek-ai/dsh-skill`、
`@deepseek-ai/dsh-skill-filesystem`、`@deepseek-ai/dsh-tool-skill` 实测均为
0.1.7-rc.2。独立 Electron launcher/受管理 desktop profile 不能与它混用。
完整结果见[会话测试记录](harness-session-test.md)和[矩阵](compatibility.md)。

可使用跨平台 helper 生成额外 overlay：

```powershell
python scripts/setup.py compile
python scripts/setup.py config --client harness --workspace .local/circuits --output .local/logisim.cordis.yml
dsh --profile headless --patch .local/logisim.cordis.yml '加载 logisim-classic-lab-workflow，并实际调用 Logisim MCP 环境检查。'
```

先创建 `.local/circuits`，设置自己的 `LOGISIM_HUST_EXE`，并安装 Skill。
上例不覆盖 profile。已有同名服务时不要重复叠加；`id`、`serverName` 应唯一。
Web 可用 `--profile web`，或把生成项合并进实际 Web profile patch。
本次未自动改写用户正在使用的 Web/desktop profile。

Skill 可安装到用户 `~/.agents/skills/` 或项目 `.agents/skills/`。
标准组合通常已有三个 Skill 插件；自定义 profile 缺项时按当前版本文档补齐。
若 MCP 包缺失，可用
`dsh plugin --profile <name> add @deepseek-ai/dsh-mcp-client@<compatible-version>`，
不要混入与当前 Harness 不兼容的版本；包安装后仍须添加服务挂载条目。

本次采用独立 `DSH_HOME`、专用 headless profile、canonical Skill 的
`customSkillDirs`。认证由现有本地凭据提供者读取，未复制密钥或上传原始会话。
已检查的现有 web 组合有 Skill 插件但没有 Logisim MCP 条目，重现了旧问题的原因。
