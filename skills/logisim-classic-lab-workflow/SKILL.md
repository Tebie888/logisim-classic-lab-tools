---
name: logisim-classic-lab-workflow
description: Inspect, edit, and simulate classic Logisim .circ projects, including the Logisim-HUST 2.15 course fork and its 74-series libraries. Identify the format before editing; Logisim Evolution projects are not supported.
---

# Logisim Classic Lab Workflow

支持经典 Logisim 课程电路及 HUST fork。先读取文件的 source、主电路和库映射；不要把 Evolution 工程当作经典工程修改。MCP 1.3.1 支持课程包中出现的 2.3.x、2.6.x、2.7.x 和 HUST 2.15.x，工程格式为 version="1.0"；其他来源只做读取诊断。

## 工具选择

配套 MCP：<MCP_INSTALL_DIR>\server.py，提供 28 个工具。优先用可用的 MCP；缺失时可使用本技能脚本。旧服务进程需重连才能加载升级后的工具和参数。

- 环境：logisim_env_info(probe_version=true) 动态确认 exe、Java 和版本，不依赖历史机器记录。
- 读取：describe_circuit、list_pins、list_library_index；需要原始片段时用 get_circuit_xml。
- 校验：validate_circuit 的 ok 表示没有 error；warning 单独列出。默认仅结构检查；接线或布局改动前后用 runtime=true，加载真实端口检查多驱动和位宽冲突。check_connections(expected_nets=...) 还能检查同位宽网络意外合并、断开和多接端口；不提供设计网络时无法证明接线符合意图。
- 仿真：simulate_tty(format="table,halt,stats", timeout_sec=30, include_output=true)。
- 表格：get_simulation_table 解析输出变化记录；get_truth_table 是兼容别名，**两者均不自动枚举输入**。complete 只表示本次采集和解析完成，输入覆盖率和功能正确性须另验证。
- 编辑：add_wire、add_pin、set_pin_label、remove_component、remove_wire 支持 dry_run=true，预览也进行候选校验。
- 完整搭建：build_project 一次创建多电路工程或向旧工程追加；build_circuit 是单电路入口。create_project、add_circuit、add_component 提供分步搭建。先 list_component_catalog 查真实名称和属性，用 get_component_ports 查 index、坐标、位宽及 tooltip，再按 nets 批量接线；已有元件用 connect_ports。
- 批量建图：components 用唯一 id 标识，nets 端点用 id+port 或 name+loc+port。默认 layout="readable" 用短导线、密集端口扇出及可读网络标签；label_spacing、tunnel_offset 调整间距，layout="compact" 保留端口直放隧道。两端网络可用 waypoints 画正交线；所有分支应列在同一个 net。dry_run 返回候选 XML 和实际端口，未知属性/位宽冲突/递归子电路/意外短接拒绝提交。保存 connection_manifest 作为后续 check_connections 的 expected_nets。详见 [完整搭建参考](full-circuit-building.md)。
- 图像：export_circuit_image 用 Logisim 自身绘图和仿真引擎导出 PNG，支持 inputs、steps 或 ticks，返回真实 pin_values；不保存 .circ、不覆盖已有图片。返回 layout_report 检查仿真后 Tunnel/元件显示框重叠，包含变宽的 Probe；用它检查整体布局与密集端口局部；报告中需要 GUI 操作证据时仍用实际 GUI 截图。
- 恢复：restore_backup 不传 backup 时列出快照；backup="latest" 只选择最新的编辑前 bak 快照。支持 dry_run=true。

编辑时读取真实库和坐标，并提供唯一定位条件。set_pin_label 必须有 loc 或 old_label；remove_component 必须有 loc，同坐标存在多个元件时补 name。不要猜测、自动选择第一个匹配项。

MCP 会检查候选 XML、精确修改结果和新增结构错误，再保存原始字节备份并原子提交；失败不会先覆盖原文件。已有结构错误仍需检查，warning 不阻止编辑。提交前检测到外部变更会取消操作；同时在 GUI 中保存同一文件仍应避免。

## 关键规则

