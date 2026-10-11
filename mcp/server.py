#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Logisim Classic Lab MCP — stdio server for classic Logisim projects.

设计目标
--------
只依赖 Python 标准库（Python >= 3.8）。
不需要 pip install、不需要 Node、不需要 WSL/Docker —— 原生 Windows 可用。

能做什么
--------
* 解析经典 Logisim 2.7 / 2.6 的 .circ（XML）：多电路、子电路、库索引映射
* 无界面仿真：包装 `java -jar <logisim-hust>.exe -tty <fmt> <circ>`
  - 强制超时（`-tty` 在没有 halt 引脚时永不退出）
  - 注入 -Dsun.stdout.encoding=UTF-8 解决 Java 默认 GBK 的中文乱码
  - 判定 halted by halt pin / oscillation / timeout
* 结构校验：schema、库索引、坐标、Pin 属性、重复标签；不判几何连通性
* 受保护编辑：文本定位 → 候选字节校验与精确后置条件 → 自动 .bak 备份
  → 原子提交；候选校验失败不会改动原文件。不使用 ElementTree 整体重序列化，避免破坏
  `<project>` 内的裸文本行和原有排版（学生要提交、要能 diff）。

为什么不直接用 ElementTree 写回
------------------------------
真实课程文件（74160.circ）在 `<project>` 里有一行裸文本：
    This file is intended to be loaded by Logisim (http://www.cburch.com/logisim/).
ET 重序列化会丢掉排版、改变属性顺序，虽然 Logisim 多半还能读，
但 diff 会变成整文件重写。因此所有写操作都用精确文本定位。

环境变量
--------
LOGISIM_HUST_EXE        兼容 Logisim exe 完整路径（默认不自动搜索）
LOGISIM_MCP_JAVA        java.exe 完整路径（默认 JAVA_HOME → PATH → 注册表）
LOGISIM_MCP_WORKSPACE   安全围栏：只允许操作该目录下的文件（可选）
LOGISIM_MCP_MAX_TIMEOUT 仿真超时上限秒数（默认 300）

用法
----
  python server.py                 # 启动 stdio MCP 服务器
  python server.py --self-test X.circ   # 离线自检：对本机 .circ 跑一遍全部只读工具
  python server.py --print-config      # 打印可直接粘贴到客户端的配置片段
  python server.py --version
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

SERVER_NAME = "logisim-classic-lab-mcp"
SERVER_VERSION = "1.3.2"
PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18"}

DEFAULT_EXE = ""

TTY_FORMATS = {"table", "speed", "tty", "halt", "stats", "few"}

# 判定用（严格按实测字符串，勿凭记忆改）
RE_HALT_PIN = re.compile(r"halted due to halt pin", re.I)
RE_OSCILLATION = re.compile(r"halted due to detected oscillation", re.I)

RE_XY = re.compile(r"(?:\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)|(-?\d+)\s*,\s*(-?\d+))")
RE_XML_TOKEN = re.compile(
    r"<!--[\s\S]*?-->|<!\[CDATA\[[\s\S]*?\]\]>|<\?[\s\S]*?\?>|"
    r'''<(?:[^<>"']|"[^"]*"|'[^']*')+>'''
)

INSTRUCTIONS = (
    "面向经典 Logisim 2.7（Logisim-HUST / 计组虚拟实验）的 .circ 工具集。"
    "读电路用 describe_circuit / list_pins，验证作业用 validate_circuit，"
    "无界面仿真用 simulate_tty / get_simulation_table；两者只接受 file 并运行文件的 main 电路，不接受 circuit 选择参数。"
    "编辑前请先 validate_circuit；编辑工具校验候选文件后自动备份并原子提交。"
    "没有 halt 引脚时 -tty 可能运行到超时；get_simulation_table 和兼容别名 get_truth_table 都不自动枚举输入。"
    "完整搭建用 build_project/build_circuit，支持元件、子电路、批量网络和 dry_run；"
    "先 list_component_catalog 获取真实名称和属性，get_component_ports 获取端口编号、坐标与说明。"
    "注意：本工具只处理经典 2.3/2.6/2.7 schema，不能处理 Logisim-evolution 4.x 的 .circ。"
)


class ToolError(Exception):
    """工具级错误：以 isError=true 返回给模型，而不是打断 JSON-RPC 会话。"""


# --------------------------------------------------------------------------
# 定位 exe / java
# --------------------------------------------------------------------------

def find_exe(explicit: str | None = None) -> str:
    override = explicit or os.environ.get("LOGISIM_HUST_EXE")
    if override and not Path(override).is_file():
        raise ToolError(f"指定的 Logisim 程序不存在：{override}")
    cands = [explicit, os.environ.get("LOGISIM_HUST_EXE"), DEFAULT_EXE]
    for c in cands:
        if c and Path(c).is_file():
            return str(Path(c).resolve())
    root = Path(os.environ.get("LOGISIM_SEARCH_ROOT", "")) if os.environ.get("LOGISIM_SEARCH_ROOT") else Path("__disabled__")
    if root.is_dir():
        hits = sorted(root.rglob("logisim-hust-*.exe"))
        if hits:
            return str(hits[0].resolve())
    raise ToolError(
        "找不到 logisim-hust-*.exe。请设置环境变量 LOGISIM_HUST_EXE 为完整路径，"
        "或设置 LOGISIM_SEARCH_ROOT 指定搜索目录。"
    )


def _registry_java_homes() -> list[tuple[tuple[int, ...], str]]:
    """从注册表读已安装的 JDK/JRE 主目录（Launch4j 就是这么找的）。"""
    out: list[tuple[tuple[int, ...], str]] = []
    try:
        import winreg  # type: ignore
    except ImportError:
        return out
    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Development Kit"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Runtime Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JRE"),
    )
    for hive, key in keys:
        try:
            with winreg.OpenKey(hive, key) as k:
                n = winreg.QueryInfoKey(k)[0]
                for i in range(n):
                    sub = winreg.EnumKey(k, i)
                    try:
                        with winreg.OpenKey(k, sub) as k2:
                            home, _ = winreg.QueryValueEx(k2, "JavaHome")
                    except OSError:
                        continue
                    ver = tuple(int(x) for x in re.findall(r"\d+", sub)[:3]) or (0,)
                    out.append((ver, str(home)))
        except OSError:
            continue
    return out


def find_java(explicit: str | None = None) -> str:
    override = explicit or os.environ.get("LOGISIM_MCP_JAVA")
    if override and not Path(override).is_file():
        raise ToolError(f"指定的 Java 程序不存在：{override}")
    cands: list[str] = []
    if explicit:
        cands.append(explicit)
    if os.environ.get("LOGISIM_MCP_JAVA"):
        cands.append(os.environ["LOGISIM_MCP_JAVA"])
    if os.environ.get("JAVA_HOME"):
        cands.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / "java.exe"))
    which = shutil.which("java")
    if which:
        cands.append(which)
    for c in cands:
        if c and Path(c).is_file():
            return str(Path(c).resolve())
    homes = sorted(_registry_java_homes(), key=lambda t: t[0], reverse=True)
    for _, home in homes:
        p = Path(home) / "bin" / "java.exe"
        if p.is_file():
            return str(p.resolve())
    raise ToolError(
        "找不到 java.exe。请安装 JDK 8+（本机 JDK 17 可用），"
        "或设置 LOGISIM_MCP_JAVA / JAVA_HOME。"
    )


# --------------------------------------------------------------------------
# 路径安全围栏
# --------------------------------------------------------------------------

def resolve_circ(path: str, must_exist: bool = True) -> Path:
    if not path or not str(path).strip():
        raise ToolError("缺少 file 参数")
    p = Path(str(path)).expanduser()
    ws = os.environ.get("LOGISIM_MCP_WORKSPACE")
    if ws:
        ws_root = Path(ws).expanduser().resolve()
        try:
            p.resolve().relative_to(ws_root)
        except ValueError:
            raise ToolError(f"路径不在允许的工作区内：{ws_root}")
    if must_exist and not p.is_file():
        raise ToolError(f"文件不存在：{p}")
    return p.resolve()


# --------------------------------------------------------------------------
# .circ 解析
# --------------------------------------------------------------------------

def parse_project(path: Path) -> dict:
    return parse_project_bytes(path.read_bytes(), str(path))


def parse_project_bytes(raw: bytes, label: str = "candidate") -> dict:
    # Course files do not need DTDs; reject them rather than expand entities.
    if b"<!DOCTYPE" in raw.upper():
        raise ToolError("不支持带 DTD 的 .circ 文件")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ToolError(f".circ XML 解析失败（{label}）：{exc}")
    if root.tag != "project":
        raise ToolError(f"不是 Logisim 工程文件：根元素是 <{root.tag}>，应为 <project>")

    libs: dict[str, str] = {}
    for lib in root.findall("lib"):
        libs[lib.get("name") or ""] = lib.get("desc") or ""

    main_el = root.find("main")
    main = main_el.get("name") if main_el is not None else None

    circuits = []
    for c in root.findall("circuit"):
        comps = []
        for comp in c.findall("comp"):
            attrs = {}
            for a in comp.findall("a"):
                attrs[a.get("name") or ""] = a.get("val") if "val" in a.attrib else (a.text or "")
            libid = comp.get("lib") or ""
            comps.append({
                "lib": libid,
                "libdesc": libs.get(libid, f"(未声明的库索引 {libid})"),
                "name": comp.get("name") or "",
                "loc": comp.get("loc") or "",
                "attrs": attrs,
            })
        wires = [{"from": w.get("from") or "", "to": w.get("to") or ""}
                 for w in c.findall("wire")]
        circuits.append({"name": c.get("name") or "", "components": comps, "wires": wires})

    # 子电路引用：<comp lib="" name="子电路名"/> —— lib 为空或未声明，name 命中本工程电路名。
    # 实测 circ7400.circ 里有 6 个这样的引用（74x00/74x02/... ），lib="" 是合法写法，
    # 不能当成"悬空库索引"。
    nameset = {c["name"] for c in circuits}
    for c in circuits:
        for comp in c["components"]:
            sub = comp["lib"] == "" and comp["name"] in nameset
            comp["is_subcircuit"] = sub
            if sub and comp["lib"] not in libs:
                comp["libdesc"] = "(子电路引用)"

    return {
        "file": label,
        "source": root.get("source"),
        "version": root.get("version"),
        "libs": libs,
        "main": main,
        "circuits": circuits,
        "circuit_names": [c["name"] for c in circuits],
    }


