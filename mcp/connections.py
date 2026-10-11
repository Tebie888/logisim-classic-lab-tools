"""Connectivity from runtime port coordinates, never component anchors."""
from collections import defaultdict

def graph(s, model, runtime):
    parent={};ports=[];labels=defaultdict(list)
    def root(p):
        parent.setdefault(p,p)
        while parent[p]!=p:parent[p]=parent[parent[p]];p=parent[p]
        return p
    def union(p,q):parent[root(p)]=root(q)
    for c in runtime['components']:
        for port in c['ports']:
            p=s.xy(port['loc']);root(p)
            if c['name']=='Tunnel':labels[c['attributes'].get('label','')].append(p)
            else:ports.append({'name':c['name'],'component_loc':s.norm_xy(c['loc']),**port})
    for name,points in labels.items():
        if name:
            for p in points[1:]:union(points[0],p)
    for w in model['wires']:union(s.xy(w['from']),s.xy(w['to']))
    # Intersections only join at a port or a wire endpoint. A plain crossing does not.
    points=list(parent)
    for w in model['wires']:
        p,q=s.xy(w['from']),s.xy(w['to'])
        for point in points:
            if s.on_segment(point,p,q):union(p,point)
    groups=defaultdict(lambda:{'ports':[],'wires':[],'labels':[]})
    for port in ports:groups[root(s.xy(port['loc']))]['ports'].append(port)
    for w in model['wires']:groups[root(s.xy(w['from']))]['wires'].append(w)
    for label,points in labels.items():
        if label:groups[root(points[0])]['labels'].append(label)
    return root,groups

def analyze(s, model, runtime, expected=(), include_networks=False):
    root,groups=graph(s,model,runtime);findings=[];claimed={};allowed=set()
    def add(code,message,g=None,ports=None,severity='error'):
        item={'severity':severity,'code':code,'message':message,'circuit':model['name']}
        if g is not None:item.update(labels=g['labels'],ports=ports if ports is not None else g['ports'],wires=g['wires'])
        findings.append(item)
    for n in expected:
        ends=[]
        for ep in n['endpoints']:
            candidates=[p for g in groups.values() for p in g['ports'] if p['name']==ep['name'] and s.xy(p['component_loc'])==s.xy(ep['loc']) and p['index']==ep['port']]
            ends.append(s._unique(candidates,'预期网络端口'))
        ids={root(s.xy(p['loc'])) for p in ends}
        if len(ids)!=1:
            add('disconnected_net',f"网络 {n['name']} 未完全连通",ports=ends)
            findings[-1]['ports']=ends
            continue
        ident=next(iter(ids));g=groups[ident]
        if n.get('allow_multiple_drivers'):allowed.add(ident)
        if ident in claimed:add('merged_nets',f"网络 {n['name']} 与 {claimed[ident]} 意外短接",g)
        claimed[ident]=n['name']
        keys={(p['name'],p['component_loc'],p['index']) for p in ends}
        extras=[p for p in g['ports'] if (p['name'],p['component_loc'],p['index']) not in keys]
        if extras:add('unexpected_port',f"网络 {n['name']} 意外连接了请求之外的端口",g,extras)
    for ident,g in groups.items():
        drivers=[p for p in g['ports'] if p['output'] and not p['input']]
        if len(drivers)>1 and ident not in allowed:
            conditional=any(p['name'] in {'Controlled Buffer','Controlled Inverter','RAM'} for p in drivers)
            add('multiple_drivers','同一连通网络包含多个独占输出；请检查短接，三态总线请在预期网络中显式声明 allow_multiple_drivers',g,drivers,'warning' if conditional else 'error')
    if runtime['width_conflicts']:
        add('runtime_width_conflict',f"Logisim 检测到 {runtime['width_conflicts']} 组位宽冲突")
        findings[-1]['points']=runtime.get('width_conflict_points',[])
    result={'circuit':model['name'],'runtime_checked':True,'network_count':len(groups),'findings':findings,
            'error_count':sum(f['severity']=='error' for f in findings),'warning_count':sum(f['severity']=='warning' for f in findings)}
    result['ok']=result['error_count']==0
    if include_networks:result['networks']=list(groups.values())
    return result

def check(s,a):
    p=s.resolve_circ(a['file']);d=s.parse_project(p)
    if not s.supported_source(d['source']) or d['version']!='1.0':raise s.ToolError('连通性检查仅支持经典 Logisim/HUST 工程')
    names=d['circuit_names'] if a.get('all') else [s.pick_circuit(d,a.get('circuit'))['name']]
    runtime=s._builder.probe(s,'inspect',a)
    expected=a.get('expected_nets',[])
    if a.get('all') and any('circuit' not in n for n in expected):raise s.ToolError('all=true 时每个 expected_net 必须注明 circuit')
    for n in expected:
        if n.get('circuit',names[0]) not in names:raise s.ToolError('预期网络的 circuit 不在本次检查范围内')
    results=[]
    for name in names:
        rc=next(c for c in runtime['circuits'] if c['name']==name)
        result=analyze(s,s.pick_circuit(d,name),rc,[n for n in expected if n.get('circuit',names[0])==name],a.get('include_networks',False))
        results.append(result)
    return {'file':str(p),'ok':all(r['ok'] for r in results),'runtime_checked':True,
            'error_count':sum(r['error_count'] for r in results),'warning_count':sum(r['warning_count'] for r in results),
            'findings':[f for r in results for f in r['findings']],'results':results,
            'intent_checked':bool(expected),'note':'使用真实端口与导线/隧道建图；没有 expected_nets 时只能发现驱动及位宽冲突，无法证明网络符合设计意图。'}

def install(s):
    text={'type':'string','minLength':1}
    ep={'type':'object','properties':{'name':text,'loc':text,'port':{'type':'integer','minimum':0}},'required':['name','loc','port'],'additionalProperties':False}
    net={'type':'object','properties':{'name':text,'circuit':text,'endpoints':{'type':'array','items':ep,'minItems':2,'maxItems':256},'allow_multiple_drivers':{'type':'boolean'}},'required':['name','endpoints'],'additionalProperties':False}
    props={'file':s.FILE_PROP,'circuit':s.CIRCUIT_PROP,'all':{'type':'boolean'},'expected_nets':{'type':'array','items':net,'maxItems':2000},'include_networks':{'type':'boolean'},'exe':text,'java':text}
    tool={'name':'check_connections','description':'使用真实运行时端口检查导线、隧道、多个驱动及位宽冲突，返回端口与导线坐标。expected_nets 可检查预期网络断开、意外合并及多接端口。不根据元件 loc 猜端口，不把普通线段交叉误判为连接。',
          'inputSchema':{'type':'object','properties':props,'required':['file'],'additionalProperties':False},'annotations':{'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False}}
    s.TOOLS.append(tool);s.TOOL_SCHEMAS[tool['name']]=tool['inputSchema'];s.TOOL_IMPL[tool['name']]=lambda a:check(s,a)
