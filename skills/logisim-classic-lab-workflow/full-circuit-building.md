# 完整工程搭建（MCP 1.3.1）

配套服务 <MCP_INSTALL_DIR>\server.py 有 28 个工具；完整搭建用 Python 标准库与当前 Java/Logisim 运行时，无需 pip 或运行时 javac。builder.py、layout.py、connections.py、image_export.py 和 PortProbe/CircuitImage 的全部 class 文件必须与服务一起保留。旧 MCP 进程需重连后才出现新工具。

重连暂不可用时，可在新 Python 进程使用同一服务入口；参数和写入保护与 MCP 相同，不绕过校验：

~~~python
import json, sys
sys.path.insert(0, '<MCP_INSTALL_DIR>')
import server
result = server.call_tool('check_connections', {'file': 'C:/path/demo.circ', 'all': True})
payload = json.loads(result['content'][0]['text'])
if result.get('isError'):
    raise RuntimeError(payload)
print(json.dumps(payload, ensure_ascii=False))
~~~

## 推荐顺序

1. logisim_env_info 确认运行环境。list_component_catalog 获取真实 XML 元件名、library、defaults；当前本机 HUST 有 78 种，不把这个数量当其他安装的固定要求。factory_name 可能与 XML name 不同，应使用 name。
2. 用 build_project 一次声明 main 和 circuits。每个 circuit 包含 name、components、nets。本工程子电路可直接用其电路名作为 component.name，省略库；不允许递归引用。
3. components 每项有唯一 id、name、可选 loc/library/lib/attrs。library 为 #Wiring/#Gates/#Memory 等；lib 是已有工程实际索引。新工程自动声明运行时支持的内建库，追加时仅补缺失内建库。
4. 先 dry_run=true，返回 candidate_xml 和 ports。get_component_ports 适用于已有工程；它返回每个端口的 index、loc、width、input、output、tooltip 和元件 bounds。端口编号随属性变化；例如当前 HUST Counter 新布局有九个端口，Multiplexer 输出是 index=3，不能凭印象连线。
5. nets 按真实端口填写。新元件用 {id, port}，已有元件用 {name, loc, port}。一个 net 的 endpoints 包含全部分支，每个端口只列一次。位宽一致；多个独占输出默认拒绝，明确受使能控制的三态总线才传 allow_multiple_drivers=true。
6. 再调用建图提交，保存返回的 connection_manifest。用 validate_circuit(all=true,runtime=true) 与 check_connections(all=true,expected_nets=connection_manifest) 检查实际网络，再用 get_simulation_table/simulate_tty 对照输入刺激和预期输出。停机成功不能代替输出断言或输入覆盖验证。

## 定位与接线

未给 loc 时按每行五项、220×180 间距网格摆放；这是基础摆放，复杂布局应明确坐标。新增元件坐标在十像素网格，已有元件占用的坐标拒绝。

默认 routing 使用 Tunnel：同一网络使用独特标签，优先采用请求的网络名；与已有标签冲突时追加 _2 等后缀。结果 nets 返回网络名和实际 Tunnel 标签。

默认 layout="readable" 根据真实 bounds 和端口位置向外引出短导线，对密集端口扇出。tunnel_offset 默认 60（40..500），label_spacing 默认 40（20..200），单位为 Logisim 像素；布局可能为容纳拐角而增加实际偏移。layout="compact" 将 Tunnel 放在端口上，适合调用方自行排版。waypoints 网络不受这些参数影响。include_details=false 可省略完整 ports 和 candidate_xml，仍保留网络与布局摘要；查询端口或审阅 dry_run 时保持默认 true。

layout_report 返回每个电路的 tunnel_overlap_count 和最多 20 对相交标签位置；该检查只覆盖 Tunnel 的运行时 bounds，不覆盖全部元件、文字和导线遮挡。导出图仍需查看。元件靠得太近导致布线碰到其他端口时，真实连通性检查会拒绝提交；应调整 components.loc，不能跳过检查。长标签、邻近元件和复杂功能分区需要显式排版，不保证一次自动消除全部重叠。

两端网络可指定 waypoints=["(200,100)","(200,200)"]，起止点自动来自端口，折点间必须正交。waypoints=[] 表示直接画线。工具检查新网络端点完全连通、不同网络短接、经过其他端口以及运行时位宽冲突；已有连通分支也应全部列入该网络。

## 属性与来源兼容

attrs 值可为字符串、整数、布尔值；值使用 Logisim 标准格式，例如 Constant.value="0x3"、Pin.output=true、Counter.max="0x3"。未知属性、非法位宽及运行时忽略的值会拒绝。

ROM 可用 attrs.contents="addr/data: 2 4\n1 2 3 4\n"，同时设置 addrWidth=2、dataWidth=4；服务保存为 XML 元素文本并核对运行时内容。分线器可显式设置 bit0 等映射；先配置 incoming/fanout，再确认端口位宽。

