# Classic Logisim Runtime Reference

命令行、格式和端口说明针对本课程包。路径、Java 和程序属性表是本机历史发现；使用前以 `logisim_env_info(probe_version=true)` 或实际命令复核。默认结构校验不证明功能正确；runtime=true 可加载真实端口检查冲突，预期网络、可读布局和导出见 [完整搭建参考](full-circuit-building.md)。

## 1. 命令行选项全表（来自 `-help` 与 jar 内 `resources/logisim/en/start.properties`，已实测）

```
usage: java com.cburch.logisim.gui.start.Startup [options] [filenames]

 -tty format       run without graphical interface   (format 逗号分隔)
 -sub file1 file2  load file replacing library file1 with file2
 -load file        load image file into RAM (works with -tty only)
 -empty            use empty template
 -plain            use standard Logisim template
 -template file    use file as template
 -gates shaped|rectangular
 -locale str
 -accents yes|no
 -nosplash         hides splash screen at startup
 -version          display version number and exit
 -help             display this summary and exit
 -clearprops       clear application preferences at startup
```

### `-tty` 格式取值（`Startup.parseArgs` 用 `String.split(",")` 解析）

| 取值 | 常量 | 作用 |
| --- | --- | --- |
| `table` | `FORMAT_TABLE = 1` | 打印信号值表。**列只有主电路的输出引脚**（输入引脚不进表），行在引脚值变化时输出 |
| `speed` | `FORMAT_SPEED = 2` | 打印仿真速度 `%s Hz (%s ticks in %s ms)` |
| `tty` | `FORMAT_TTY = 4` | 把电路里 TTY 元件的输出转发到 stdout（需要 TTY/Keyboard 元件，否则 `ttyNoTtyError`） |
| `halt` | `FORMAT_HALT = 8` | 打印终止原因（`halted due to halt pin` / `halted due to detected oscillation`） |
| `stats` | `FORMAT_STATISTICS = 16` | 打印元件统计表（各库元件数 / 唯一数 / 含子电路总数） |
| `few` | `FORMAT_FEW = 32` | 精简输出 |

其他相关字符串（同样来自 properties）：
- `ttyNeedsFileError = Using "-tty" requires a filename provided on command line.`
- `ttyFormatError = -tty requires at least one of the following: halt, speed, stats, table, tty`
- `loadNeedsTtyError` / `loadMultipleError` / `loadNoRamError`：`-load` 只能配 `-tty` 用且只能给一次，且电路里必须有 RAM。

### halt 引脚如何被识别（反编译 + 实测双重确认）

反编译 `TtyInterface.run()`：它调用 `Analyze.getPinLabels(Circuit)` 取得引脚标签表
（`Pin.FACTORY.isInputPin(instance)` / `Pin.getWidth(...)` 用于区分输入列与输出列），
再与字符串常量 `"halt"` 比较，命中后每 tick 读取 `Pin.getValue(InstanceState)`，
值为 `TRUE` 时打印 `ttyHaltReasonPin` 并退出。

实测（`-tty table,halt`）：

| 电路 | 结果 |
| --- | --- |
| `Power` → 标签 `halt` 的 **output** Pin | `halted due to halt pin`（立即停机）✅ |
| `Constant(0x1)` → 标签 `halt` 的 output Pin | `halted due to halt pin` ✅ |
| 74160 的 `TC` 输出 Pin 改名 `halt`（值一直 0） | 不停机；且值表表头里 **halt 列被剔除** |

结论：**标签必须正好是 `halt`**；识别与引脚方向无关；该引脚不参与值表输出；值为 1 即停机。

### 端口坐标与连通规则（控制实验实测；2026-10-09 更正）

实验方法：用 `Constant(0x1)` 驱动与门输入、输出接 `Pin`，加 `Power→halt` 收尾；看输出是 `1`（接通）还是 `E`（没接上）。

1. **导线接通的条件是"端口点落在导线线段上"**，不是"端点必须正好落在端口上"：
   - 端点正好落在端口上 → 通
   - 端点**越过**端口、线段仍覆盖端口 → 通（实测 `(60,90)→(200,90)`，端口 170，结果 `1`）
   - 线段**没覆盖**端口 → 不通（`(60,90)→(150,90)` 时若端口在 170 → `E`）
   - 来源端没被覆盖 → 也不通（`(80,90)→(200,90)`，Constant 端口在 60 → `E`）
