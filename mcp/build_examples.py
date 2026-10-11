"""Generate two runnable examples using the same protected MCP implementations.

Usage: python build_examples.py OUTPUT_DIRECTORY
Existing examples are refused. Also saves reusable tool-call JSON and evidence.
"""
import json
from pathlib import Path
import sys
import server as s


def net(name, *ends):
    return {"name": name, "endpoints": [{"id": ident, "port": port} for ident, port in ends]}


def checked(tool, args):
    response = s.call_tool(tool, args)
    data = json.loads(response["content"][0]["text"])
    if response["isError"]:
        raise RuntimeError(data)
    return data


def full_adder(path):
    inputs = [{"id": label, "name": "Pin", "loc": f"(80,{y})", "attrs": {"label": label, "tristate": False}} for label, y in (("A", 80), ("B", 180), ("Cin", 280))]
    gates = [{"id": ident, "name": kind, "loc": loc} for ident, kind, loc in
             (("x1", "XOR Gate", "(300,100)"), ("x2", "XOR Gate", "(520,100)"), ("a1", "AND Gate", "(300,240)"),
              ("a2", "AND Gate", "(520,240)"), ("or", "OR Gate", "(740,240)"))]
    outputs = [{"id": label, "name": "Pin", "loc": f"(850,{y})", "attrs": {"label": label, "output": True, "facing": "west"}} for label, y in (("S", 100), ("C", 240))]
    fa = {"name": "FA", "components": inputs + gates + outputs,
          "nets": [net("A", ("A", 0), ("x1", 1), ("a1", 1)), net("B", ("B", 0), ("x1", 2), ("a1", 2)),
                   net("Cin", ("Cin", 0), ("x2", 2), ("a2", 2)), net("axb", ("x1", 0), ("x2", 1), ("a2", 1)),
                   net("ab", ("a1", 0), ("or", 1)), net("cx", ("a2", 0), ("or", 2)), net("S", ("x2", 0), ("S", 0)), net("C", ("or", 0), ("C", 0))]}
    main = {"name": "main", "components": [{"id": label, "name": "Pin", "loc": f"(100,{y})", "attrs": {"label": label, "tristate": False}} for label, y in (("A", 100), ("B", 180), ("Cin", 260))]}
    main["components"] += [{"id": "fa", "name": "FA", "loc": "(400,180)"},
                           {"id": "S", "name": "Pin", "loc": "(700,140)", "attrs": {"label": "S", "output": True, "facing": "west"}},
                           {"id": "C", "name": "Pin", "loc": "(700,220)", "attrs": {"label": "C", "output": True, "facing": "west"}},
                           {"id": "stop", "name": "Power", "loc": "(100,400)"},
                           {"id": "halt", "name": "Pin", "loc": "(300,400)", "attrs": {"label": "halt", "output": True, "facing": "west"}}]
    args = {"file": str(path), "main": "main", "circuits": [main, fa]}
    preview = checked("build_project", {**args, "dry_run": True})
    instance = next(x for c in preview["ports"] if c["name"] == "main" for x in c["components"] if x["name"] == "FA")
    portmap = {port["tooltip"]: port["index"] for port in instance["ports"]}
    main["nets"] = [net(label, (label, 0), ("fa", portmap[label])) for label in ("A", "B", "Cin", "S", "C")]
    main["nets"].append({**net("stop", ("stop", 0), ("halt", 0)), "waypoints": []})
    return args


def counter(path):
    nodes = [{"id": "counter", "name": "Counter", "loc": "(400,160)", "attrs": {"width": 2, "max": "0x3"}},
             {"id": "clock", "name": "Clock", "loc": "(100,100)"}, {"id": "low", "name": "Ground", "loc": "(100,240)"},
             {"id": "high", "name": "Power", "loc": "(100,320)"},
             {"id": "zero", "name": "Constant", "loc": "(100,400)", "attrs": {"width": 2, "value": "0x0"}},
             {"id": "count", "name": "Pin", "loc": "(700,160)", "attrs": {"width": 2, "output": True, "label": "count", "facing": "west"}},
             {"id": "halt", "name": "Pin", "loc": "(700,260)", "attrs": {"output": True, "label": "halt", "facing": "west"}}]
    nets = [net("clock", ("clock", 0), ("counter", 2)), net("zero_data", ("zero", 0), ("counter", 1)),
            net("clear_load_reverse_preset", ("low", 0), ("counter", 3), ("counter", 4), ("counter", 5), ("counter", 7)),
            net("enable", ("high", 0), ("counter", 8)), net("count", ("counter", 0), ("count", 0)), net("stop", ("counter", 6), ("halt", 0))]
    return {"file": str(path), "circuits": [{"name": "main", "components": nodes, "nets": nets}]}


def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    targets = [root / "full-adder.circ", root / "counter-stop.circ"]
    if any(path.exists() for path in targets):
        raise RuntimeError("Example targets already exist; choose a new output directory")
    evidence = []
    for args in (full_adder(targets[0]), counter(targets[1])):
        path = Path(args["file"])
        result = checked("build_project", args)
        table = checked("get_simulation_table", {"file": str(path), "timeout_sec": 5})
        if not table["complete"]: raise RuntimeError(table)
        values = dict(zip(table["header"], table["rows"][-1]))
        expected = {"S": "0", "C": "0"} if path.stem == "full-adder" else {"count": "3"}
        if values != expected: raise RuntimeError(f"Unexpected outputs: {values}")
        portable = {**args, "file": path.name}
        path.with_suffix(".json").write_text(json.dumps({"tool": "build_project", "arguments": portable}, ensure_ascii=False, indent=2), encoding="utf-8")
        evidence.append({"file": str(path), "build_sha256": result["sha256_after"], "table": table})
    (root / "verification.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "examples": [str(p) for p in targets]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
