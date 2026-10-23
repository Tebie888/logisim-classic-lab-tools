# 已有作业的布局与报告更新

适用于已有经验证电路、测试和报告，只调整电路可读性或实验图片。编写/修改 DOCX 时另遵循当前可用的 documents 技能；不要修改该插件的安装文件。

1. 以用户本次指定文件为基线，先保留原件；不要用旧工程同名报告替代用户已修改的桌面版本。逐项对应题目位宽、输入、表格和图片；门级图、封装模块外观、级联图与实验状态图分别核对。要求封装时应展示可调用模块。复用接口定义、元件/网络请求、测试向量与断言；报告正文、表格及身份字段按授权范围保留。
2. 查询一次真实端口，布局修改同步预期网络中的定位坐标。先 dry_run，看密集组和 Tunnel 标签报告，再导一张代表状态图查看 Probe、文字和数值。Probe 传播后变宽；静态重叠数为零不代表仿真显示清晰。
3. 定稿后运行受影响的网络/功能检查，断言实际输出。再一次生成所需状态图片；每张导图建立独立状态，必须带完整 inputs/steps。不要反复生成全部报告图作为排版预览。
4. 只替换需要更新的图片及尺寸，核对保留的正文和表格。旧图片比例不能直接套用到新图；保持比例，按页面可用宽高设置尺寸。
5. 报告渲染前确认本机渲染引擎。Windows 无 LibreOffice 但有 Word 时，使用下方后备脚本；引擎缺失不等于 DOCX 损坏，不重复安装或反复尝试已知不可用路径。
6. 渲染后查看所有页面的裁切、表格及图中文字。最终证据需对应最终文件；不因只改图片而重新生成未受影响的测试向量/报告正文，但电路改动后受影响检查必须重跑。

## Windows 原生 Word 后备渲染

脚本仅用于只读导出 PDF，使用自己创建的隐藏 Word 实例，不接管用户已有窗口；源文件哈希核对，不保存 DOCX，不覆盖已有 PDF。Word 未安装或 COM 注册不可用时，保留原件并报告缺失引擎。

```powershell
$skillRoot = $PSScriptRoot
& "$skillRoot/scripts/render-report-word.ps1" -Docx 'C:/path/report.docx' -OutputPdf 'C:/path/review/report.pdf'
```

PDF 仅作检查中间件。通过 load_workspace_dependencies 获取当次 bundled Python 路径；在它提供 pypdfium2 时可直接逐页生成 PNG，无须猜测 fitz 或安装新依赖：

```python
from pathlib import Path
import pypdfium2 as pdfium
out = Path('C:/path/review')
with pdfium.PdfDocument(str(out / 'report.pdf')) as document:
    for number, page in enumerate(document, 1):
        page.render(scale=160/72).to_pil().save(out / f'page-{number}.png')
```

PNG/PDF 检查通过后再打包电路、报告、测试结果及说明。已有有效检查复用；报告图片变动需重新渲染页面，电路布局/支线变动需重新检查网络与受影响仿真。不要声称固定完成时间；用实际运行记录衡量流程改善。

## 报告范围与测量口径

实验正文主要保留设置、结果、原因分析和必要图片；复测程序、缓冲区核对与完整校验记录作为附件。精简时保留老师指定的题目和实验，不更换位宽。原生引擎导图与实际GUI窗口截图分别标明。

信号有效与事件队列清空时间分别记录；讨论和与进位都有效时，取两者稳定时间的较晚值。端口封装延迟按当前工程实测校准，不将某个测量副本的“减2”推广到其他电路。传播工具参数见[传播测量参考](propagation-measurement.md)。