2. **单引脚元件（`Pin`/`Power`/`Ground`/`Constant`）的端口就在 `loc`**。
3. **多端口元件还有偏移端口**：不能只根据 `loc` 判断连接。实测与门（`loc=(200,100)`、east）：
   - 输出端口在 `loc`
   - 输入端口在 `loc + (-size, ±10)`（2 输入）；3 输入为 `loc + (-size, -20/0/+20)`
   - `size` 属性改变端口位置：`size="30"`（74 系列文件写法）→ 输入在 `-30`；不写（默认）或 `size="50"` → 输入在 `-50`
   - 因此**端口偏移随元件类型与属性而变**，任何"按 `loc` 硬算连通性"的校验都会在官方电路上大量误报
4. **复杂元件（`Counter`/`ROM`/`Splitter`/`Multiplexer` 等）优先复用课程实例坐标**。仿真值必须对照预期；`E` 可能来自接线、位宽或驱动冲突，不唯一等于没接上。
5. **新增导线保持正交**：MCP 会拒绝新增斜线。已有斜线不能一概断言会卡死；本次含孤立斜线的样例仍正常停机，具体连通效果需要具体测试。
6. **畸形 `.circ` 同样会静默卡死**：例如把 `AND Gate` 写进 `lib="0"`（`#Wiring`）——Logisim 找不到元件，`-tty` 不打印任何东西也不退出。⇒ **任何无界面调用都必须带超时**。

## 2. `.circ` 格式（经典 Logisim 2.7）

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<project source="2.7.1" version="1.0">
  <lib desc="#Wiring" name="0"> <tool name="Probe">...</tool> </lib>
  <lib desc="#Gates" name="1"/>
  <lib desc="#Plexers" name="2"/>
  <lib desc="#Arithmetic" name="3"/>
  <lib desc="#Memory" name="4"/>
  <lib desc="#I/O" name="5"/>
  <lib desc="#Base" name="6"/>
  <main name="main"/>
  <circuit name="main">
    <comp lib="0" loc="(330,530)" name="Pin">
      <a name="facing" val="west"/>
      <a name="label" val="CLK"/>
      <a name="tristate" val="false"/>
    </comp>
    <comp lib="3" loc="(470,530)" name="Adder"/>
    <wire from="(350,530)" to="(450,530)"/>
  </circuit>
</project>
```

要点：

- `<lib desc="#X" name="N">`：`desc` 是库显示名（带 `#` 前缀），`name` 是索引；`<comp lib="N">` 引用该索引
- 库索引不一定固定，**以文件里 `<lib>` 的实际 name 为准**。经典版本之间有差异，实测两例：
  - `74160.circ`（`source="2.7.1"`）：`0=#Wiring 1=#Gates 2=#Plexers 3=#Arithmetic 4=#Memory 5=#I/O 6=#Base`，Pin 在 `#Wiring`
  - `74163.circ`（`source="2.6.2.165"`）：`0=#Base 1=#Gates 2=#Plexers 3=#Arithmetic 4=#Memory 5=#I/O`，**没有 `#Wiring`**，Pin 的 `lib="0"` 指向 `#Base`（2.6 时代 Pin 属于 Base 库）
  - 结论：别背索引，按映射读；`inspect-circ.py` 输出的 `Pin/#Base` 是真实归属，不是 bug
- 引脚：`name="Pin"`，`<a name="label">` 标签、`<a name="output" val="true">` 表示输出引脚（省略或 false 为输入）、`<a name="width" val="8">` 位宽、`<a name="facing">` 朝向
- **未写 `<a name="width">` 时位宽默认 1**：`inspect-circ.py` 显示的 `w1` 是默认值，不等于文件里显式声明过
- 连线：`<wire from="(x,y)" to="(x,y)"/>`；隧道 `<comp name="Tunnel">`
- 同文件子电路复用：`<comp lib="" loc="..." name="电路名"/>`（也可省略 `lib`）；`name` 指向同文件电路名，不能使用内建库索引冒充本地引用
- `<main name="...">` 指定启动时打开的电路