def pick_circuit(data: dict, name: str | None) -> dict:
    target = name or data.get("main")
    if not target:
        raise ToolError(
            "未指定 circuit，且文件里没有 <main>。可用电路："
            + ", ".join(data["circuit_names"])
        )
    matches = [c for c in data["circuits"] if c["name"] == target]
    if len(matches) > 1:
        raise ToolError(f"电路名 {target!r} 不唯一，无法安全定位")
    if matches:
        return matches[0]
    raise ToolError(
        f"找不到电路 {target!r}。可用：{', '.join(data['circuit_names'])}"
    )


def pin_info(comp: dict) -> dict:
    a = comp.get("attrs") or {}
    is_out = str(a.get("output", "false")).lower() == "true"
    try:
        width = int(str(a.get("width", "1")))
    except ValueError:
        width = 1
    return {
        "loc": comp["loc"],
        "label": a.get("label") or "",
        "direction": "out" if is_out else "in",
        "width": width,
        "width_declared": "width" in a,
        "facing": a.get("facing") or "",
    }


def xy(s: str) -> tuple[int, int] | None:
    m = RE_XY.fullmatch(str(s or "").strip())
    if not m:
        return None
    x, y = m.group(1, 2) if m.group(1) is not None else m.group(3, 4)
    return int(x), int(y)


def norm_xy(s: str) -> str:
    p = xy(s)
    if p is None:
        raise ToolError(f'坐标格式不对：{s!r}，应为 "(330,530)" 或 "330,530"')
    return f"({p[0]},{p[1]})"


