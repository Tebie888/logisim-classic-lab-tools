"""Bounded propagation recording through the installed Logisim engine."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import xml.etree.ElementTree as E


def trace(s, a):
    source=s.resolve_circ(a['file']);project=s.parse_project(source)
    if not s.supported_source(project['source']) or project['version']!='1.0':
        raise s.ToolError('传播采样仅支持经典 Logisim/HUST 工程')
    s.check_runtime_libraries(source)
    circuit=s.pick_circuit(project,a.get('circuit'))['name']
    target=s.resolve_circ(a['output_dir'],must_exist=False)
    if target.exists() or not target.parent.is_dir():raise s.ToolError('output_dir 必须为尚不存在的目录，且父目录已存在')
    if len(set(a['signals']))!=len(a['signals']):raise s.ToolError('signals 不可重复')
    if a.get('anchor_signal') and a['anchor_signal'] not in a['signals']:raise s.ToolError('anchor_signal 必须包含在 signals 中')
    helper=Path(__file__).with_name('PropagationTrace.class')
    if not helper.is_file():raise s.ToolError('缺少 PropagationTrace.class；请编译传播采样桥接器')
    spec=importlib.util.spec_from_file_location('_trace_image_options',Path(__file__).with_name('image_export.py'))
    image=importlib.util.module_from_spec(spec);spec.loader.exec_module(image)
    req=E.Element('trace',circuit=circuit,max_events=str(a.get('max_events',4096)),max_time=str(a.get('max_time',1000000)),anchor_signal=a.get('anchor_signal',''),scale=str(a.get('scale',2)),padding=str(a.get('padding',30)),show_state='true')
    image.render_options(s,a,req)
    for tag,values in [('initial',a['initial_inputs']),('change',a['inputs'])]:
        element=E.SubElement(req,tag)
        for label,value in values.items():
            try:v=int(value,0) if isinstance(value,str) and value.lower().startswith(('0x','0b','0o')) else int(value)
            except (ValueError,TypeError):raise s.ToolError('输入值必须为整数或 0x/0b 数据：'+label)
            if not 0<=v<=0xffffffff:raise s.ToolError('输入值超出32位范围：'+label)
            E.SubElement(element,'pin',label=label,value=str(v))
    for label in a['signals']:E.SubElement(req,'signal',label=label)
    for time in a.get('capture_times',[]):E.SubElement(req,'capture',time=str(time))
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='.mcp-trace-',dir=target.parent) as tmp:
        tmp=Path(tmp);request=tmp/'request.xml';outdir=tmp/'record';outdir.mkdir()
        E.ElementTree(req).write(request,encoding='utf-8',xml_declaration=True)
        cmd=[s.find_java(a.get('java')),'-Djava.awt.headless=true','-Dfile.encoding=UTF-8','-Dsun.stdout.encoding=UTF-8','-cp',os.pathsep.join((str(helper.parent),s.find_exe(a.get('exe')))),'PropagationTrace',str(source),str(request),str(outdir)]
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
            proc=subprocess.Popen(cmd,stdout=out,stderr=err)
            try:proc.wait(timeout=a.get('timeout_sec',30))
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait();raise s.ToolError('传播采样超时，未创建交付目录')
            out.seek(0);err.seek(0);raw=out.read(1000001);diagnostic=err.read(12000).decode('utf-8','replace')
            if proc.returncode or len(raw)>1000000:raise s.ToolError('传播采样失败：'+diagnostic)
        try:metadata=json.loads(raw.decode('utf-8'))
        except (ValueError,UnicodeError) as exc:raise s.ToolError('传播桥接器返回无效JSON：'+str(exc))
        if hashlib.sha256(source.read_bytes()).hexdigest()!=before:raise s.ToolError('采样期间源文件被外部修改，本次记录未提交')
        result={'ok':metadata['complete'],'file':str(source),'circuit':circuit,'source_sha256':before,'source_modified':False,'output_dir':str(target),'csv':str(target/'trace.csv'),'metadata':str(target/'trace.json'),**metadata}
        (outdir/'trace.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        # Reserve the directory exclusively on every platform. POSIX rename
        # can replace an existing empty directory, which would violate this
        # tool's no-overwrite contract.
        try:target.mkdir()
        except FileExistsError:raise s.ToolError('目标目录被其他程序创建，本次记录未覆盖它')
        created=[]
        try:
            for item in sorted(outdir.iterdir(),key=lambda p:(p.name=='trace.json',p.name)):
                destination=target/item.name
                with destination.open('xb') as stream:
                    created.append(destination)
                    with item.open('rb') as incoming:shutil.copyfileobj(incoming,stream)
                    stream.flush();os.fsync(stream.fileno())
        except BaseException:
            for item in created:item.unlink(missing_ok=True)
            try:target.rmdir()
            except OSError:pass  # Preserve files created by another actor.
            raise
    return result


def install(s):
    text={'type':'string','minLength':1}
    values={'type':'object','additionalProperties':{'type':['integer','string','boolean']}}
    spec=importlib.util.spec_from_file_location('_trace_schema',Path(__file__).with_name('image_export.py'))
    image=importlib.util.module_from_spec(spec);spec.loader.exec_module(image)
    props={'file':s.FILE_PROP,'circuit':s.CIRCUIT_PROP,'output_dir':text,'initial_inputs':values,'inputs':values,
           'signals':{'type':'array','items':text,'minItems':1,'maxItems':64},'anchor_signal':text,
           'max_events':{'type':'integer','minimum':1,'maximum':10000},'max_time':{'type':'integer','minimum':1,'maximum':100000000},
           'capture_times':{'type':'array','items':{'type':'integer','minimum':0,'maximum':100000000},'maxItems':16},
           'scale':{'type':'integer','minimum':1,'maximum':4},'padding':{'type':'integer','minimum':0,'maximum':200},
           'timeout_sec':{'type':'integer','minimum':1,'maximum':120},'exe':text,'java':text,**image.render_schema()}
    tool={'name':'trace_propagation','description':'使用真实Logisim传播单步API：先稳定initial_inputs，再同时施加inputs，记录指定顶层Pin的瞬态CSV及延迟摘要。区分输出最终稳定时间与队列清空时间，可指定anchor_signal对齐真实输入边沿。capture_times导出观测到的事件时刻原生PNG；未观测时刻单独报告。达到事件/时间限制时complete=false，不报告最终稳定时间；不改工程，不覆盖目录。','inputSchema':{'type':'object','properties':props,'required':['file','output_dir','initial_inputs','inputs','signals'],'additionalProperties':False},'annotations':{'readOnlyHint':False,'destructiveHint':False,'openWorldHint':False}}
    s.TOOLS.append(tool);s.TOOL_SCHEMAS[tool['name']]=tool['inputSchema'];s.TOOL_IMPL[tool['name']]=lambda a:trace(s,a)
