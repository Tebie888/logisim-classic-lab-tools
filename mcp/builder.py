"""Complete classic project construction; no third-party Python dependencies."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import layout


def probe(s, mode, a, text=None, parent=None):
    helper = Path(__file__).with_name("PortProbe.class")
    if not helper.is_file():
        raise s.ToolError("缺少 PortProbe.class；请按 README 编译附带的 Java 8 源码")
    exe, java = s.find_exe(a.get("exe")), s.find_java(a.get("java"))
    # A candidate lives beside its target, so relative course libraries still resolve.
    temporary = None
    try:
        args = [java, "-Djava.awt.headless=true", "-Dfile.encoding=UTF-8",
                "-Dsun.stdout.encoding=UTF-8", "-cp", os.pathsep.join((str(helper.parent), exe)), "PortProbe", mode]
        if mode == "inspect":
            if text is not None:
                fd, name = tempfile.mkstemp(prefix=".mcp-probe-", suffix=".circ", dir=parent)
                temporary = Path(name)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(text.encode("utf-8"))
                args.append(str(temporary))
            else:
                args.append(str(s.resolve_circ(a["file"])))
        # Disk capture bounds memory even if an incompatible fork prints diagnostics.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(args, stdout=out, stderr=err)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
                raise s.ToolError("Logisim 端口查询超过 20 秒，候选未提交")
            out.seek(0); err.seek(0)
            raw, diagnostic = out.read(8_000_001), err.read(8000).decode("utf-8", "replace")
            if proc.returncode or len(raw) > 8_000_000:
                raise s.ToolError("Logisim 拒绝候选元件/属性/库：" + diagnostic)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise s.ToolError(f"端口查询返回无效 JSON：{exc}；{diagnostic}")
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def component_xml(s, comp, indent="    ", nl="\n"):
    lib = f' lib="{s.xml_value(comp["lib"])}"' if comp["lib"] else ""
    lines = [f'{indent}<comp{lib} loc="{comp["loc"]}" name="{s.xml_value(comp["name"])}">']
    for key, value in comp["attrs"].items():
        # Logisim's ROM/RAM content readers consume element text, not a val attribute.
        if key.lower() == "contents" and "\n" in value:
            lines.append(f'{indent}  <a name="{s.xml_value(key)}">{s.escape(value)}</a>')
        else:
            lines.append(f'{indent}  <a name="{s.xml_value(key)}" val="{s.xml_value(value)}"/>')
    lines.append(f"{indent}</comp>")
    return nl.join(lines) + nl


def empty_project(s, main, names, source="2.15.0.2", libraries=None):
    libs = libraries or ("Wiring", "Gates", "Plexers", "Arithmetic", "Memory", "I/O", "Base", "TTL")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<project source="{s.xml_value(source)}" version="1.0">',
             'This file is intended to be loaded by Logisim (http://www.cburch.com/logisim/).']
    lines += [f'  <lib name="{i}" desc="#{name}"/>' for i, name in enumerate(libs)]
    lines += [f'  <main name="{s.xml_value(main)}"/>']
    lines += [f'  <circuit name="{s.xml_value(name)}"/>' for name in names]
    return "\n".join(lines + ["</project>", ""])


def insert_root(s, text, block):
    root = next(x for x in s.element_spans(text, "project") if x["parent"] is None)
    at = root["close_start"]
    return text[:at] + block + text[at:]


def append_components(s, text, circuit, comps, wires=()):
    span = next(x for x in s.element_spans(text, "circuit") if x["attrs"].get("name") == circuit)
    body = text[span["start"]:span["end"]]
    indent, nl = s.detect_indent(body), s.newline_style(text)
    block = "".join(component_xml(s, c, indent, nl) for c in comps)
    block += "".join(f'{indent}<wire from="{w["from"]}" to="{w["to"]}"/>{nl}' for w in wires)
    return s.insert_in_circuit(text, span, block) if block else text


def commit(s, path, before, text, expected, dry_run):
    raw = text.encode("utf-8")
    data = s.parse_project_bytes(raw, str(path))
    for key in ("source", "version", "main", "libs", "circuit_names", "circuits"):
        if data[key] != expected[key]:
            raise s.ToolError(f"候选 {key} 与批量建图请求不一致；原文件未改动")
    errors = s.error_signatures(data)
    if before is not None:
        errors -= s.error_signatures(s.parse_project_bytes(before))
    if errors:
        raise s.ToolError("候选结构校验失败：" + "；".join(x[2] for x in errors))
    result = {"ok": True, "file": str(path), "bytes_after": len(raw),
              "sha256_after": hashlib.sha256(raw).hexdigest(),
              "circuit_names": data["circuit_names"], "dry_run": dry_run}
    if dry_run:
        result["candidate_xml"] = text
        return result
    if before is None:
        # Exclusive creation: a concurrent new file can never be overwritten.
        try:
            with path.open("xb") as stream:
                try:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                except BaseException:
                    stream.close(); path.unlink(); raise
        except FileExistsError:
            raise s.ToolError("目标文件已经存在；新建不会覆盖已有工程")
        result["created"] = True
    elif raw != before:
        if path.read_bytes() != before:
            raise s.ToolError("文件已被其他程序修改，本次提交取消")
        bak = s.make_backup(path, raw=before)
        try:
            s.atomic_replace(path, raw, before)
        except Exception as exc:
            raise s.ToolError(f"提交失败：{exc}；备份保留在 {bak.name}") from exc
        result["backup"] = bak.name
    else:
        result["unchanged"] = True
    return result


def check_connectivity(s, data, runtime, nets):
    """Check Logisim's wire endpoint/junction rules and named tunnel networks."""
    for circuit in runtime["circuits"]:
        cname = circuit["name"]
        requested = [n for n in nets if n["circuit"] == cname]
        if not requested: continue
        model = s.pick_circuit(data, cname)
        parent = {}
        def root(point):
            parent.setdefault(point, point)
            while parent[point] != point:
                parent[point] = parent[parent[point]]; point = parent[point]
            return point
        def union(p, q): parent[root(p)] = root(q)
        real_ports, tunnel_groups = [], {}
        for comp in circuit["components"]:
            for port in comp["ports"]:
                point = s.xy(port["loc"]); root(point)
                if comp["name"] == "Tunnel":
                    label = comp["attributes"]["label"]
                    if label in tunnel_groups: union(point, tunnel_groups[label])
                    else: tunnel_groups[label] = point
                else:
                    real_ports.append((point, comp["name"], s.norm_xy(comp["loc"]), port["index"]))
        for wire in model["wires"]:
            union(s.xy(wire["from"]), s.xy(wire["to"]))
        # Mid-segment crossings do not join unless a port or wire endpoint is at the crossing.
        points = list(parent)
        for wire in model["wires"]:
            p, q = s.xy(wire["from"]), s.xy(wire["to"])
            for point in points:
                if s.on_segment(point, p, q): union(point, p)
        claimed = {}
        for net in requested:
            endpoints = {s.xy(ep["loc"]) for ep in net["ports"]}
            groups = {root(p) for p in endpoints}
            if len(groups) != 1: raise s.ToolError(f"网络 {net['net']} 未完全连通")
            group = next(iter(groups))
            if group in claimed:
                raise s.ToolError(f"网络 {net['net']} 与 {claimed[group]} 意外短接")
            claimed[group] = net["net"]
            extras = [p for p in real_ports if root(p[0]) == group and p[0] not in endpoints]
            if extras:
                raise s.ToolError(f"网络 {net['net']} 意外连接其他端口 {extras[:5]}；请调整路径或将已有分支全部纳入 net")