def on_segment(p: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> bool:
    """点是否落在线段上（只考虑水平/垂直，Logisim 导线只允许正交）。"""
    if a[0] == b[0] == p[0]:
        return min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    if a[1] == b[1] == p[1]:
        return min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
    return False


# --------------------------------------------------------------------------
# 文本级定位（编辑用）
# --------------------------------------------------------------------------

def element_spans(text: str, wanted: str) -> list[dict]:
    """Locate real XML elements without reserializing or matching comments/CDATA.

    Callers first parse the complete document with ElementTree. Tokenization
    then preserves character offsets, quote style and attribute ordering.
    """
    stack, found = [], []
    for match in RE_XML_TOKEN.finditer(text):
        tag = match.group(0)
        if tag.startswith(("<!", "<?")):
            continue
        if tag.startswith("</"):
            item = stack.pop()
            if item["name"] == wanted:
                item.update(end=match.end(), close_start=match.start())
                found.append(item)
            continue
        selfclose = tag.rstrip().endswith("/>")
        empty_tag = tag if selfclose else tag[:-1] + "/>"
        node = ET.fromstring(empty_tag)
        item = {"name": node.tag, "attrs": dict(node.attrib),
                "start": match.start(), "open_end": match.end(),
                "tag": tag, "selfclose": selfclose,
                "parent": stack[-1]["name"] if stack else None}
        if selfclose:
            item.update(end=match.end(), close_start=match.start())
            if node.tag == wanted:
                found.append(item)
        else:
            stack.append(item)
    return sorted(found, key=lambda item: item["start"])


def circuit_span(text: str, name: str) -> tuple[int, int] | None:
    matches = [x for x in element_spans(text, "circuit")
               if x["attrs"].get("name") == name and x["parent"] == "project"]
    if len(matches) != 1:
        return None
    return matches[0]["start"], matches[0]["end"]


def find_comp_spans(region: str) -> list[dict]:
    return [x for x in element_spans(region, "comp") if x["parent"] == "circuit"]


def detect_indent(region: str) -> str:
    m = re.search(r"\n([ \t]*)<comp\b", region)
    if m:
        return m.group(1)
    m = re.search(r"\n([ \t]*)<wire\b", region)
    return m.group(1) if m else "    "


# --------------------------------------------------------------------------
# 备份 / 校验 / 回滚
# --------------------------------------------------------------------------

def make_backup(path: Path, kind: str = "bak", raw: bytes | None = None) -> Path:
    """kind='bak' 是编辑前快照；kind='prerestore' 是恢复前的安全快照。
    两者分开命名，避免 'latest' 指向刚刚自动产生的那种快照而反复震荡。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    bak = path.with_name(f"{path.name}.{kind}-{stamp}")
    n = 1
    content = path.read_bytes() if raw is None else raw
    while True:
        try:
            with bak.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            break
        except FileExistsError:
            bak = path.with_name(f"{path.name}.{kind}-{stamp}-{n}")
            n += 1
    return bak


def list_backups(path: Path) -> list[dict]:
    """全部备份，新的在前。每项带 kind（bak=编辑前快照 / prerestore=恢复前快照）。"""
    out: list[dict] = []
    for kind in ("bak", "prerestore"):
        # Literal prefix, not a glob: filenames may contain [] characters.
        for b in path.parent.iterdir():
            if b.name.startswith(f"{path.name}.{kind}-") and b.is_file() and not b.is_symlink():
                suffix = b.name[len(f"{path.name}.{kind}-"):]
                m = re.fullmatch(r"(\d{8}-\d{6})(?:-(\d+))?(?:-(\d+))?", suffix)
                if not m:
                    continue
                # Old names use a numeric collision suffix; new names have
                # a six-digit microsecond field followed by an optional suffix.
                first = m.group(2) or ""
                micro = int(first) if len(first) == 6 else 0
                collision = int(m.group(3) or 0) if len(first) == 6 else int(first or 0)
                out.append({"path": b, "kind": kind,
                            "created_key": (m.group(1), micro, collision)})
    out.sort(key=lambda x: x["created_key"], reverse=True)
    return out


def latest_edit_backup(path: Path) -> Path | None:
    """最新的"编辑前快照"（kind=bak），供 latest 使用。"""
    cands = [b["path"] for b in list_backups(path) if b["kind"] == "bak"]
    return cands[0] if cands else None


def atomic_replace(path: Path, raw: bytes, expected: bytes) -> None:
    """Prepare a same-directory file, detect stale input, then replace once."""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.mcp-", suffix=".tmp", dir=path.parent)
    tmp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(path, tmp)
        if path.read_bytes() != expected:
            raise ToolError("文件已被其他程序修改，本次提交取消；请重新读取电路")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def error_signatures(data: dict) -> Counter:
    return Counter((c["name"], f["code"], f["message"])
                   for c in data["circuits"] for f in validate(data, c)["findings"]
                   if f["severity"] == "error")


def write_verified(path: Path, new_text: str, expect: dict,
                   original_text: str | None = None, dry_run: bool = False) -> dict:
    """Validate bytes and exact postconditions before touching the original."""
    original = path.read_bytes() if original_text is None else original_text.encode("utf-8")
    raw = new_text.encode("utf-8")
    before = parse_project_bytes(original, str(path))
    data = parse_project_bytes(raw, str(path))
    problems = []
    for key in ("source", "version", "main", "libs", "circuit_names"):
        if before[key] != data[key]:
            problems.append(f"工程属性 {key} 意外变化")
    target = expect["circuit"]
    c = pick_circuit(data, target)
    for old, new in zip(before["circuits"], data["circuits"]):
        if old["name"] != target and old != new:
            problems.append(f"非目标电路 {old['name']!r} 意外变化")
    for key in ("components", "wires"):
        if key in expect and c[key] != expect[key]:
            problems.append(f"{key} 内容与请求的精确修改不一致")
    added_errors = error_signatures(data) - error_signatures(before)
    if added_errors:
        problems.extend(item[2] for item in added_errors)
    if problems:
        raise ToolError("候选文件校验失败，原文件未改动：" + "；".join(problems))
    info = {"bytes_before": len(original), "bytes_after": len(raw),
            "sha256_before": hashlib.sha256(original).hexdigest(),
            "sha256_after": hashlib.sha256(raw).hexdigest(),
            "validation": validate(data, c)}
    if dry_run:
        return {"dry_run": True, **info}
    if path.read_bytes() != original:
        raise ToolError("文件已被其他程序修改，本次提交取消；请重新读取电路")
    if raw == original:
        return {"unchanged": True, **info}
    bak = make_backup(path, raw=original)
    try:
        atomic_replace(path, raw, original)
    except Exception as exc:
        raise ToolError(f"提交失败：{exc}；备份保留在 {bak.name}") from exc
    return {"backup": bak.name, **info}


# --------------------------------------------------------------------------
# 仿真
# --------------------------------------------------------------------------

def run_tty(circ: Path, fmt: str, timeout_sec: int = 30,
            load_image: str | None = None,
            exe: str | None = None, java: str | None = None) -> dict:
    if not isinstance(fmt, str):
        raise ToolError("format 必须为逗号分隔的字符串，例如 table,halt")
    project = parse_project(circ)
    if not supported_source(project["source"]) or project["version"] != "1.0":
        raise ToolError("仿真只支持经典 2.3/2.6/2.7 和 HUST 2.15 的 version=1.0 工程")
    fmt = fmt.strip()
    parts = [p.strip() for p in fmt.split(",") if p.strip()]
    if not parts:
        raise ToolError("-tty 格式不能为空，至少给一个：halt, speed, stats, table, tty, few")
    bad = [p for p in parts if p not in TTY_FORMATS]
    if bad:
        raise ToolError(f"不支持的 -tty 格式：{bad}；可用：{sorted(TTY_FORMATS)}")
    if not set(parts) - {"few"}:
        raise ToolError("few 是修饰项，必须同时包含 table/halt/speed/stats/tty 之一")

    try:
        cap = int(os.environ.get("LOGISIM_MCP_MAX_TIMEOUT", "300"))
        output_cap = int(os.environ.get("LOGISIM_MCP_MAX_OUTPUT_BYTES", "4194304"))
    except ValueError as exc:
        raise ToolError("超时/输出上限环境变量必须为正整数") from exc
    if cap <= 0 or output_cap <= 0 or type(timeout_sec) is not int or timeout_sec <= 0:
        raise ToolError("超时和输出上限必须为正整数")
    timeout_sec = min(timeout_sec, cap)

    exe_path = find_exe(exe)
    java_path = find_java(java)

    args = [
        java_path,
        "-Dsun.stdout.encoding=UTF-8",
        "-Dsun.stderr.encoding=UTF-8",
        "-jar", exe_path,
        "-tty", ",".join(parts),
    ]
    if load_image:
        image_path = resolve_circ(load_image)
        args += ["-load", str(image_path)]
    args.append(str(circ.resolve()))

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    # 关键：输出重定向到临时文件而不是管道。
    # 超时被杀时管道里未 flush 的缓冲会丢，文件方式能保住部分输出。
    with tempfile.TemporaryDirectory(prefix="logisim-mcp-") as td:
        so, se = Path(td) / "out.txt", Path(td) / "err.txt"
        t0 = time.perf_counter()
        timed_out = False
        output_limited = False
        code: int | None = None
        with open(so, "wb") as fso, open(se, "wb") as fse:
            proc = subprocess.Popen(args, stdout=fso, stderr=fse, creationflags=creationflags)
            deadline = t0 + timeout_sec
            while proc.poll() is None:
                output_limited = so.stat().st_size + se.stat().st_size > output_cap
                timed_out = time.perf_counter() >= deadline
                if output_limited or timed_out:
                    break
                try:
                    code = proc.wait(timeout=min(0.1, max(0.001, deadline - time.perf_counter())))
                except subprocess.TimeoutExpired:
                    continue
            if output_limited or timed_out:
                proc.kill()
                try:
                    code = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    raise ToolError("仿真进程未能在 kill 后退出")
            else:
                code = proc.returncode
        duration = round(time.perf_counter() - t0, 3)
        stdout_truncated = so.stat().st_size > output_cap
        stderr_truncated = se.stat().st_size > output_cap
        with so.open("rb") as stream:
            out = stream.read(output_cap).decode("utf-8", "replace")
        with se.open("rb") as stream:
            err = stream.read(output_cap).decode("utf-8", "replace")
        output_limited = output_limited or stdout_truncated or stderr_truncated

    if output_limited:
        verdict, hint = "output limit", f"输出超过 {output_cap} 字节，已结束仿真；结果可能不完整。"
    elif timed_out:
        verdict, hint = "timeout", (
            f"{timeout_sec}s 内未结束：可能缺少 halt Pin、值未变为 1，或文件/库无法加载。"
            "注意：只有信号变化时才追加输出行，"
            "行数少不代表被截断。"
        )
    elif RE_OSCILLATION.search(out):
        verdict, hint = "halted by oscillation", "检测到震荡，检查组合环 / 竞争。"
    elif code not in (0, None):
        verdict, hint = "error", f"仿真进程异常退出（code={code}），请检查 stderr。"
    elif RE_HALT_PIN.search(out):
        verdict, hint = "halted by halt pin", "halt 引脚触发停机；输出正确性需另与预期对照。"
    else:
        verdict, hint = "exited", f"进程退出（code={code}）；未观察到停机原因，输出需与预期对照。"

    return {
        "circuit_file": str(circ.resolve()),
        "format": ",".join(parts),
        "verdict": verdict,
        "hint": hint,
        "timed_out": timed_out,
        "process_ok": code == 0 and not timed_out and not output_limited,
        "output_limit_reached": output_limited,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "exit_code": code,
        "duration_sec": duration,
        "stdout": out,
        "stderr": err,
        "exe": exe_path,
        "java": java_path,
        "timeout_sec": timeout_sec,
    }


def probe_version(exe: str | None = None, java: str | None = None) -> dict:
    exe_path = find_exe(exe)
    java_path = find_java(java)
    args = [java_path, "-Dsun.stdout.encoding=UTF-8", "-jar", exe_path, "-version"]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        p = subprocess.run(args, capture_output=True, timeout=30, creationflags=creationflags)
        out = p.stdout.decode("utf-8", "replace").strip()
        err = p.stderr.decode("utf-8", "replace").strip()
        code = p.returncode
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "-version 超时（30s）"}
    # 注意：Launch4j 包装的 -version 退出码是 -1，不代表失败。
    # Python 在 Windows 上把 -1 报成 -1，但某些路径下会变成 4294967295，两种都识别。
    unsigned = code & 0xFFFFFFFF if isinstance(code, int) else None
    is_minus_one = code == -1 or unsigned == 0xFFFFFFFF
    return {
        "ok": bool(out),
        "raw": out or err,
        "exit_code": code,
        "exit_code_note": (
            "退出码 -1（可能显示为 4294967295）是本程序 -version 的正常表现，不是错误"
            if is_minus_one else ""
        ),
    }


# --------------------------------------------------------------------------
# 工具实现
# --------------------------------------------------------------------------

def tool_env_info(a: dict) -> dict:
    info = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "server_version": SERVER_VERSION,
        "workspace_fence": os.environ.get("LOGISIM_MCP_WORKSPACE") or None,
    }
    try:
        info["exe"] = find_exe(a.get("exe"))
        info["exe_exists"] = True
    except ToolError as exc:
        info["exe"] = None
        info["exe_exists"] = False
        info["exe_error"] = str(exc)
    try:
        info["java"] = find_java(a.get("java"))
    except ToolError as exc:
        info["java"] = None
        info["java_error"] = str(exc)
    if a.get("probe_version"):
        try:
            info["probe"] = probe_version(a.get("exe"), a.get("java"))
        except ToolError as exc:
            info["probe"] = {"ok": False, "error": str(exc)}
    return info


def tool_list_circuits(a: dict) -> dict:
    p = resolve_circ(a["file"])
    d = parse_project(p)
    return {
        "file": d["file"],
        "schema_source": d["source"],
        "schema_version": d["version"],
        "main": d["main"],
        "library_index": d["libs"],
        "circuit_count": len(d["circuits"]),
        "circuits": [
            {"name": c["name"], "components": len(c["components"]), "wires": len(c["wires"]),
             "is_main": c["name"] == d["main"]}
            for c in d["circuits"]
        ],
    }


def tool_describe_circuit(a: dict) -> dict:
    p = resolve_circ(a["file"])
    d = parse_project(p)
    c = pick_circuit(d, a.get("circuit"))
    comps = c["components"]
    pins = [pin_info(x) for x in comps if x["name"] == "Pin"]
    names = set(d["circuit_names"])
    subs = sorted({x["name"] for x in comps if x["name"] in names})
    hist = Counter(f'{x["name"]} [{x["libdesc"]}]' for x in comps)

    result: dict = {
        "file": d["file"],
        "schema_source": d["source"],
        "main": d["main"],
        "circuit": c["name"],
        "is_main": c["name"] == d["main"],
        "component_count": len(comps),
        "wire_count": len(c["wires"]),
        "pins": pins,
        "pin_count": len(pins),
        "has_halt_pin": any(x["label"] == "halt" for x in pins),
        "component_histogram": dict(sorted(hist.items())),
        "subcircuit_refs": subs,
        "subcircuit_ref_count": len(subs),
        "has_tty_component": any(x["name"] in {"Tty", "Keyboard"} for x in comps),
    }
    if a.get("include_components"):
        result["components"] = [
            {"name": x["name"], "lib": x["lib"], "libdesc": x["libdesc"],
             "loc": x["loc"], "is_subcircuit": x.get("is_subcircuit", False),
             "attrs": x["attrs"]}
            for x in comps
        ]
    if a.get("include_wires"):
        result["wires"] = c["wires"]
    return result


def tool_list_pins(a: dict) -> dict:
    p = resolve_circ(a["file"])
    d = parse_project(p)
    c = pick_circuit(d, a.get("circuit"))
    pins = [pin_info(x) for x in c["components"] if x["name"] == "Pin"]
    pins.sort(key=lambda x: (x["direction"], x["label"] or "~", x["loc"]))
    return {
        "circuit": c["name"],
        "pin_count": len(pins),
        "input_count": sum(1 for x in pins if x["direction"] == "in"),
        "output_count": sum(1 for x in pins if x["direction"] == "out"),
        "has_halt_pin": any(x["label"] == "halt" for x in pins),
        "note": (
            "width 若 width_declared=false，说明文件里没写 <a name=\"width\">，"
            "显示的是 Logisim 默认值 1。表头名不等于引脚标签：-tty 会去掉前导 '!' "
            "并在重名时加数字后缀，要标签请看这里。"
        ),
        "pins": pins,
    }


def tool_count_components(a: dict) -> dict:
    p = resolve_circ(a["file"])
    d = parse_project(p)
    if a.get("all") or not (a.get("circuit") or d.get("main")):
        targets = d["circuits"]
    else:
        targets = [pick_circuit(d, a.get("circuit"))]
    per = {}
    for c in targets:
        hist = Counter(f'{x["name"]} [{x["libdesc"]}]' for x in c["components"])
        per[c["name"]] = {"components": len(c["components"]), "wires": len(c["wires"]),
                          "histogram": dict(sorted(hist.items()))}
    return {"file": d["file"], "circuits": per}


def tool_find_components(a: dict) -> dict:
    query = (a.get("query") or "").strip()
    if not query:
        raise ToolError("query 不能为空")
    p = resolve_circ(a["file"])
    d = parse_project(p)
    limit = int(a.get("limit") or 50)
    q = query.lower()
    scope = d["circuits"] if a.get("all") else [pick_circuit(d, a.get("circuit"))]
    hits = []
    for c in scope:
        for x in c["components"]:
            blob = f'{x["name"]} {x["libdesc"]} {x["loc"]} ' + " ".join(
                f"{k}={v}" for k, v in x["attrs"].items()
            )
            if q in blob.lower():
                hits.append({"circuit": c["name"], "name": x["name"],
                             "libdesc": x["libdesc"], "loc": x["loc"], "attrs": x["attrs"]})
                if len(hits) >= limit:
                    return {"query": query, "truncated": True, "count": len(hits), "matches": hits}
    return {"query": query, "truncated": False, "count": len(hits), "matches": hits}


def tool_get_circuit_xml(a: dict) -> dict:
    p = resolve_circ(a["file"])
    text = p.read_bytes().decode("utf-8")
    d = parse_project(p)
    name = a.get("circuit") or d.get("main")
    if not name:
        raise ToolError("需要 circuit 参数（文件里没有 <main>）")
    span = circuit_span(text, name)
    if span is None:
        raise ToolError(f"找不到电路 {name!r} 的 XML 区间")
    start, end = span
    body = text[start:end]
    off = int(a.get("offset") or 0)
    maxc = int(a.get("max_chars") or 8000)
    chunk = body[off:off + maxc]
    return {
        "circuit": name,
        "total_chars": len(body),
        "offset": off,
        "returned_chars": len(chunk),
        "has_more": off + len(chunk) < len(body),
        "xml": chunk,
    }


def tool_list_library_index(a: dict) -> dict:
    p = resolve_circ(a["file"])
    d = parse_project(p)
    return {
        "file": d["file"],
        "schema_source": d["source"],
        "library_index": d["libs"],
        "warning": (
            "库索引不固定：2.7.1 里 Pin 属于 #Wiring，2.6.2 里 Pin 属于 #Base。"
            "不要背索引，按映射读。"
        ),
    }


def supported_source(source: str | None) -> bool:
    return bool(re.fullmatch(r"2\.(?:3|6|7|15)(?:\.\d+)*", source or ""))


def validate(data: dict, circuit: dict) -> dict:
    findings = []
    libs = data["libs"]
    names = set(data["circuit_names"])

    def add(sev: str, code: str, msg: str, **extra):
        findings.append({"severity": sev, "code": code, "message": msg, **extra})

    if not data.get("source"):
        add("error", "no_schema_source", "<project> 缺少 source 属性，不是经典 Logisim 文件")
    elif not supported_source(data["source"]):
        add("error", "unsupported_schema_source",
            f"未支持的 project source={data['source']!r}；本服务编辑/仿真仅支持经典 2.3/2.6/2.7 和 HUST 2.15")
    if data.get("version") != "1.0":
        add("error", "unsupported_schema_version", f"未支持的 project version={data.get('version')!r}")
    if len(names) != len(data["circuit_names"]) or "" in names:
        add("error", "invalid_circuit_names", "电路名必须非空且唯一")

    if data.get("main") is None:
        add("warning", "no_main",
            "文件里没有 <main>，Logisim 打开时不知道该显示哪个电路；提交通常需要 main")
    elif data["main"] not in names:
        add("error", "main_missing", f"<main name=\"{data['main']}\"> 指向的电路不存在")

    comps, wires = circuit["components"], circuit["wires"]

    used_libs = {c["lib"] for c in comps}
    for libid in sorted(used_libs):
        if libid in libs:
            continue
        bad = sorted({c["name"] for c in comps
                      if c["lib"] == libid and not c.get("is_subcircuit")})
        if bad:
            add("error", "dangling_lib_index",
                f'<comp lib="{libid}"> 引用了未声明的库索引（元件：{", ".join(bad)}）')

    comp_locs: dict[tuple[int, int], list[str]] = {}
    for c in comps:
        pt = xy(c["loc"])
        if pt is None:
            add("error", "bad_loc", f'元件 {c["name"]} 的 loc 无法解析：{c["loc"]!r}')
            continue
        comp_locs.setdefault(pt, []).append(c["name"])
        if c["name"] == "Pin" and not c.get("is_subcircuit"):
            attrs = c["attrs"]
            try:
                width = int(str(attrs.get("width", "1")))
            except (ValueError, TypeError):
                width = 0
            if not 1 <= width <= 32:
                add("error", "invalid_pin_width", f"Pin {c['loc']} 的位宽必须为 1..32")
            if attrs.get("facing", "east") not in {"east", "west", "north", "south"}:
                add("error", "invalid_pin_facing", f"Pin {c['loc']} 的 facing 无效：{attrs.get('facing')!r}")
            if attrs.get("output", "false") not in {"true", "false"}:
                add("error", "invalid_pin_direction", f"Pin {c['loc']} 的 output 必须为 true/false")

    pins = [pin_info(c) for c in comps if c["name"] == "Pin"]
    labels = [x["label"] for x in pins if x["label"]]
    dupes = [l for l, n in Counter(labels).items() if n > 1]
    if dupes:
        add("warning", "duplicate_pin_labels",
            f"引脚标签重复：{sorted(dupes)}；-tty 值表会加数字后缀，容易看错列")

    if not any(x["label"] == "halt" for x in pins):
        add("warning", "no_halt_pin",
            '没有标签为 "halt" 的 Pin：通常需要超时结束 -tty。'
            "测试电路可把实际停止信号接到 halt 引脚；只添加标签不能保证停机。")

    if not any(x["name"] in {"Tty", "Keyboard"} for x in comps):
        add("info", "no_tty_component",
            "-tty 的 tty 格式需要 Tty 或 Keyboard 元件，否则报 ttyNoTtyError。"
            "使用 table/halt/stats 格式则不需要。")

    # 结构检查：坐标可解析、非零长、正交、重复、同坐标同名元件。
    #
    # Port offsets depend on component attributes; loc alone cannot prove connectivity.
    seen_wires: set[tuple[str, str]] = set()
    for w in wires:
        a_, b_ = xy(w["from"]), xy(w["to"])
        if a_ is None or b_ is None:
            add("error", "bad_wire", f'导线端点无法解析：from={w["from"]!r} to={w["to"]!r}')
            continue
        if a_ == b_:
            add("error", "zero_length_wire", f'导线两端相同：{w["from"]}')
        elif a_[0] != b_[0] and a_[1] != b_[1]:
            add("info", "non_orthogonal_wire",
                f'导线两端既不同 x 也不同 y：{w["from"]} -> {w["to"]}。'
                "建议检查坐标并改用正交导线；本服务不据此判断是否导通或会否卡死")
        key = tuple(sorted([w["from"], w["to"]]))
        if key in seen_wires:
            add("info", "duplicate_wire", f'重复导线：{w["from"]} -> {w["to"]}')
        seen_wires.add(key)

    # 同一坐标出现"不同"元件是合法的：loc 只是包围盒锚点，不同元件的包围盒可以锚在同一点，
    # 端口各自偏移。实测 74160 官方电路里 (470,340) 同时有 Buffer 和 Splitter，电路正常工作。
    # 因此只有"同名元件叠在同一坐标"才提醒（通常是重复粘贴）。
    for pt, names_here in comp_locs.items():
        dup_names = [n for n, k in Counter(names_here).items() if k > 1]
        if dup_names:
            add("info", "duplicate_component_loc",
                f"同一坐标 {pt} 上有多个同名元件：{dup_names}（该处全部元件：{names_here}）—— 可能是重复粘贴")

    # 几何连通性：刻意不做校验。
    #
    # 这不是偷懒，是两次实证失败的结果：
    #   判据一「导线端点必须落在元件 loc 上」→ 在官方 74160 误报 21 个、74163 误报 79 个"悬空"。
    #   判据二「导线网里至少有一条线段覆盖某个 loc」→ 在 74193/74385/74670/7474/7476 等
    #          官方电路上仍报出悬空网络（例如 74160 一张 3 线网在 (440,350)，而 Counter 的
    #          loc 是 (440,340)，端口在 loc+(0,10)）。
    #   根因：loc 只是包围盒锚点，**每种元件的端口偏移各不相同**。用 10 个 Pin 做的控制实验
    #   得到"端口 = loc"，但那只对 Pin 成立（Pin 单端口且恰好落在 loc）；Counter/Gate/Splitter
    #   等多引脚元件的端口在 loc 的偏移处（实测 Counter 有 (0,10)、(-30,0)、(10,0) 等）。
    #   没有逐元件端口偏移表，就无法可靠判定连通性 —— 而官方电路被误报是最坏的结果。
    # 因此使用仿真值并对照预期验证连通和功能；E 可能有多种原因。
    add("info", "geometry_not_checked",
        "本工具不做几何连通性校验：实测元件 loc 只是包围盒锚点，各类型元件的端口偏移不同"
        "（Pin 的端口恰在 loc，Counter 等有 (0,10)、(-30,0) 等偏移），任何基于 loc 坐标的"
        "连通判据都会在官方课程电路上误报。判断连线是否有效请用 simulate_tty / "
        "get_simulation_table 检查引脚值，并与预期输出对照；E 也可能由宽度或驱动冲突造成。")

    subs = sorted({c["name"] for c in comps if c["name"] in names})
    return {
        "circuit": circuit["name"],
        "components": len(comps),
        "wires": len(wires),
        "pins": len(pins),
        "subcircuit_refs": subs,
        "error_count": sum(1 for f in findings if f["severity"] == "error"),
        "warning_count": sum(1 for f in findings if f["severity"] == "warning"),
        "info_count": sum(1 for f in findings if f["severity"] == "info"),
        "ok": not any(f["severity"] == "error" for f in findings),
        "findings": findings,
    }


def tool_validate_circuit(a: dict) -> dict:
    p = resolve_circ(a["file"])
    d = parse_project(p)
    if a.get("all"):
        if not d["circuits"]:
            raise ToolError("工程没有任何电路")
        results = [validate(d, c) for c in d["circuits"]]
        if a.get("runtime"):
            connection = _connections.check(_ServerAPI(), a)
            for result in results:
                _merge_connection_findings(result, next(r for r in connection["results"] if r["circuit"] == result["circuit"]))
        return {"file": d["file"], "schema_source": d["source"],
                "ok": all(r["ok"] for r in results),
                "error_count": sum(r["error_count"] for r in results),
                "warning_count": sum(r["warning_count"] for r in results),
                "results": results}
    c = pick_circuit(d, a.get("circuit"))
    r = validate(d, c)
    if a.get("runtime"):
        _merge_connection_findings(r, _connections.check(_ServerAPI(), a)["results"][0])
    r["file"] = d["file"]
    r["schema_source"] = d["source"]
    r["main"] = d["main"]
    r["note"] = ('rows 末尾的 "Error！" 不能用来判断震荡或未稳定（实测在最小确定电路上也会出现）；'
                 '判震荡只看 verdict=halted by oscillation。')
    return r


def _merge_connection_findings(result, connection):
    result["findings"] = [f for f in result["findings"] if f["code"] != "geometry_not_checked"] + connection["findings"]
    result.update(runtime_checked=True, network_count=connection["network_count"])
    for severity in ("error", "warning", "info"):
        result[severity + "_count"] = sum(f["severity"] == severity for f in result["findings"])
    result["ok"] = result["error_count"] == 0


def tool_simulate_tty(a: dict) -> dict:
    p = resolve_circ(a["file"])
    r = run_tty(p, a.get("format") or "table,halt,stats",
                int(a.get("timeout_sec") or 30), a.get("load_image"),
                a.get("exe"), a.get("java"))
    if not a.get("include_output"):
        r.pop("stdout", None)
        if not r["process_ok"] and r["stderr"]:
            r["stderr"] = r["stderr"][:2000]
        else:
            r.pop("stderr", None)
    return r


def parse_tty_table(raw: str, column_widths: list[int] | None = None) -> dict:
    header, rows, diagnostics, warnings = [], [], [], []
    legacy_count, legacy_first, legacy_last = 0, None, None
    for number, original in enumerate(raw.splitlines(), 1):
        line = RE_HALT_PIN.sub("", original)
        line = RE_OSCILLATION.sub("", line).rstrip()
        # HUST may append this marker and the halt message to the value row.
        tail = re.search(r"(?:^|\s)Error[！!]", line)
        if tail:
            suffix = line[tail.start():].strip()
            if re.fullmatch(r"Error[！!]", suffix):
                legacy_count += 1; legacy_first = legacy_first or number; legacy_last = number
            else:
                diagnostics.append({"line": number, "text": suffix})
            line = line[:tail.start()].rstrip()
        if not line:
            continue
        if not header and column_widths:
            tokens, offset = [], 0
            for width in column_widths:
                tokens.append(line[offset:offset + width].strip())
                offset += width
        else:
            tokens = [part.strip() for part in line.split("\t")] if "\t" in line else re.split(r" {2,}", line.strip())
        if not header:
            header = tokens
            continue
        if len(tokens) != len(header):
            warnings.append({"line": number, "text": original, "reason": "列数与表头不一致"})
            continue
        rows.append(tokens)
    return {"header": header, "rows": rows, "row_count": len(rows),
            "diagnostics": diagnostics, "parse_warnings": warnings,
            "unparsed_trailing_tokens": [d["text"] for d in diagnostics],
            "legacy_marker": {"count": legacy_count, "first_line": legacy_first, "last_line": legacy_last,
                              "note": "HUST 行尾 Error！标记单独汇总；不等于信号值 E，也不证明仿真正确。"}}


def tool_get_simulation_table(a: dict) -> dict:
    p = resolve_circ(a["file"])
    r = run_tty(p, "table,halt", int(a.get("timeout_sec") or 30), None, a.get("exe"), a.get("java"))
    raw = r["stdout"]
    table = parse_tty_table(raw)
    table_metadata = {}
    if table["parse_warnings"]:
        # HUST concatenates fixed-width header fields without delimiters, so labels
        # can touch. Only split using verified runtime metadata and exact header text.
        try:
            project = parse_project(p)
            cname = pick_circuit(project, None)["name"]
            runtime = _builder.probe(_ServerAPI(), "inspect", a)
            columns = next(c["tty_columns"] for c in runtime["circuits"] if c["name"] == cname)
            expected_header = "".join(c["header_field"] for c in columns).strip()
            actual_header = next((line.strip() for line in raw.splitlines() if line.strip()), "")
            if columns and actual_header == expected_header:
                table = parse_tty_table(raw, [c["field_width"] for c in columns])
                table_metadata = {"column_format": "hust_fixed_header", "value_radix": 16, "pin_columns": columns}
        except ToolError:
            pass  # Preserve explicit parse warnings instead of inventing columns.
    return {
        "circuit_file": str(p.resolve()),
        "verdict": r["verdict"],
        "timed_out": r["timed_out"],
        "duration_sec": r["duration_sec"],
        "exit_code": r["exit_code"],
        "process_ok": r["process_ok"],
        "stderr": r["stderr"],
        "table_kind": "output_changes",
        "inputs_enumerated": False,
        "complete": (r["process_ok"] and r["verdict"] != "halted by oscillation"
                     and not r["stdout_truncated"] and not table["parse_warnings"]),
        "header_note": (
            "表头只列主电路的输出引脚，且不是原标签：前导 '!' 会被去掉，"
            "重名时按顺序加数字后缀（Q 与 !Q -> Q / Q2）。"
            "不要用表头反推引脚标签，要标签用 list_pins。"
        ),
        **table,
        **table_metadata,
        "raw_output": raw,
    }


def tool_get_truth_table(a: dict) -> dict:
    result = tool_get_simulation_table(a)
    result["compatibility_note"] = "get_truth_table 是 get_simulation_table 的兼容别名；不自动枚举输入，不保证真值表覆盖率。"
    return result


# ---- 编辑类工具 -----------------------------------------------------------

def _edit_guard(a: dict) -> tuple[Path, str]:
    p = resolve_circ(a["file"])
    if p.suffix.lower() != ".circ":
        raise ToolError("编辑工具只允许操作 .circ 文件")
    try:
        text = p.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("编辑仅支持 UTF-8 .circ；请先在 Logisim 中另存为 UTF-8") from exc
    d = parse_project_bytes(text.encode("utf-8"), str(p))
    if not supported_source(d["source"]) or d["version"] != "1.0":
        raise ToolError("拒绝编辑未支持的 schema；仅支持经典 2.3/2.6/2.7 和 HUST 2.15、version=1.0")
    return p, text


def _edit_context(a: dict):
    p, text = _edit_guard(a)
    data = parse_project_bytes(text.encode("utf-8"), str(p))
    circuit = pick_circuit(data, a.get("circuit"))
    spans = [x for x in element_spans(text, "circuit")
             if x["parent"] == "project" and x["attrs"].get("name") == circuit["name"]]
    if len(spans) != 1:
        raise ToolError("电路 XML 区间不唯一")
    span = spans[0]
    body = text[span["start"]:span["end"]]
    return p, text, data, circuit, span, body


def xml_value(value: str) -> str:
    return escape(value, {'"': "&quot;", "'": "&apos;", "\n": "&#10;",
                          "\r": "&#13;", "\t": "&#9;"})


def newline_style(text: str) -> str:
    match = re.search(r"\r\n|\n|\r", text)
    return match.group(0) if match else "\n"


def insert_in_circuit(text: str, span: dict, block: str) -> str:
    if span["selfclose"]:
        opening = span["tag"].rstrip()[:-2].rstrip() + ">"
        replacement = opening + newline_style(text) + block + "</circuit>"
        return text[:span["start"]] + replacement + text[span["end"]:]
    close = span["close_start"]
    line_start = text.rfind("\n", 0, close) + 1
    insert_at = line_start if not text[line_start:close].strip() else close
    return text[:insert_at] + block + text[insert_at:]


def _postcondition(circuit: dict, components=None, wires=None) -> dict:
    return {"circuit": circuit["name"],
            "components": circuit["components"] if components is None else components,
            "wires": circuit["wires"] if wires is None else wires}


def _unique(matches: list, what: str):
    if not matches:
        raise ToolError(f"找不到匹配的{what}；原文件未改动")
    if len(matches) != 1:
        raise ToolError(f"匹配到 {len(matches)} 个{what}，请增加定位条件；原文件未改动")
    return matches[0]


def tool_add_wire(a: dict) -> dict:
    p, text, d, c, span, body = _edit_context(a)
    f, t = norm_xy(a["from_xy"]), norm_xy(a["to_xy"])
    first, second = xy(f), xy(t)
    if f == t:
        raise ToolError("导线两端不能相同")
    if first[0] != second[0] and first[1] != second[1]:
        raise ToolError("新增导线必须水平或垂直；请用两段正交导线")
    if any({xy(w["from"]), xy(w["to"])} == {first, second} for w in c["wires"]):
        raise ToolError("同一条导线已存在；没有重复写入")
    block = f'{detect_indent(body)}<wire from="{f}" to="{t}"/>' + newline_style(text)
    new_text = insert_in_circuit(text, span, block)
    wires = c["wires"] + [{"from": f, "to": t}]
    info = write_verified(p, new_text, _postcondition(c, wires=wires),
                          original_text=text, dry_run=a.get("dry_run", False))
    return {"ok": True, "circuit": c["name"], "added_wire": [f, t],
            "wire_count": len(wires), "would_insert": block.strip(), **info}


def tool_add_pin(a: dict) -> dict:
    p, text, d, c, span, body = _edit_context(a)
    if a.get("loc"):
        loc = norm_xy(a["loc"])
    elif "x" in a and "y" in a:
        loc = norm_xy(f'{a["x"]},{a["y"]}')
    else:
        raise ToolError("需要 loc 或同时提供 x、y")
    if any(x["name"] == "Pin" and xy(x["loc"]) == xy(loc) for x in c["components"]):
        raise ToolError("该坐标已有 Pin；请先定位现有引脚")
    label = a.get("label", "")
    is_out = a.get("output", False)
    width = a.get("width", 1)
    facing = a.get("facing", "east")
    if type(width) is not int or not 1 <= width <= 32:
        raise ToolError("Pin 位宽必须为 1..32 的整数")
    if facing not in {"east", "west", "north", "south"}:
        raise ToolError("Pin 朝向必须为 east/west/north/south")
    if type(is_out) is not bool or not isinstance(label, str):
        raise ToolError("output 必须为布尔值，label 必须为字符串")
    libid = next((lid for desc in ("#Wiring", "#Base") for lid, value in d["libs"].items()
                  if value == desc), None)
    if libid is None:
        raise ToolError("文件里没有 #Wiring 或 #Base 库")
    attrs = {"facing": facing}
    if label:
        attrs["label"] = label
    if is_out:
        attrs["output"] = "true"
    if width != 1:
        attrs["width"] = str(width)
    indent = detect_indent(body)
    lines = [f'{indent}<comp lib="{xml_value(libid)}" loc="{loc}" name="Pin">']
    lines.extend(f'{indent}  <a name="{key}" val="{xml_value(value)}"/>' for key, value in attrs.items())
    lines.append(f"{indent}</comp>")
    block = newline_style(text).join(lines) + newline_style(text)
    new_comp = {"lib": libid, "libdesc": d["libs"][libid], "name": "Pin",
                "loc": loc, "attrs": attrs, "is_subcircuit": False}
    info = write_verified(p, insert_in_circuit(text, span, block),
                          _postcondition(c, components=c["components"] + [new_comp]),
                          original_text=text, dry_run=a.get("dry_run", False))
    return {"ok": True, "circuit": c["name"], "loc": loc, "label": label,
            "direction": "out" if is_out else "in", "width": width,
            "lib_index_used": libid, "lib_desc": d["libs"][libid],
            "would_insert": block.strip(), **info}


def tool_set_pin_label(a: dict) -> dict:
    if not a.get("loc") and "old_label" not in a:
        raise ToolError("必须提供 loc 或 old_label 定位 Pin")
    p, text, d, c, span, body = _edit_context(a)
    new_label = a["new_label"]
    if not isinstance(new_label, str):
        raise ToolError("new_label 必须为字符串")
    want_loc = norm_xy(a["loc"]) if a.get("loc") else None
    comp_spans = find_comp_spans(body)
    if len(comp_spans) != len(c["components"]):
        raise ToolError("元件 XML 定位数量与解析结果不一致")
    matches = []
    for index, (cs, comp) in enumerate(zip(comp_spans, c["components"])):
        if comp["name"] != "Pin" or comp.get("is_subcircuit"):
            continue
        if want_loc and norm_xy(comp["loc"]) != want_loc:
            continue
        if "old_label" in a and (comp["attrs"].get("label") or "") != a["old_label"]:
            continue
        matches.append((index, cs))
    index, target = _unique(matches, "Pin")
    seg = body[target["start"]:target["end"]]
    labels = [x for x in element_spans(seg, "a")
              if x["parent"] == "comp" and x["attrs"].get("name") == "label"]
    if len(labels) > 1:
        raise ToolError("该 Pin 有多个 label 属性，请先修正原文件")
    replacement = f'<a name="label" val="{xml_value(new_label)}"/>'
    if labels:
        old = labels[0]
        new_seg = seg[:old["start"]] + replacement + seg[old["end"]:]
    elif target["selfclose"]:
        new_seg = seg.rstrip()[:-2].rstrip() + ">" + replacement + "</comp>"
    else:
        local = element_spans(seg, "comp")[0]
        new_seg = seg[:local["close_start"]] + replacement + seg[local["close_start"]:]
    new_text = text[:span["start"] + target["start"]] + new_seg + text[span["start"] + target["end"]:]
    components = [dict(x, attrs=dict(x["attrs"])) for x in c["components"]]
    components[index]["attrs"]["label"] = new_label
    info = write_verified(p, new_text, _postcondition(c, components=components),
                          original_text=text, dry_run=a.get("dry_run", False))
    return {"ok": True, "circuit": c["name"], "loc": components[index]["loc"],
            "new_label": new_label, "before": seg, "after": new_seg,
            "has_halt_pin": any(x["name"] == "Pin" and x["attrs"].get("label") == "halt"
                                for x in components), **info}


def tool_remove_component(a: dict) -> dict:
    if not a.get("loc"):
        raise ToolError("必须提供 loc 定位要删除的元件")
    p, text, d, c, span, body = _edit_context(a)
    want_loc = norm_xy(a["loc"])
    comp_spans = find_comp_spans(body)
    if len(comp_spans) != len(c["components"]):
        raise ToolError("元件 XML 定位数量与解析结果不一致")
    matches = [(i, cs) for i, (cs, comp) in enumerate(zip(comp_spans, c["components"]))
               if norm_xy(comp["loc"]) == want_loc
               and ("name" not in a or comp["name"] == a["name"])]
    index, target = _unique(matches, "元件")
    seg = body[target["start"]:target["end"]]
    new_text = text[:span["start"] + target["start"]] + text[span["start"] + target["end"]:]
    components = c["components"][:index] + c["components"][index + 1:]
    info = write_verified(p, new_text, _postcondition(c, components=components),
                          original_text=text, dry_run=a.get("dry_run", False))
    return {"ok": True, "circuit": c["name"], "removed": seg,
            "component_count": len(components), **info}


def tool_remove_wire(a: dict) -> dict:
    p, text, d, c, span, body = _edit_context(a)
    f, t = xy(norm_xy(a["from_xy"])), xy(norm_xy(a["to_xy"]))
    wire_spans = [x for x in element_spans(body, "wire") if x["parent"] == "circuit"]
    if len(wire_spans) != len(c["wires"]):
        raise ToolError("导线 XML 定位数量与解析结果不一致")
    matches = [(i, ws) for i, (ws, w) in enumerate(zip(wire_spans, c["wires"]))
               if {xy(w["from"]), xy(w["to"])} == {f, t}]
    index, target = _unique(matches, "导线")
    new_text = text[:span["start"] + target["start"]] + text[span["start"] + target["end"]:]
    wires = c["wires"][:index] + c["wires"][index + 1:]
    info = write_verified(p, new_text, _postcondition(c, wires=wires),
                          original_text=text, dry_run=a.get("dry_run", False))
    return {"ok": True, "circuit": c["name"], "removed": [f, t], "wire_count": len(wires), **info}


def tool_restore_backup(a: dict) -> dict:
    p = resolve_circ(a["file"])
    if p.suffix.lower() != ".circ":
        raise ToolError("恢复工具只允许操作 .circ 文件")
    baks = list_backups(p)
    if not a.get("backup"):
        return {"file": str(p), "backup_count": len(baks),
                "backups": [{"name": b["path"].name, "kind": b["kind"],
                             "size": b["path"].stat().st_size,
                             "created_key": b["created_key"]} for b in baks],
                "note": "备份按文件名中的创建时间排序；latest 只指最新 bak 编辑快照。"}
    want = a["backup"]
    if want == "latest":
        src = latest_edit_backup(p)
        if src is None:
            raise ToolError("没有 bak 编辑快照；prerestore 快照需用具体文件名恢复")
    else:
        src = next((b["path"] for b in baks if b["path"].name == want), None)
        if src is None:
            raise ToolError(f"找不到备份 {want!r}")
    raw = src.read_bytes()
    candidate = parse_project_bytes(raw, str(src))
    if not supported_source(candidate["source"]) or candidate["version"] != "1.0":
        raise ToolError("备份不是受支持的经典/HUST 工程；原文件未改动")
    if not candidate["circuits"]:
        raise ToolError("备份没有任何电路；原文件未改动")
    original = p.read_bytes()
    if a.get("dry_run"):
        return {"dry_run": True, "restored_from": src.name,
                "bytes_before": len(original), "bytes_after": len(raw),
                "sha256_after": hashlib.sha256(raw).hexdigest()}
    current_bak = make_backup(p, kind="prerestore", raw=original)
    try:
        atomic_replace(p, raw, original)
    except Exception as exc:
        raise ToolError(f"恢复提交失败：{exc}；当前内容备份在 {current_bak.name}") from exc
    return {"ok": True, "restored_from": src.name,
            "current_saved_as": current_bak.name, "file": str(p),
            "sha256_after": hashlib.sha256(raw).hexdigest()}


# --------------------------------------------------------------------------
# 工具注册表
# --------------------------------------------------------------------------

FILE_PROP = {"type": "string", "minLength": 1, "description": "Logisim 经典 .circ 文件路径（绝对或相对）"}
CIRCUIT_PROP = {"type": "string", "minLength": 1, "description": "电路名；省略则用文件里的 <main> 电路"}

TOOLS: list[dict] = [
    {
        "name": "logisim_env_info",
        "description": "报告本机兼容经典 Logisim 运行环境：exe 路径是否存在、java 路径、Python 版本和安全围栏。"
                       "probe_version=true 时会真正调用 -version 探测（约 1-3 秒）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "exe": {"type": "string", "description": "覆盖 logisim-hust exe 路径"},
                "java": {"type": "string", "description": "覆盖 java.exe 路径"},
                "probe_version": {"type": "boolean", "description": "是否实际探测版本"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_circuits",
        "description": "列出 .circ 工程的所有电路、主电路、schema 版本与库索引映射。",
        "inputSchema": {"type": "object", "properties": {"file": FILE_PROP},
                        "required": ["file"], "additionalProperties": False},
    },
    {
        "name": "describe_circuit",
        "description": "给出某个电路的概览：元件数、连线数、引脚表（标签/方向/位宽/坐标）、"
                       "元件分布直方图、子电路引用、是否含 halt 引脚。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": FILE_PROP, "circuit": CIRCUIT_PROP,
                "include_components": {"type": "boolean", "description": "附带每个元件的全部属性"},
                "include_wires": {"type": "boolean", "description": "附带全部导线"},
            },
            "required": ["file"], "additionalProperties": False,
        },
    },
    {
        "name": "list_pins",
        "description": "只列引脚：标签、输入/输出、位宽（含是否显式声明）、朝向、坐标。"
                       "要引脚标签就看这个，不要从 -tty 值表表头反推。",
        "inputSchema": {"type": "object", "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP},
                        "required": ["file"], "additionalProperties": False},
    },
    {
        "name": "count_components",
        "description": "统计元件数量与分布。all=true 时统计全部电路。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP,
                           "all": {"type": "boolean", "description": "统计文件中所有电路"}},
            "required": ["file"], "additionalProperties": False,
        },
    },
    {
        "name": "find_components",
        "description": "按关键字搜索元件（匹配元件名、库名、坐标、全部属性值）。"
                       "例如查所有标签为 halt 的元件：query=\"halt\"。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "query": {"type": "string"},
                           "circuit": CIRCUIT_PROP,
                           "all": {"type": "boolean", "description": "搜索所有电路"},
                           "limit": {"type": "integer", "description": "最多返回条数，默认 50"}},
            "required": ["file", "query"], "additionalProperties": False,
        },
    },
    {
        "name": "get_circuit_xml",
        "description": "取某个电路的原始 XML 文本片段（分页）。编辑前先用它看清真实文本，"
                       "因为写入是文本级定位。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP,
                           "offset": {"type": "integer"}, "max_chars": {"type": "integer"}},
            "required": ["file"], "additionalProperties": False,
        },
    },
    {
        "name": "list_library_index",
        "description": "列出该文件的库索引 -> 库名映射（#Wiring/#Gates/...）。"
                       "2.7.1 与 2.6.2 的索引不同，写元件前必须按映射查，不要背索引。",
        "inputSchema": {"type": "object", "properties": {"file": FILE_PROP},
                        "required": ["file"], "additionalProperties": False},
    },
    {
        "name": "validate_circuit",
        "description": "结构体检：schema、库索引、坐标、Pin 属性、重复标签、halt、main。"
                       "ok 表示没有 error；warning 单独列出。不检查几何连通或功能正确性。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP,
                           "all": {"type": "boolean", "description": "校验所有电路"},
                           "runtime": {"type": "boolean", "description": "加载真实端口并检查连通网络、多个驱动及位宽冲突；默认 false，仅结构检查。"},
                           "exe": {"type": "string"}, "java": {"type": "string"}},
            "required": ["file"], "additionalProperties": False,
        },
    },
    {
        "name": "simulate_tty",
        "description": "无界面仿真，只运行文件中的 <main>，不接受 circuit 选择参数；等价于 `java -jar <logisim-hust> -tty <format> <circ>`。"
                       "强制超时（没有 halt 引脚时仿真永不退出）。返回 verdict："
                       "halted by halt pin / halted by oscillation / timeout / output limit / error / exited。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": FILE_PROP,
                "format": {"type": "string",
                           "description": "逗号分隔，取值 table,speed,tty,halt,stats,few。默认 table,halt,stats"},
                "timeout_sec": {"type": "integer", "description": "超时秒数，默认 30"},
                "load_image": {"type": "string", "description": "可选的 RAM 镜像文件（-load，仅 -tty 可用）"},
                "include_output": {"type": "boolean", "description": "是否返回完整 stdout/stderr"},
                "exe": {"type": "string"}, "java": {"type": "string"},
            },
            "required": ["file"], "additionalProperties": False,
        },
    },
    {
        "name": "get_truth_table",
        "description": "兼容入口：与 get_simulation_table 相同，只解析输出变化记录，不自动枚举输入。"
                       "注意：表头只含输出引脚且会去掉前导 '!'、重名加数字后缀，"
                       "不能用来反推引脚标签；行尾的 Error！不能用来判断震荡。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "timeout_sec": {"type": "integer"},
                           "exe": {"type": "string"}, "java": {"type": "string"}},
            "required": ["file"], "additionalProperties": False,
        },
    },
    {
        "name": "add_wire",
        "description": "加一条正交导线。先校验候选内容与精确差值，再备份并原子提交。"
                       "dry_run=true 也校验但不写；重复导线拒绝写入。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP,
                           "from_xy": {"type": "string", "description": "起点，如 \"(330,530)\" 或 \"330,530\""},
                           "to_xy": {"type": "string", "description": "终点，格式同上"},
                           "dry_run": {"type": "boolean"}},
            "required": ["file", "from_xy", "to_xy"], "additionalProperties": False,
        },
    },
    {
        "name": "add_pin",
        "description": "加一个 Pin 元件，按库映射选索引，先验证再备份原子提交。"
                       "halt Pin 需要实际停止信号驱动到 1；标签本身不能保证停机。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP,
                           "loc": {"type": "string", "description": "坐标，如 \"(330,530)\""},
                           "x": {"type": "integer"}, "y": {"type": "integer"},
                           "label": {"type": "string"},
                           "output": {"type": "boolean", "description": "true 为输出引脚，默认输入"},
                           "width": {"type": "integer", "description": "位宽，默认 1（省略则不写入 width 属性）"},
                           "facing": {"type": "string", "description": "朝向：east/west/north/south，默认 east"},
                           "dry_run": {"type": "boolean"}},
            "required": ["file"], "additionalProperties": False,
        },
    },
    {
        "name": "set_pin_label",
        "description": "修改某个 Pin 的标签（按 loc 或按 old_label 定位）。"
                       "必须唯一匹配；halt 还需值变为 1 才停机。先校验再备份原子提交。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP,
                           "loc": {"type": "string", "description": "按坐标定位 Pin"},
                           "old_label": {"type": "string", "description": "按当前标签定位 Pin"},
                           "new_label": {"type": "string"},
                           "dry_run": {"type": "boolean"}},
            "required": ["file", "new_label"], "additionalProperties": False,
        },
    },
    {
        "name": "remove_component",
        "description": "删除一个元件，按 loc 或 loc+name 唯一定位。先验证精确删除结果再备份原子提交。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP,
                           "loc": {"type": "string"}, "name": {"type": "string"},
                           "dry_run": {"type": "boolean"}},
            "required": ["file", "loc"], "additionalProperties": False,
        },
    },
    {
        "name": "remove_wire",
        "description": "删除一条唯一匹配的导线（两端顺序可颠倒）。先校验再备份原子提交。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP, "circuit": CIRCUIT_PROP,
                           "from_xy": {"type": "string"}, "to_xy": {"type": "string"},
                           "dry_run": {"type": "boolean"}},
            "required": ["file", "from_xy", "to_xy"], "additionalProperties": False,
        },
    },
    {
        "name": "restore_backup",
        "description": "列出或恢复自动备份。不传 backup 时列出全部；传文件名或 latest 则恢复"
                       "（先验证备份，再保存当前字节并原子恢复；latest 只指 bak 编辑快照）。",
        "inputSchema": {
            "type": "object",
            "properties": {"file": FILE_PROP,
                           "backup": {"type": "string", "minLength": 1, "description": "备份文件名，或 latest"},
                           "dry_run": {"type": "boolean"}},
            "required": ["file"], "additionalProperties": False,
        },
    },
]

_table_tool = next(t for t in TOOLS if t["name"] == "get_truth_table")
TOOLS.append({"name": "get_simulation_table",
              "description": "只运行文件中的 <main>，不接受 circuit 选择参数。运行 -tty table,halt，解析输出变化记录为 header/rows，保留停机同一行的数值。"
                             "不会枚举输入；complete 只表示本次输出采集和解析完成，不表示真值表覆盖或功能正确。",
              "inputSchema": _table_tool["inputSchema"]})

for _tool in TOOLS:
    _props = _tool["inputSchema"]["properties"]
    for _key in ("loc", "from_xy", "to_xy", "name", "exe", "java", "load_image", "query", "format"):
        if _key in _props:
            _props[_key]["minLength"] = 1
    for _key, _minimum, _maximum in (("width", 1, 32), ("timeout_sec", 1, None),
                                     ("limit", 1, 1000), ("offset", 0, None), ("max_chars", 1, 64000)):
        if _key in _props:
            _props[_key]["minimum"] = _minimum
            if _maximum is not None:
                _props[_key]["maximum"] = _maximum
    if "facing" in _props:
        _props["facing"]["enum"] = ["east", "west", "north", "south"]
    if _tool["name"] == "set_pin_label":
        _tool["inputSchema"]["anyOf"] = [{"required": ["loc"]}, {"required": ["old_label"]}]
    if _tool["name"] == "add_pin":
        _tool["inputSchema"]["anyOf"] = [{"required": ["loc"]}, {"required": ["x", "y"]}]
    _writes = _tool["name"] in {"add_wire", "add_pin", "set_pin_label", "remove_component", "remove_wire", "restore_backup"}
    _tool["annotations"] = {"readOnlyHint": not _writes, "destructiveHint": _writes,
                            "openWorldHint": False}

TOOL_SCHEMAS = {t["name"]: t["inputSchema"] for t in TOOLS}

TOOL_IMPL = {
    "logisim_env_info": tool_env_info,
    "list_circuits": tool_list_circuits,
    "describe_circuit": tool_describe_circuit,
    "list_pins": tool_list_pins,
    "count_components": tool_count_components,
    "find_components": tool_find_components,
    "get_circuit_xml": tool_get_circuit_xml,
    "list_library_index": tool_list_library_index,
    "validate_circuit": tool_validate_circuit,
    "simulate_tty": tool_simulate_tty,
    "get_truth_table": tool_get_truth_table,
    "get_simulation_table": tool_get_simulation_table,
    "add_wire": tool_add_wire,
    "add_pin": tool_add_pin,
    "set_pin_label": tool_set_pin_label,
    "remove_component": tool_remove_component,
    "remove_wire": tool_remove_wire,
    "restore_backup": tool_restore_backup,
}


# --------------------------------------------------------------------------
# MCP stdio 协议层（JSON-RPC 2.0，换行分隔）
# --------------------------------------------------------------------------

def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _ok(rid, result) -> None:
    _send({"jsonrpc": "2.0", "id": rid, "result": result})


def _err(rid, code: int, message: str, data=None) -> None:
    e = {"code": code, "message": message}
    if data is not None:
        e["data"] = data
    _send({"jsonrpc": "2.0", "id": rid, "error": e})


def _text_result(payload, is_error: bool = False) -> dict:
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def call_tool(name: str, args: dict) -> dict:
    if not isinstance(name, str):
        return _text_result({"error": "工具名必须为字符串"}, True)
    impl = TOOL_IMPL.get(name)
    if impl is None:
        return _text_result({"error": f"未知工具 {name!r}", "available": sorted(TOOL_IMPL)}, True)
    try:
        validate_arguments(args, TOOL_SCHEMAS[name])
        return _text_result(impl(args))
    except ToolError as exc:
        return _text_result({"error": str(exc)}, True)
    except Exception as exc:  # 兜底，避免一个工具炸掉整个会话
        return _text_result({"error": f"{type(exc).__name__}: {exc}",
                             "hint": "这是服务端未预期异常，请把该消息反馈给使用者"}, True)


def validate_arguments(args, schema: dict) -> None:
    """Validate all exposed nested schemas, including dynamic attribute maps."""
    def check(value, rule, key):
        kinds = rule.get("type", [])
        kinds = [kinds] if isinstance(kinds, str) else kinds
        valid = {"string": isinstance(value, str), "integer": type(value) is int,
                 "boolean": type(value) is bool, "object": isinstance(value, dict),
                 "array": isinstance(value, list)}
        if kinds and not any(valid.get(kind, False) for kind in kinds):
            raise ToolError(f"参数 {key} 必须为 {'/'.join(kinds)}")
        if isinstance(value, dict):
            missing = [k for k in rule.get("required", []) if k not in value]
            if missing: raise ToolError(f"{key} 缺少必填参数：{', '.join(missing)}")
            props = rule.get("properties", {})
            extra = rule.get("additionalProperties", True)
            for k, v in value.items():
                if k in props: check(v, props[k], f"{key}.{k}")
                elif extra is False: raise ToolError(f"未知参数：{key}.{k}")
                elif isinstance(extra, dict): check(v, extra, f"{key}.{k}")
            if "anyOf" in rule and not any(all(k in value for k in option["required"]) for option in rule["anyOf"]):
                raise ToolError("需要提供以下一组定位参数：" + " 或 ".join("+".join(o["required"]) for o in rule["anyOf"]))
        if isinstance(value, list):
            if len(value) < rule.get("minItems", 0) or len(value) > rule.get("maxItems", float("inf")):
                raise ToolError(f"参数 {key} 数组长度超出允许范围")
            for i, item in enumerate(value): check(item, rule.get("items", {}), f"{key}[{i}]")
        if isinstance(value, str) and len(value) < rule.get("minLength", 0):
            raise ToolError(f"参数 {key} 不能为空")
        if type(value) is int:
            if value < rule.get("minimum", float("-inf")) or value > rule.get("maximum", float("inf")):
                raise ToolError(f"参数 {key} 数值超出允许范围")
        if "enum" in rule and value not in rule["enum"]:
            raise ToolError(f"参数 {key} 取值必须为 {rule['enum']}")
    check(args, schema, "arguments")


_builder_spec = importlib.util.spec_from_file_location("logisim_builder", Path(__file__).with_name("builder.py"))
_builder = importlib.util.module_from_spec(_builder_spec)
_builder_spec.loader.exec_module(_builder)
class _ServerAPI:
    def __getattr__(self, name):
        return globals()[name]

_builder.install(_ServerAPI())
import connections as _connections
_connections.install(_ServerAPI())
import image_export as _image_export
_image_export.install(_ServerAPI())


def handle(req: dict) -> None:
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params", {})
    if req.get("jsonrpc") != "2.0" or not isinstance(method, str) or not isinstance(params, dict):
        _err(rid, -32600, "非法 JSON-RPC 请求：检查 jsonrpc、method 和 params")
        return
    if "id" not in req:
        return  # Notifications cannot invoke mutations or receive replies.
    if type(rid) not in (int, str):
        _err(None, -32600, "请求 id 必须为整数或字符串")
        return

    if method == "initialize":
        client_ver = params.get("protocolVersion")
        ver = client_ver if client_ver in SUPPORTED_PROTOCOLS else PROTOCOL_VERSION
        _ok(rid, {
            "protocolVersion": ver,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        })
        return

    if method in ("notifications/initialized", "initialized",
                  "notifications/cancelled", "notifications/roots/list_changed"):
        return  # 通知不需要回复

    if method == "ping":
        _ok(rid, {})
        return

    if method == "tools/list":
        _ok(rid, {"tools": TOOLS})
        return

    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in TOOL_IMPL:
            _err(rid, -32602, "tools/call 缺少有效的 params.name，或工具不存在")
            return
        arguments = params.get("arguments", {})
        try:
            validate_arguments(arguments, TOOL_SCHEMAS[name])
        except ToolError as exc:
            _err(rid, -32602, str(exc))
            return
        _ok(rid, call_tool(name, arguments))
        return

    if rid is None:
        return  # 其它通知，静默忽略
    _err(rid, -32601, f"未实现的方法：{method}")


def serve() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    while True:
        raw = sys.stdin.buffer.readline()
        if not raw:
            break
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            _err(None, -32700, f"JSON 解析失败：{exc}")
            continue
        if isinstance(req, list):
            _err(None, -32600, "stdio 每行只接受一个请求对象，不接受批量数组")
            continue
        if not isinstance(req, dict):
            _err(None, -32600, "不是合法的 JSON-RPC 请求对象")
            continue
        try:
            handle(req)
        except Exception as exc:  # 协议层兜底
            if req.get("id") is not None:
                _err(req.get("id"), -32603, f"内部错误：{exc}")
    return 0


# --------------------------------------------------------------------------
# CLI：自检 / 打印配置
# --------------------------------------------------------------------------

def self_test(circ: str) -> int:
    print(f"== logisim-classic-lab-mcp 自检 ==\nPython {sys.version.split()[0]} on {sys.platform}")
    steps = [
        ("logisim_env_info", {"probe_version": True}),
        ("list_circuits", {"file": circ}),
        ("list_library_index", {"file": circ}),
        ("describe_circuit", {"file": circ}),
        ("list_pins", {"file": circ}),
        ("count_components", {"file": circ, "all": True}),
        ("find_components", {"file": circ, "query": "halt", "all": True}),
        ("get_circuit_xml", {"file": circ, "max_chars": 1000}),
        ("validate_circuit", {"file": circ, "all": True}),
        ("simulate_tty", {"file": circ, "format": "table,halt,stats", "timeout_sec": 20,
                          "include_output": True}),
        ("get_simulation_table", {"file": circ, "timeout_sec": 20}),
    ]
    rc = 0
    for name, args in steps:
        print(f"\n--- {name} ---")
        out = call_tool(name, args)
        if out.get("isError"):
            rc = 1
            print("  [isError=true]")
        txt = out["content"][0]["text"]
        if not out.get("isError"):
            payload = json.loads(txt)
            failed = (
                (name == "logisim_env_info" and not payload.get("probe", {}).get("ok"))
                or (name == "validate_circuit" and payload.get("error_count", 0) > 0)
                or (name == "simulate_tty" and (not payload.get("process_ok") or payload.get("verdict") == "halted by oscillation"))
                or (name == "get_simulation_table" and not payload.get("complete"))
            )
            if failed:
                rc = 1
                print("  [检查未通过]")
        print(txt if len(txt) <= 4000 else txt[:4000] + "\n  ...[截断]")
    return rc


def print_config() -> None:
    here = Path(__file__).resolve()
    py = sys.executable
    try:
        configured_exe = find_exe()
    except ToolError:
        configured_exe = os.environ.get("LOGISIM_HUST_EXE") or DEFAULT_EXE
    cfg = {
        "mcpServers": {
            "logisim-classic-lab-mcp": {
                "command": py,
                "args": [str(here)],
                "env": {"LOGISIM_HUST_EXE": configured_exe},
            }
        }
    }
    print("# 通用 JSON 形式（Claude Desktop / 多数客户端）")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    print()
    print("# Codex config.toml 形式")
    print("[mcp_servers.logisim-classic-lab-mcp]")
    print(f'command = "{py.replace(chr(92), "/")}"')
    print(f'args = ["{str(here).replace(chr(92), "/")}"]')
    print("[mcp_servers.logisim-classic-lab-mcp.env]")
    print(f'LOGISIM_HUST_EXE = {json.dumps(configured_exe.replace(chr(92), "/"), ensure_ascii=False)}')
    print()
    print(f"# 服务端脚本: {here}")
    print(f"# Python    : {py}")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Logisim Classic Lab MCP server")
    ap.add_argument("--self-test", metavar="CIRC", help="对本机 .circ 跑一遍全部只读工具")
    ap.add_argument("--print-config", action="store_true", help="打印客户端配置片段")
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args(argv)

    if args.version:
        print(f"{SERVER_NAME} {SERVER_VERSION} (python {sys.version.split()[0]})")
        return 0
    if args.print_config:
        print_config()
        return 0
    if args.self_test:
        return self_test(args.self_test)
    return serve()


if __name__ == "__main__":
    sys.exit(main())