实测的库显示名：`#Wiring`（Pin/Splitter/Tunnel/Clock/Probe/Pull Resistor）、`#Gates`、`#Plexers`、`#Arithmetic`、`#Memory`、`#I/O`、`#Base`。

Logisim-HUST 的 I/O 库元件（jar 内 `com/cburch/logisim/std/io/`）：
`Button, Buzzer, DipSwitch, DotMatrix, HexDigit, Joystick, Keyboard, Led, RGBLed, SevenSegment, Slider, Switch, Tty, DigitalOscilloscope`。
**没有独立的 Halt 元件** —— 停机靠标签为 `halt` 的 Pin。

## 3. 课程包内文件实测属性

| 文件 | 类型 | Main-Class | class 版本 | 说明 |
| --- | --- | --- | --- | --- |
| `logisim-hust-20200118.exe` | Launch4j + 内嵌 jar | `com.cburch.logisim.Main` | 52 | Windows 主程序，2.15.0.2 |
| `logisim-hust-linux.jar` | jar | `com.cburch.logisim.Main` | 52 | 含 66 处 `com/sun/java/help/*`（内置 JavaHelp） |
| `logisim-hust-mac.jar` | jar | 同上 | 52 | macOS 版 |
| `Camera.jar` | Logisim 元件库 | `Camera` | 49 | 无 `sun.*` 引用 |
| `cs3410.jar` | Logisim 元件库 | `edu.cornell.cs3410.Components` | 49 | 康奈尔 CS3410 组件 |
| `Mars4_5.jar` | MIPS 模拟器 | `Mars` | 49 | 旧版 MARS |
| `rars1_3_1.jar` | RISC-V 模拟器 | `rars.Launch` | 52 | 均可在 JDK 17 上运行 |

74 系列电路包解包后的可用 `.circ`：

- `logisim_74v1.zip` → `74109 74138 74147 74148 74151 74154 74157 74160 74163 74164 74165 74166 74173 74181v3 74182 74193 74273 74374 74385 7442 7442v2 7451 74670 7474 7476 .circ`
- `circ7400-master.zip` → `circ7400.circ`
- `logi7400-master.zip` → `logi7400dip.circ`、`logi7400ic.circ`、`tests.circ`、`in-progress/74x299.circ`、`doc/*.md` 全部芯片手册、`dia/*.png` 引脚图

## 4. 启动与 JVM 选择细节

**两条路径选 JVM 的机制不同，别混为一谈：**

| 路径 | 选 JVM 的机制 | 本机结果 |
| --- | --- | --- |
| 双击 exe / `launch-logisim.cmd`（走 Launch4j） | 查**注册表**已安装 JRE，进程级 `JAVA_HOME`/`PATH` 不生效 | `<JDK_INSTALL_DIR>` |
| `tty-sim.ps1` / 手工 `java -jar <exe>`（绕开 Launch4j） | 用 `$env:JAVA_HOME\bin\java.exe`，其次 `PATH` 里的 `java` | 同为 JDK 17（恰好一致） |

Launch4j 3.12 调试日志（`launch4j.log`）关键行：
`Java min ver: 1.005.000`、`Java max ver:`（空）、`installedJreSearch()`、`64-bit search: SOFTWARE\JavaSoft\Java Runtime Environment...`
→ Launch4j 配置只设 Java 5 下限，但这不代表 Java 5 能加载包中所有 class：最高 class 52 要求 Java 8。JDK 17 已实际运行通过；无需强制使用 JDK 8。

要强制某个 JVM：直接
`"<jdk>\bin\javaw.exe" -jar "<...>\logisim-hust-20200118.exe"`

小提示：`-version` 会正常打印 `2.15.0.2.exe`，但进程退出码是 `-1`，不代表失败。

## 5. 无界面仿真的实测输出与判读

`-tty table,halt,stats` 对 `74160.circ`：

```
 2	 2	Splitter	Wiring        # 唯一数 / 含子电路总数，元件名，库名
14	14	Pin     	Wiring
 2	 2	NOT Gate	Gates
 1	 1	Buffer  	Gates
 2	 2	AND Gate	Gates
 1	 1	Counter 	Memory
22	22	TOTAL (without project's subcircuits)
22	22	TOTAL (with subcircuits)
Q0    Q1    Q2    Q3    TC      # 值表表头 = 引脚标签
0     0     0     0     0    Error！
```