- **可读性也是验收项**。提交前检查 layout_report，并查看导出图中的译码器、寄存器、选择器等密集端口。重叠时增大元件间距、标签间距或隧道偏移，保留功能分区；不能只把整张图缩小后当作清晰。布局前保留预期网络，改后重新检查并对照原测试向量；同位宽短接不会总产生 E。自动扇出不是全局排版，复杂邻近元件仍需明确坐标。
- **库索引按文件读**。2.7 的 Pin 通常在 #Wiring；旧课程文件可在 #Base。同文件子电路引用的 lib 为空或省略，name 指向该电路；不要套内建库编号。
- Pin 省略 width 时默认 1，经典位宽为 1..32。朝向为 east/west/north/south。
- **端口点落在导线线段上即可连接**，端点不必刚好是端口。Pin、Power、Ground、Constant 的端口在 loc；多端口元件还有与类型、size、inputs、facing 相关的偏移端口，部分端口也可能在 loc。
- 复杂元件优先 get_component_ports 动态读取真实端口，或复用课程实例。port-geometry.py 只提供附近端点统计候选，不是权威端口表。新增导线保持正交；已有斜线的效果须用具体电路验证，不能断言全部会卡死。
- **halt 是标签正好为 halt 的 Pin**，不是独立元件。HUST 实测与方向无关，值变为 1 才停机；该引脚不进入输出值表。测试电路应把实际停止信号接到 halt，单纯加标签不能保证停机，也不要擅自改变提交电路接口。
- -tty table 只记录主电路输出引脚的变化，表头会去掉前导 ! 并处理重名；HUST 还会定长截断表头、多位值用十六进制。真实标签看 list_pins；解析回退的 pin_columns 给出运行时列对应。完整功能验证需要测试计数器、输入刺激或测试向量覆盖。
- Pin 值 E 可能来自接线、位宽、冲突等问题，必须保留和检查；行尾 HUST 文本 Error！在最小确定电路也出现，解析器将精确匹配的重复标记汇总到 legacy_marker，未知尾部诊断仍保留。不能据此判震荡；震荡看明确停机消息或 verdict。
- 所有无界面仿真设置超时。没有 halt、值始终为 0 或加载失败，都可能不结束。停机只证明终止条件触发，输出仍须对照实验要求。

## 已验证工程与实验报告

只改布局时，复用接口、测试向量、断言和报告正文；受影响的网络检查、仿真及图片检查重跑，未变的有效证据不重复生成。先定稿布局并查看一张代表状态图，再导出各实验状态的最终图片。Probe 的数值框会随信号位宽扩展，静态 tunnel_overlap_count=0 不代表数值没有遮挡；检查导图返回的 simulated 显示框报告并查看原尺寸局部。报告更新及 Windows Word 渲染后备方案见 [报告复用参考](report-workflow.md)，仅需要报告时读取。

## 脚本后备方案

脚本路径相对**技能根目录**，不相对当前项目目录。当前维护源是 <SKILL_INSTALL_DIR>\；.agents\skills\logisim-classic-lab-workflow\ 是同步副本，修改维护源后同步对应文件。

~~~powershell
$skillRoot = '<SKILL_INSTALL_DIR>'
python "$skillRoot\scripts\inspect-circ.py" 'D:\path\lab.circ' --all
& "$skillRoot\scripts\tty-sim.ps1" -Circuit 'D:\path\lab.circ' -Format 'table,halt,stats' -TimeoutSec 30
& "$skillRoot\scripts\launch-logisim.cmd" 'D:\path\lab.circ'
~~~

最小运行检查：assets/minimal-halt.circ，Power 驱动 output halt Pin，预期打印 halted due to halt pin。MCP --print-config 只打印配置，不安装服务或验证运行环境；--self-test 会检查环境、结构和仿真，失败/超时返回非零。

GUI exe 通过 Launch4j 寻找注册表中的 JVM；无界面脚本走 java -jar，可显式选 Java。包中 class 最高为 Java 8；本机 JDK 17 已运行通过。-version 的 -1/4294967295 是该程序已知表现，需结合版本文本判断。

命令行选项、课程包资源、具体端口样例和 JVM 历史记录见 [reference.md](reference.md)，按当前任务读取相应章节。