def build(s, a):
    path = s.resolve_circ(a["file"], must_exist=False)
    if path.suffix.lower() != ".circ":
        raise s.ToolError("建图工具只允许写入 .circ 文件")
    if not path.parent.is_dir():
        raise s.ToolError("目标父目录不存在；请提供已存在的工程目录")
    before = path.read_bytes() if path.exists() else None
    specs = a["circuits"]
    names = [x["name"] for x in specs]
    if len(names) != len(set(names)):
        raise s.ToolError("批量请求中的电路名重复")
    metadata = probe(s, "catalog", a)
    if not s.supported_source(metadata["source"]):
        raise s.ToolError("当前运行时不是受支持的经典 Logisim/HUST 版本")
    if before is None:
        main = a.get("main", names[0])
        if main not in names:
            raise s.ToolError("main 必须是请求中声明的电路")
        supported_libraries = {x["library"].lstrip("#") for x in metadata["components"]}
        liborder = [name for name in ("Wiring", "Gates", "Plexers", "Arithmetic", "Memory", "I/O", "Base", "TTL") if name in supported_libraries]
        text = empty_project(s, main, names, metadata["source"], liborder)
    else:
        _, text = s._edit_guard({"file": str(path)})
        if text.encode("utf-8") != before:
            raise s.ToolError("读取过程中工程发生变化，请重试")
        if "main" in a and a["main"] != s.parse_project_bytes(before)["main"]:
            raise s.ToolError("追加建图不能改变已有主电路")
        existing_names = s.parse_project_bytes(before)["circuit_names"]
        for name in names:
            if name not in existing_names:
                text = insert_root(s, text, f'  <circuit name="{s.xml_value(name)}"/>' + s.newline_style(text))
    data = s.parse_project_bytes(text.encode("utf-8"))
    expected = data
    catalogs = metadata["components"]
    runtime_ids = {}
    added = {}
    for spec in specs:
        c = s.pick_circuit(expected, spec["name"])
        ids, new = {}, []
        for i, node in enumerate(spec.get("components", [])):
            if node["id"] in ids:
                raise s.ToolError(f"重复元件 id：{node['id']}")
            name = node["name"]
            entry = None
            if "lib" in node:
                lib = node["lib"]
                if lib and lib not in expected["libs"]:
                    raise s.ToolError(f"未声明的库索引 {lib}")
            elif name in expected["circuit_names"] and "library" not in node:
                lib = ""
            else:
                candidates = [x for x in catalogs if x["name"] == name and
                              ("library" not in node or x["library"] == node["library"])]
                entry = s._unique(candidates, f"元件类型 {name}")
                desc = entry["library"]
                matches = [k for k, v in expected["libs"].items() if v == desc]
                if not matches:
                    lib = str(max([int(k) for k in expected["libs"] if k.isdigit()] + [-1]) + 1)
                    text = insert_root(s, text, f'  <lib name="{lib}" desc="{s.xml_value(desc)}"/>' + s.newline_style(text))
                    expected["libs"][lib] = desc
                else:
                    lib = matches[0]
            # Explicit defaults prevent source-version migration from changing geometry
            # (2.7's gate defaults are five inputs; this HUST runtime defaults to two).
            attrs = {k: v for k, v in (entry or {}).get("defaults", {}).items()
                     if v is not None and not k.startswith("negate") and not (k.startswith("bit") and k[3:].isdigit())}
            for key, value in node.get("attrs", {}).items():
                attrs[key] = str(value).lower() if type(value) is bool else str(value)
            if name == "Counter" and not expected["source"].startswith("2.15") and "behavior" not in node.get("attrs", {}):
                attrs["behavior"] = "old"
            loc = s.norm_xy(node.get("loc", f"({160 + (i % 5)*220},{120 + (i // 5)*180})"))
            if any(x["loc"] == loc for x in c["components"] + new):
                raise s.ToolError(f"元件位置 {loc} 已被占用；请指定不同坐标")
            if any(v % 10 for v in s.xy(loc)):
                raise s.ToolError("新增元件坐标必须在 10 像素网格上")
            sub = not lib and name in expected["circuit_names"]
            comp = {"lib": lib, "libdesc": expected["libs"].get(lib, "(子电路引用)"),
                    "name": name, "loc": loc, "attrs": attrs, "is_subcircuit": sub}
            ids[node["id"]] = (name, loc)
            new.append(comp)
        text = append_components(s, text, c["name"], new)
        c["components"].extend(new)
        runtime_ids[c["name"]] = ids
        added[c["name"]] = len(new)
    # Detect recursive hierarchies before asking Logisim to expand appearances.
    graph = {c["name"]: [x["name"] for x in c["components"] if x["is_subcircuit"]] for c in expected["circuits"]}
    visited = set()
    def visit(name, stack):
        if name in stack:
            raise s.ToolError("子电路引用形成递归环：" + " -> ".join(stack + [name]))
        if name in visited: return
        for child in graph[name]: visit(child, stack + [name])
        visited.add(name)
    for name in graph: visit(name, [])
    # Do not let runtime loading or version migration repair malformed requests.
    candidate = s.parse_project_bytes(text.encode("utf-8"))
    for key in ("source", "version", "main", "libs", "circuit_names", "circuits"):
        if candidate[key] != expected[key]:
            raise s.ToolError(f"候选 {key} 与请求不一致；候选未提交")
    problems = s.error_signatures(candidate)
    if before is not None: problems -= s.error_signatures(s.parse_project_bytes(before))
    if problems: raise s.ToolError("候选结构错误：" + "；".join(x[2] for x in problems))
    runtime = probe(s, "inspect", a, text, path.parent)
    runtime_map = {c["name"]: c for c in runtime["circuits"]}
    routed = []
    for spec in specs:
        cname = spec["name"]
        c = s.pick_circuit(expected, cname)
        rc = runtime_map[cname]
        stub_plans = layout.plans(s, rc, a.get("tunnel_offset", 60), a.get("label_spacing", 40)) if a.get("layout", "readable") == "readable" else {}
        ids = runtime_ids[cname]
        used, net_names, new, wires = {}, set(), [], []
        for ni, net in enumerate(spec.get("nets", [])):
            if net["name"] in net_names:
                raise s.ToolError("网络名称重复：" + net["name"])
            net_names.add(net["name"])
            endpoints = []
            for ep in net["endpoints"]:
                if "id" in ep:
                    if ep["id"] not in ids: raise s.ToolError("未知元件 id：" + ep["id"])
                    name, loc = ids[ep["id"]]
                else:
                    name, loc = ep["name"], s.norm_xy(ep["loc"])
                comp = s._unique([x for x in rc["components"] if x["name"] == name and s.xy(x["loc"]) == s.xy(loc)], "端口所属元件")
                port = s._unique([x for x in comp["ports"] if x["index"] == ep["port"]], "端口编号")
                point = s.norm_xy(port["loc"])
                if point in used:
                    raise s.ToolError(f"端口 {point} 被重复连接（{used[point]} / {net['name']}）；一个 net 应包含所有分支")
                used[point] = net["name"]
                endpoints.append({**port, "component": comp["name"], "component_loc": s.norm_xy(comp["loc"])})
            widths = {x["width"] for x in endpoints if x["width"] != 0}
            if len(widths) != 1:
                raise s.ToolError(f"网络 {net['name']} 端口位宽不一致：{sorted(widths)}")
            net_width = next(iter(widths))
            if sum(x["output"] and not x["input"] for x in endpoints) > 1 and not net.get("allow_multiple_drivers", False):
                raise s.ToolError(f"网络 {net['name']} 有多个驱动；三态总线需显式 allow_multiple_drivers=true")
            if "waypoints" in net:
                if len(endpoints) != 2:
                    raise s.ToolError("waypoints 接线只支持两个端口；分支请使用 tunnel 网络")
                points = [s.norm_xy(endpoints[0]["loc"])] + [s.norm_xy(v) for v in net["waypoints"]] + [s.norm_xy(endpoints[1]["loc"])]
                for f, t in zip(points, points[1:]):
                    p, q = s.xy(f), s.xy(t)
                    if p == q: continue
                    if p[0] != q[0] and p[1] != q[1]: raise s.ToolError("waypoints 中有非正交线段")
                    wires.append({"from": f, "to": t})
                routed.append({"circuit": cname, "net": net["name"], "routing": "wire", "ports": endpoints,"allow_multiple_drivers": net.get("allow_multiple_drivers",False)})
            else:
                lib = next((k for k, v in expected["libs"].items() if v in ("#Wiring", "#Base")), None)
                if lib is None: raise s.ToolError("tunnel 接线需要 #Wiring 库")
                base_label = net["name"].strip() or f"net_{ni+1}"
                label, suffix = base_label, 2
                existing_labels = {x["attrs"].get("label") for x in c["components"] + new if x["name"] == "Tunnel"}
                while label in existing_labels:
                    label = f"{base_label}_{suffix}"; suffix += 1
                for port in endpoints:
                    stub = stub_plans.get(s.norm_xy(port["loc"]))
                    if stub:
                        wires.extend({"from": f, "to": t} for f, t in zip(stub["points"], stub["points"][1:]))
                    new.append({"lib": lib, "libdesc": expected["libs"][lib], "name": "Tunnel", "loc": stub["loc"] if stub else s.norm_xy(port["loc"]),
                                "attrs": {"label": label, "width": str(net_width), "facing": stub["facing"] if stub else ("west" if port["output"] else "east")}, "is_subcircuit": False})
                routed.append({"circuit": cname, "net": net["name"], "routing": "tunnel", "tunnel_label": label, "ports": endpoints,"allow_multiple_drivers": net.get("allow_multiple_drivers",False)})
        text = append_components(s, text, cname, new, wires)
        c["components"].extend(new); c["wires"].extend(wires)
    final = probe(s, "inspect", a, text, path.parent)
    old_conflicts = {c["name"]: c["width_conflicts"] for c in runtime["circuits"]}
    if any(c["width_conflicts"] > old_conflicts.get(c["name"], 0) for c in final["circuits"]):
        raise s.ToolError("Logisim 检测到新增连线位宽冲突；候选未提交")
    check_connectivity(s, expected, final, routed)
    result = commit(s, path, before, text, expected, a.get("dry_run", False))
    result = {**result, "added_components": added, "nets": routed, "runtime_checked": True,
              "layout_report": [{"circuit": c["name"], **layout.overlaps(c)} for c in final["circuits"]],
              "connection_manifest": [{"circuit": n["circuit"], "name": n["net"], "allow_multiple_drivers": n["allow_multiple_drivers"], "endpoints": [{"name": p["component"], "loc": p["component_loc"], "port": p["index"]} for p in n["ports"]]} for n in routed],
              "ports": [{"name": c["name"], "components": [x for x in c["components"] if x["name"] != "Tunnel"]} for c in final["circuits"]]}
    if not a.get("include_details", True):
        result.pop("ports", None); result.pop("candidate_xml", None)
    return result