- 表头**只列输出引脚**；且表头名不是原标签：
  - 去掉前导 `!`（实测 `!Q` 打印成 `Q`）
  - 去掉 `!` 后重名时按顺序加数字后缀（实测同电路 `Q` 与 `!Q` → 表头 `Q` / `Q2`；`Z`/`!Z` → `Z`/`Z2`）
  - 所以**不要用表头反推引脚标签**，要标签就用 `inspect-circ.py`
- 行尾 `Error！` 的触发条件尚未查明：在完全确定、无悬空、无时钟的最小电路上（包括本技能 `assets/minimal-halt.circ`）也会出现，**不能据此判断震荡/未稳定**。要判震荡只看 `halted due to detected oscillation`
- 没有 halt 引脚时**进程会一直 tick 直到超时**；但只有在引脚值发生变化时才追加新行，所以没有 Clock/输入变化的电路可能 7 秒只出一行（这不代表输出被截断）

## 6. 端口几何候选（附近端点统计；门类另有控制实验）

`python scripts\port-geometry.py <目录或文件>` 可复现。**统计结果不是已验证的端口表**：
脚本统计每个元件附近 ±100 内的导线端点，无法确认端点属于哪个元件；覆盖率 ≥90% 仍可能混入邻居连接。当前脚本按 facing、size、inputs 分组，默认值和显式值分别记录；门类几何优先使用第一节中的控制实验结论。

| 元件 | facing | 端口（相对 `loc`） |
| --- | --- | --- |
| `Pin`（#Wiring / #Base，各朝向） | 全部 | `(+0,+0)` [>99%]（单引脚，端口=loc） |
| `AND Gate` | east | 输出 `(+0,+0)`；输入 `(-size,+10)`、`(-size,-10)`（**控制实验**：size=30→-30；默认/50→-50） |
| `AND Gate` | north | `(+0,+0)`，`(+10,+30)`，`(-10,+30)` |
| `AND Gate` | south | `(+0,+0)`，`(+10,-30)`，`(-10,-30)` |
| `OR Gate` | east / south | east：`(+0,+0)`、`(-30,+10)`、`(-30,-10)`；south：`(+0,+0)`、`(+10,-30)`、`(-10,-30)` |
| `NAND / NOR / XOR Gate` | east | `(+0,+0)`，`(-40,+10)`，`(-40,-10)`（该批文件里的常见值；`-40` 说明这些实例的 `size` 与 74 系列 AND 门不同 → 必须按实例核对） |
| `NOT Gate` | east | `(+0,+0)`（输入偏移随 `size` 变化，未达阈值） |
| `Buffer` | east | 输出 `(+0,+0)`，输入 `(-20,+0)` |
| `D Flip-Flop`（#Memory） | east | `(+0,+0)`，`(-40,+0)`，`(-40,+20)` |
| `Register`（#Memory） | east | `(+0,+0)`，`(-30,+0)`，`(-20,+20)` |
| `Multiplexer`（#Plexers） | east | `(+0,+0)`，`(-30,+10)`，`(-30,-10)`，`(-20,+20)` |
| `LED`（#I/O） | east | `(+0,+0)`，`(-40,+0)` |
| `Ground` / `Constant` / `Power`（#Wiring） | east | `(+0,+0)` |
| `Splitter`（#Wiring） | east | 总线端 `(+20,-10)`；分支端随配置变化 |

**注意**：带 `size`/`inputs` 属性的门（如 3 输入 NAND/AND）端口位置会变——输入纵向间距 20、以 `loc.y` 居中，横向在 `-size`。
生成电路时**优先复制现有实例的坐标**；改完使用仿真与预期输出对照。单纯“没有 Error”不证明功能正确。
**Constant 写法**（驱动输入要用，已从真实文件确认；`lib` 索引用该文件映射到 `#Wiring`/`#Base` 的那个）：

```xml
<comp lib="0" loc="(640,210)" name="Constant">
  <a name="facing" val="west"/>
  <a name="value" val="0x0"/>
</comp>
```

