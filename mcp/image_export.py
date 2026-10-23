"""Export only; never save or mutate the loaded circuit."""
import layout
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as E

def render_options(s,a,req):
    if 'component' in a and 'viewport' in a:raise s.ToolError('component 和 viewport 只能选择一个')
    if 'component' in a:
        req.set('component_name',a['component']['name']);req.set('component_loc',s.norm_xy(a['component']['loc']))
    for key,value in a.get('viewport',{}).items():req.set('viewport_'+key,str(value))

def render_schema():
    text={'type':'string','minLength':1}
    return {'component':{'type':'object','properties':{'name':text,'loc':text},'required':['name','loc'],'additionalProperties':False},
            'viewport':{'type':'object','properties':{'x':{'type':'integer'},'y':{'type':'integer'},'width':{'type':'integer','minimum':1,'maximum':20000},'height':{'type':'integer','minimum':1,'maximum':20000}},'required':['x','y','width','height'],'additionalProperties':False}}

def export(s,a):
    p=s.resolve_circ(a['file']);d=s.parse_project(p)
    if not s.supported_source(d['source']) or d['version']!='1.0':raise s.ToolError('图像导出仅支持经典 Logisim/HUST 工程')
    s.check_runtime_libraries(p)
    name=s.pick_circuit(d,a.get('circuit'))['name']
    output=s.resolve_circ(a['output'],must_exist=False)
    if output.suffix.lower()!='.png':raise s.ToolError('图像输出必须为 .png 文件')
    if output.exists():raise s.ToolError('输出已存在；导出不会覆盖已有图片')
    if not output.parent.is_dir():raise s.ToolError('图像输出目录不存在')
    helper=Path(__file__).with_name('CircuitImage.class')
    if not helper.is_file():raise s.ToolError('缺少 CircuitImage.class；请按 README 编译 Java 导出桥接器')
    req=E.Element('export',circuit=name,scale=str(a.get('scale',2)),padding=str(a.get('padding',30)),ticks=str(a.get('ticks',0)),show_state=str(a.get('show_state',True)).lower())
    render_options(s,a,req)
    for values in [a.get('inputs',{}),*a.get('steps',[])]:
        step=E.SubElement(req,'step')
        for label,value in values.items():
            try:
                v=int(value,0) if isinstance(value,str) and value.lower().startswith(('0x','0b','0o')) else int(value)
            except ValueError:raise s.ToolError('输入值必须为整数或 0x/0b 数据：'+label)
            if not 0<=v<=0xffffffff:raise s.ToolError('输入值超出 32 位非负整数范围：'+label)
            E.SubElement(step,'pin',label=label,value=str(v))
    with tempfile.TemporaryDirectory(prefix='.mcp-image-',dir=output.parent) as tmp:
        request=Path(tmp)/'request.xml';image=Path(tmp)/'image.png';E.ElementTree(req).write(request,encoding='utf-8',xml_declaration=True)
        cmd=[s.find_java(a.get('java')),'-Djava.awt.headless=true','-Dfile.encoding=UTF-8','-Dsun.stdout.encoding=UTF-8','-cp',os.pathsep.join((str(helper.parent),s.find_exe(a.get('exe')))),'CircuitImage',str(p),str(request),str(image)]
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
            proc=subprocess.Popen(cmd,stdout=out,stderr=err)
            try:proc.wait(timeout=a.get('timeout_sec',30))
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait();raise s.ToolError('图像导出超时，未创建输出文件')
            out.seek(0);err.seek(0);raw=out.read(1000001);diagnostic=err.read(8000).decode('utf-8','replace')
            if proc.returncode or len(raw)>1000000:raise s.ToolError('Logisim 图像导出失败：'+diagnostic)
        try:metadata=json.loads(raw.decode('utf-8'))
        except (ValueError,UnicodeError) as exc:raise s.ToolError('图像导出桥接器返回无效 JSON：'+str(exc))
        components=metadata.pop('layout_components')
        if 'component' in a:
            selector=a['component']
            components=[c for c in components if c['name']==selector['name'] and s.norm_xy(c['loc'])==s.norm_xy(selector['loc'])]
        elif 'viewport' in a:
            v=a['viewport'];pad=a.get('padding',30)
            components=[c for c in components if c['bounds']['x']+c['bounds']['width']>=v['x']-pad and c['bounds']['y']+c['bounds']['height']>=v['y']-pad and c['bounds']['x']<=v['x']+v['width']+pad and c['bounds']['y']<=v['y']+v['height']+pad]
        layout_report=layout.image_overlaps({'components':components})
        data=image.read_bytes()
        try:
            with output.open('xb') as stream:
                try:stream.write(data);stream.flush();os.fsync(stream.fileno())
                except BaseException:stream.close();output.unlink();raise
        except FileExistsError:raise s.ToolError('输出被其他程序创建；未覆盖该文件')
    return {'ok':True,'file':str(p),'circuit':name,'output':str(output),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'source_modified':False,'layout_report':layout_report,**metadata}

def install(s):
    text={'type':'string','minLength':1}
    values={'type':'object','additionalProperties':{'type':['integer','string','boolean']}}
    props={'file':s.FILE_PROP,'circuit':s.CIRCUIT_PROP,'output':text,'scale':{'type':'integer','minimum':1,'maximum':4},'padding':{'type':'integer','minimum':0,'maximum':200},'show_state':{'type':'boolean'},'inputs':values,'steps':{'type':'array','items':values,'maxItems':2048},'ticks':{'type':'integer','minimum':0,'maximum':20000},'timeout_sec':{'type':'integer','minimum':1,'maximum':120},'exe':text,'java':text,**render_schema()}
    tool={'name':'export_circuit_image','description':'使用 Logisim 自身绘图与仿真引擎导出 PNG，不改动 .circ。inputs/steps/ticks 运行到稳定态；传播瞬态用 trace_propagation。component(name+loc)单独绘制元件，viewport裁取原生电路区域，二者互斥。返回真实 pin_values 和仿真后布局报告；不是GUI窗口截图。拒绝重复标签、驱动输出、越界值和覆盖图片。',
          'inputSchema':{'type':'object','properties':props,'required':['file','output'],'additionalProperties':False},'annotations':{'readOnlyHint':False,'destructiveHint':False,'openWorldHint':False}}
    s.TOOLS.append(tool);s.TOOL_SCHEMAS[tool['name']]=tool['inputSchema'];s.TOOL_IMPL[tool['name']]=lambda a:export(s,a)
