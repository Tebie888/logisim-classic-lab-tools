# 传播单步与延迟测量

需要观察门级传播、中间状态或延迟时读取。`export_circuit_image.steps` 每次赋值后运行至稳定，不能用于瞬态测量。

## trace_propagation

- `file`、可选 `circuit`：选择实际电路，不修改 `<main>`。
- `initial_inputs`：先赋值并运行至稳定的初态。
- `inputs`：从初态同时施加的新值；按真实位宽检查，只驱动顶层输入 Pin。
- `signals`：记录的顶层 Pin 标签；重复或缺失标签拒绝。
- `output_dir`：新目录，保存 `trace.csv`、`trace.json` 和可选图片；不覆盖已有目录。
- `anchor_signal`：可选，须包含在 signals 中；同时返回相对该信号首次实际变化的延迟。
- `capture_times`：请求后的引擎时刻。只捕捉实际观测到的事件时间；未观测时刻列在 `capture_times_not_observed`。
- `max_events`、`max_time`、`timeout_sec`：有限边界。事件或时间上限返回 `complete=false`；超时取消输出提交。
- `component` 或 `viewport`：可选图片区域，格式与 export_circuit_image 相同。

例如从16位全零初态同时输入完整 FFFF 与0001：

```json
{
  "file": "C:/work/alu.circ",
  "circuit": "RCA16",
  "output_dir": "C:/work/rca16-trace",
  "initial_inputs": {"A": "0x0000", "B": "0x0000", "Cin": 0},
  "inputs": {"A": "0xFFFF", "B": "0x0001"},
  "signals": ["A", "B", "Cin", "SUM", "Cout"],
  "capture_times": [8, 15, 65],
  "max_events": 512,
  "timeout_sec": 30
}
```

## 读数口径

`engine_time_from_request` 从输入设置请求起算，实际输入网络可能稍后变化。`anchor_first_change_time` 是观测到的输入变化时刻；不要混用两种起点。

每个信号返回 `first_change_time`、`last_change_time` 和 `final_stable_time`。最后一项表示本次已完成记录中最后一次进入最终值的时刻，通过全部记录行计算，避免把初态与最终值相同误认成提前完成。`fully_defined=false` 表示仍含未知或错误位，不能据此宣称运算正确。

`queue_empty_time` 表示内部事件全部处理完毕，可能晚于输出有效。`complete=false` 时不提供最终稳定时间，也不把限时停止当成通过；即便 complete=true，功能是否正确仍需对照题目预期。和与进位都有效的时间取两者的较晚值。

桥接器使用安装的真实 Logisim 传播 API，当前经 HUST 2.15 验证。其他版本如果缺少相应 API，应报告兼容错误，不切换自建门延迟模型。时间不换算为 ns。暂只记录选定电路的顶层 Pin；不通过重复子模块名称猜测层级实例。

## 数字示波器

周期编号不一定等于每格的引擎时间。测量时说明采样边沿和间隔；测试页若经子模块额外引入端口传播，应对内部与外部边沿校准并保留原始值。封装修正来自当前工程实测，不把某个副本的“减2”推广到其他电路。

GUI窗口截图、原生示波器导图、CSV绘制波形分别注明来源。报告正文主要保留设置、结果、原因分析及必要图片，复测程序和完整校验记录作为附件。