新工程 source 使用当前运行时版本。已有工程保留来源：HUST 读取旧 source 时会迁移部分元件，Counter 默认写入兼容 old behavior；显式属性若被运行时改变，候选会拒绝。不能用 HUST 新布局的端口编号去猜旧来源计数器。

## 事务与工具边界

build_project/build_circuit 对已有电路执行追加，不替换或清空已有电路。分步工具为 create_project、add_circuit、add_component、connect_ports。create_project 对已有文件、add_circuit 对已有电路名分别拒绝覆盖。

候选完整解析、精确请求核对、实际加载元件/属性/端口、网络检查成功后才写。dry_run 不写文件和备份。旧文件保留未编辑原始文本，自动备份并原子替换；新文件独占创建，不覆盖其他程序新建文件。候选临时文件在工程旁边，退出后删除；外部课程库须能由声明的相对路径加载。

建图功能生成可由 GUI 打开的 .circ，不自动操作 GUI。可读布局提供局部端口扇出，不提供全局元件排版或避障寻路。输入枚举仍需显式测试向量或测试电路。

## 改布局后的验证与图像

check_connections 只读实际工程，用真实端口与导线/同名隧道建立网络。普通线段中间交叉不会直接判为连接，端口或导线端点落在线段上会连接。默认能发现多独占驱动及运行时位宽冲突；要发现同位宽的错误分支，传入修改前保存的 connection_manifest 作为 expected_nets。已有元件用 {name,loc,port}，all=true 时每个网络需注明 circuit。修改元件位置后同步更新清单中的 loc，保留网络端点身份和 port，不能从修改后的错误接线反推预期网络。三态网络需要显式 allow_multiple_drivers=true，并用输入刺激验证使能约束。

export_circuit_image 参数 file/output 必填，circuit 默认为主电路；output 必须是新 .png 路径，父目录已存在。scale 默认为 2（1..4），padding 默认 30（0..200），show_state 默认为 true。使用 Logisim 自身绘图引擎；不是用户 GUI 当前状态的截图。每次建立独立仿真状态，inputs 按输入 Pin 的唯一标签赋值，steps 依次更新并在每步传播后继续，ticks 在 steps 完成后推进 Clock（0..20000）。值可为非负整数、布尔或 0x/0b 字符串，必须适合引脚位宽；输出引脚、重复标签及越界值拒绝。pin_values 返回最终十六进制值，包含输入和输出。layout_report 使用仿真传播后的 bounds：tunnel_component_overlap_count/component_overlaps 给出 Tunnel 与元件本体遮挡（含 Probe 数值框）；tunnel_overlap_count 仍表示 Tunnel 之间。bounds_state="simulated"，不覆盖外部文字标签或导线。建图返回的静态布局报告不能替代这个检查。

例如验证写入：inputs={"CLK":0,"WE":1,"WA":0,"RA":0,"RB":0,"WD":"0x1829"}，steps=[{"CLK":1}]；应按实际实验断言 DA/DB。scale、引脚显示属性和图像清晰度按用途选取。show_state=false 只影响绘图，仍会运行刺激。timeout_sec 默认 30（1..120），图片最多 2400 万像素。源电路只读取，不保存输入状态，不覆盖图片。报告需要交互操作截图时使用实际 GUI。

## 可运行例子

- <MCP_INSTALL_DIR>\examples\full-adder.circ：主电路调用 FA 子电路的一位全加器，GUI 可点击 A/B/Cin。
- <MCP_INSTALL_DIR>\examples\counter-stop.circ：两位计数器按时钟输出 0、1、2、3 后 halt。
- 同目录 .json 是 build_project 的可复用参数，verification.json 是真实构建/仿真证据。把 JSON file 改为已存在目录内的新绝对路径。
- python <MCP_INSTALL_DIR>\build_examples.py NEW_DIRECTORY 可重新生成两例，已有例子拒绝覆盖。

完整回归：在服务目录运行 python -m unittest -v test_server test_improvements。真实集成测试覆盖全加器八组输入、时钟/计数器/寄存器/选择器、全部内建类型加载、ROM 内容、层级、密集端口、同位宽短接、仿真图导出及失败不写入。

## Probe 显示与重复导图

Probe 的 loc 是接线点；facing="east" 时接线点在数值框右端，数值向左显示，其他朝向同理。默认 readable 引线向接线点所在外侧延伸；相邻元件的隧道仍可能挡住数值框。不要把 Probe loc 当作显示框左上角，也不要按未仿真的 20 像素 bounds 预留空间。优先在独立支线上放 Probe，按真实仿真图留出整个数值框；方位/数值格式依当前运行时核实。

先查一次端口并保存组件/网络请求，布局调整只改坐标；密集组在 dry_run 看 layout_report，再导一张有代表性的状态图检查 Probe 和标签。布局定稿后才导出全部报告状态图，使用各自完整 inputs/steps，因为每次导图的仿真状态独立。按返回 pin_values 断言数值，并保留与最终文件对应的检查证据。Probe 也是预期网络端点，新增支线后同步 connection_manifest。