## 7. MCP 1.1 的编辑与仿真结果

- 支持课程包里的 source 2.3.x、2.6.x、2.7.x 和 HUST 2.15.x，version=1.0。已检查 74182.circ 使用 source=2.3.2。未知来源可以读取，但校验报告 error，并拒绝编辑或调用 HUST 仿真。
- 编辑先解析候选字节，校验精确元件/导线变化、非目标电路和新增结构错误，再备份并用同目录临时文件原子替换。UTF-8 BOM 和原有换行保留；dry_run 也验证候选但不创建备份。
- 备份的创建时间编码在名称内，latest 不再依赖被复制的原文件 mtime。恢复前验证备份的 XML、来源和电路存在性，再保存当前原始字节；损坏备份不会覆盖工作文件。
- 唯一定位失败会拒绝编辑。标签自动 XML 转义，支持 &、引号、反斜杠；Pin 位宽为 1..32，朝向为四个标准值。
- validate_circuit 的 ok 表示 error_count=0；warning 单独返回。不能把结构 ok 当成电路逻辑正确或端口连通证明。
- simulate_tty 返回 process_ok、exit_code、timed_out 和输出截断信息；非零退出会标为 error，震荡、超时和输出上限单独区分。LOGISIM_MCP_MAX_OUTPUT_BYTES 默认 4194304，LOGISIM_MCP_MAX_TIMEOUT 默认 300。
- get_simulation_table 的 rows 保留与停机消息同一行的数值。get_truth_table 是兼容别名，不枚举输入。complete 仅指本次采集/解析完成；仍需明确测试输入与期望输出。
- --print-config 只生成配置文本；--self-test 在环境不可用、结构错误、震荡或超时时返回非零。stdio 服务器仍按原命令启动，不加 --print-config。

当前进程加载的是启动时的代码。更新 server.py 后，需要重新连接该 MCP 或重启 Codex，让新版本和新增工具重新加载。

## 8. MCP 1.2 完整搭建

新增 create_project、add_circuit、add_component、build_circuit、build_project、connect_ports、list_component_catalog、get_component_ports，共 26 个工具。多电路批量请求在候选上实际加载验证，使用运行时端口编号接线；默认 Tunnel 网络，也可显式 waypoints 画正交导线。用 dry_run 查看候选 XML 和端口后提交。

本机 HUST 元件目录有 78 种，已全部批量加载；功能检查包括全加器八组输入、时钟驱动计数器、寄存器和选择器。工程来源决定 HUST 迁移行为，新工程采用运行时版本，旧工程 Counter 默认采用兼容旧布局。不要把旧实例的端口编号套给新布局。

HUST -tty 多位值为十六进制；表头字段宽度为 ceil(width/4)+5，长标签截断，字段直接拼接。1.2 解析列数失败时查询实际输出列并核对原始表头，再按字段拆分，返回 pin_columns 和 value_radix=16。原始输出仍保留，不能据截断表头反推原 Pin 标签。

## 9. MCP 1.3 可读布局与诊断

共 28 个工具，新增 check_connections 与 export_circuit_image。默认建图用真实端口向外扇出和可读网络名，返回布局摘要与 connection_manifest；改布局后用保存的预期清单检查同位宽短接，再对照功能刺激并查看导出图。自动扇出是局部布局，仍需明确元件间距。图像由独立真实仿真状态生成，源文件不保存，输出 PNG 不覆盖已有文件。

解析器将精确匹配的重复行尾 Error！/Error! 汇总为 legacy_marker，原始输出保留，真实信号 E 与未知尾部诊断仍保留。不能用文本标记的次数证明逻辑故障或震荡。

## 10. MCP 1.4.1 当前入口

当前为 29 个工具。1.4 新增的 trace_propagation、局部/元件导图及构建返回精简保持原有默认行为；详见 propagation-measurement.md 和当前工具 Schema。上面的 1.1/1.2/1.3 章节是版本沿革，不是当前工具数量。

围栏内运行时会递归检查外部 file# 电路库；外部 JAR 库需显式信任。协议非法参数返回 -32602，执行错误返回 isError=true。更新代码后重连服务，不能只更新 Skill 就假定运行中的工具也已更新。