def catalog(s, a):
    result = probe(s, "catalog", a)
    if "name" in a:
        result["components"] = [x for x in result["components"] if x["name"] == a["name"]]
    if "library" in a:
        result["components"] = [x for x in result["components"] if x["library"] == a["library"]]
    result["count"] = len(result["components"])
    return result


def get_ports(s, a):
    d = s.parse_project(s.resolve_circ(a["file"]))
    if not s.supported_source(d["source"]) or d["version"] != "1.0":
        raise s.ToolError("端口查询仅支持经典 Logisim/HUST 工程")
    cname = s.pick_circuit(d, a.get("circuit"))["name"]
    result = next(x for x in probe(s, "inspect", a)["circuits"] if x["name"] == cname)
    if "loc" in a: result["components"] = [x for x in result["components"] if s.xy(x["loc"]) == s.xy(s.norm_xy(a["loc"]))]
    if "name" in a: result["components"] = [x for x in result["components"] if x["name"] == a["name"]]
    return result


def install(s):
    string = {"type": "string", "minLength": 1}
    attrs = {"type": "object", "additionalProperties": {"type": ["string", "integer", "boolean"]}}
    node = {"type": "object", "properties": {"id": string, "name": string, "loc": string,
            "library": string, "lib": {"type": "string"}, "attrs": attrs}, "required": ["id", "name"], "additionalProperties": False}
    endpoint = {"type": "object", "properties": {"id": string, "name": string, "loc": string,
                "port": {"type": "integer", "minimum": 0}}, "required": ["port"],
                "anyOf": [{"required": ["id"]}, {"required": ["name", "loc"]}], "additionalProperties": False}
    net = {"type": "object", "properties": {"name": string, "endpoints": {"type": "array", "items": endpoint, "minItems": 2, "maxItems": 256},
           "waypoints": {"type": "array", "items": string, "maxItems": 1000}, "allow_multiple_drivers": {"type": "boolean"}}, "required": ["name", "endpoints"], "additionalProperties": False}
    circ = {"type": "object", "properties": {"name": string, "components": {"type": "array", "items": node, "maxItems": 2000},
            "nets": {"type": "array", "items": net, "maxItems": 2000}}, "required": ["name"], "additionalProperties": False}
    common = {"file": s.FILE_PROP, "dry_run": {"type": "boolean"}, "exe": string, "java": string,
              "layout": {"type": "string", "enum": ["readable", "compact"], "description": "readable 默认：短导线、密集端口扇出、隧道标签间距；compact 将隧道放在端口。都检查实际网络。"},
              "tunnel_offset": {"type": "integer", "minimum": 40, "maximum": 500},
              "label_spacing": {"type": "integer", "minimum": 20, "maximum": 200},
              "include_details": {"type": "boolean", "description": "默认 true；false 省略候选 XML 和完整端口，保留网络清单与布局摘要。"}}
    def add(name, desc, props, required, impl, write=True):
        s.TOOLS.append({"name": name, "description": desc, "inputSchema": {"type": "object", "properties": props,
                        "required": required, "additionalProperties": False},
                        "annotations": {"readOnlyHint": not write, "destructiveHint": write, "openWorldHint": False}})
        s.TOOL_IMPL[name] = impl
    add("list_component_catalog", "从当前 Logisim 查询所有内建元件的真实名称、所属库和默认属性。属性值必须遵循 Logisim 标准格式。",
        {"name": string, "library": string, "exe": string, "java": string}, [], lambda a: catalog(s, a), False)
    add("get_component_ports", "实际加载工程，返回元件端口 index、坐标、位宽、输入输出方向和 bounds；用于接线，不能凭元件 loc 猜端口。",
        {"file": s.FILE_PROP, "circuit": s.CIRCUIT_PROP, "loc": string, "name": string, "exe": string, "java": string}, ["file"], lambda a: get_ports(s, a), False)
    add("build_project", "一次批量创建完整工程或追加多个电路：components 用 id 标识，nets 通过 id+port（或现有元件 name+loc+port）连接。未指定 loc 时网格摆放。默认用 Tunnel 安全连接多分支；两端 net 可提供正交 waypoints 画线。真实运行时检查属性、端口及位宽，全部成功才提交；新文件不覆盖，旧文件自动备份，dry_run 返回候选 XML。支持同工程子电路和当前运行时的所有内建元件。",
        {**common, "main": string, "circuits": {"type": "array", "items": circ, "minItems": 1, "maxItems": 100}}, ["file", "circuits"], lambda a: build(s, a))
    def one(a):
        cname = a.get("circuit") or (s.parse_project(s.resolve_circ(a["file"]))["main"] if Path(a["file"]).exists() else "main")
        spec = {"name": cname, "components": a.get("components", []), "nets": a.get("nets", [])}
        return build(s, {**{k: v for k, v in a.items() if k in common}, "circuits": [spec]})
    add("build_circuit", "批量搭建一个电路。components/nets 与 build_project 相同；已有电路追加，新文件创建。",
        {**common, "circuit": string, "components": circ["properties"]["components"], "nets": circ["properties"]["nets"]}, ["file", "components"], one)
    add("create_project", "创建带标准内建库的空白经典工程；已有路径拒绝覆盖。可 dry_run。",
        {**common, "main": string}, ["file"], lambda a: create_project(s, a))
    add("add_circuit", "给现有工程添加一个空白子电路；重名拒绝，支持 dry_run。",
        {**common, "name": string}, ["file", "name"], lambda a: add_circuit(s, a))
    add("add_component", "添加任意当前运行时支持的内建/库元件或本工程子电路；attrs 支持标准属性及 ROM contents 文本，查询真实端口后返回。",
        {**common, "circuit": string, "name": string, "loc": string, "library": string, "lib": {"type": "string"}, "attrs": attrs}, ["file", "name", "loc"],
        lambda a: one({**{k: v for k, v in a.items() if k in common or k == "circuit"}, "components": [{"id": "new", **{k: v for k, v in a.items() if k in node["properties"]}}]}))
    add("connect_ports", "按现有元件的 name+loc+port 编号连接网络。默认 Tunnel；正交 waypoints 可画两端导线。位宽冲突和重复端口拒绝提交。",
        {**common, "circuit": string, "nets": circ["properties"]["nets"]}, ["file", "nets"], lambda a: one({**a, "components": []}))
    s.TOOL_SCHEMAS.update({t["name"]: t["inputSchema"] for t in s.TOOLS})


def add_circuit(s, a):
    data = s.parse_project(s.resolve_circ(a["file"]))
    if a["name"] in data["circuit_names"]:
        raise s.ToolError("电路名已存在")
    return build(s, {**{k: v for k, v in a.items() if k != "name"}, "circuits": [{"name": a["name"]}]})


def create_project(s, a):
    if s.resolve_circ(a["file"], must_exist=False).exists():
        raise s.ToolError("目标文件已经存在；create_project 不覆盖已有工程")
    return build(s, {**a, "circuits": [{"name": a.get("main", "main")}]})
