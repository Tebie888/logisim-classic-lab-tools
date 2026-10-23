"""Standard-library regressions. All mutations use temporary circuits."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SERVER = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("logisim_server_under_test", SERVER)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

BASE = '''<?xml version="1.0" encoding="UTF-8"?>
<project source="2.7.1" version="1.0">
This file is intended to be loaded by Logisim.
  <lib name="0" desc="#Wiring"/>
  <main name="main"/>
  <circuit name="main">
    <comp lib="0" loc="(100,100)" name="Power"/>
    <comp lib="0" loc="(200,100)" name="Pin">
      <a name="output" val="true"/>
      <a name="label" val="halt"/>
    </comp>
    <wire from="(100,100)" to="(200,100)"/>
  </circuit>
  <circuit name="untouched"><comp lib="0" loc="(20,20)" name="Pin"/></circuit>
</project>
'''


class CircuitFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="logisim-regression-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "电路[1].circ"
        self.file.write_bytes(BASE.encode("utf-8"))
        self.env = patch.dict(os.environ, {"LOGISIM_MCP_WORKSPACE": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def call(self, tool_name, **args):
        result = s.call_tool(tool_name, {"file": str(self.file), **args})
        payload = json.loads(result["content"][0]["text"])
        self.assertFalse(result["isError"], payload)
        return payload

    def rejected(self, tool_name, **args):
        before = self.file.read_bytes()
        result = s.call_tool(tool_name, {"file": str(self.file), **args})
        self.assertTrue(result["isError"], result)
        self.assertEqual(before, self.file.read_bytes())
        return json.loads(result["content"][0]["text"])

class RuntimeFixture(CircuitFixture):
    def setUp(self):
        super().setUp()
        try:
            s.find_exe()
            s.find_java()
        except s.ToolError as exc:
            self.skipTest(str(exc))
        for helper in ('PortProbe.class', 'CircuitImage.class'):
            if not SERVER.with_name(helper).is_file():
                self.skipTest('Compile Java bridges to enable runtime tests')


class CircuitTests(CircuitFixture):
    def test_edit_and_restore_exact_bytes(self):
        for newline, bom in (("\n", False), ("\r\n", False), ("\n", True)):
            with self.subTest(newline=newline, bom=bom):
                raw = (("\ufeff" if bom else "") + BASE.replace("\n", newline)).encode("utf-8")
                self.file.write_bytes(raw)
                result = self.call("add_pin", loc="(300,300)", label='A&B "quoted" \\1', output=True, width=8)
                current = self.file.read_bytes()
                self.assertEqual(current.startswith(b"\xef\xbb\xbf"), bom)
                if newline == "\n":
                    self.assertNotIn(b"\r\n", current)
                else:
                    self.assertNotIn(b"\n", current.replace(b"\r\n", b""))
                self.assertIn(b"This file is intended", current)
                pin = next(p for p in self.call("list_pins")["pins"] if p["loc"] == "(300,300)")
                self.assertEqual(pin["label"], 'A&B "quoted" \\1')
                self.assertEqual(pin["width"], 8)
                self.call("restore_backup", backup=result["backup"])
                self.assertEqual(self.file.read_bytes(), raw)

    def test_invalid_candidate_never_changes_bytes(self):
        for raw in (BASE.encode(), BASE.replace("\n", "\r\n").encode(), b"\xef\xbb\xbf" + BASE.encode()):
            self.file.write_bytes(raw)
            self.rejected("add_pin", loc="(300,300)", label="invalid\x00control")
            self.assertEqual(self.file.read_bytes(), raw)

    def test_restore_bad_xml_and_unsupported_backup(self):
        for raw in (b"not XML", BASE.replace('source="2.7.1"', 'source="4.0.0"').encode()):
            backup = s.make_backup(self.file)
            backup.write_bytes(raw)
            self.rejected("restore_backup", backup=backup.name)

    def test_latest_uses_creation_order_after_restore(self):
        t = time.time()
        os.utime(self.file, (t - 300, t - 300))
        first = s.make_backup(self.file)
        self.file.write_bytes(BASE.replace('val="halt"', 'val="older edit"').encode())
        os.utime(self.file, (t - 200, t - 200))
        s.make_backup(self.file)
        self.call("restore_backup", backup=first.name)
        newest = s.make_backup(self.file)
        self.assertEqual(s.latest_edit_backup(self.file), newest)

    def test_legacy_backup_collision_order(self):
        for suffix in ("20250101-120000", "20250101-120000-2", "20250101-120000-10"):
            self.file.with_name(self.file.name + ".bak-" + suffix).write_bytes(BASE.encode())
        self.assertTrue(s.latest_edit_backup(self.file).name.endswith("-10"))

    def test_latest_does_not_fall_back_to_prerestore(self):
        s.make_backup(self.file, kind="prerestore")
        self.rejected("restore_backup", backup="latest")

    def test_dry_run_validates_without_backup_or_mutation(self):
        before = self.file.read_bytes()
        for name, args in (("add_pin", {"loc": "(300,300)", "label": "preview"}),
                           ("add_wire", {"from_xy": "(300,300)", "to_xy": "(400,300)"}),
                           ("set_pin_label", {"old_label": "halt", "new_label": "preview"}),
                           ("remove_component", {"loc": "(100,100)"}),
                           ("remove_wire", {"from_xy": "(100,100)", "to_xy": "(200,100)"})):
            self.assertTrue(self.call(name, dry_run=True, **args)["dry_run"])
            self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual(s.list_backups(self.file), [])
        self.rejected("add_pin", loc="(300,300)", label="bad\x00", dry_run=True)

    def test_required_selectors_and_scalar_types(self):
        cases = (("set_pin_label", {"new_label": "changed"}),
                 ("remove_component", {}), ("add_pin", {}),
                 ("add_pin", {"x": 1}), ("add_pin", {"loc": "(300,300)", "width": -1}),
                 ("add_pin", {"loc": "(300,300)", "width": 33}),
                 ("add_pin", {"loc": "(300,300)", "width": True}),
                 ("add_pin", {"loc": "(300,300)", "output": "false"}),
                 ("add_pin", {"loc": "(300,300)", "facing": "banana"}),
                 ("simulate_tty", {"format": ["table", "halt"]}),
                 ("list_pins", {"unexpected": 1}), ("get_circuit_xml", {"offset": -1}))
        for name, args in cases:
            with self.subTest(name=name, args=args):
                result = self.rejected(name, **args)
                self.assertNotIn("AttributeError", result["error"])

    def test_ambiguous_pin_and_component_rejected(self):
        self.file.write_bytes(BASE.replace("  </circuit>", '<comp lib="0" name="Pin" loc="(250,100)"><a name="label" val="halt"/></comp>\n  </circuit>', 1).encode())
        self.rejected("set_pin_label", old_label="halt", new_label="Q")
        self.file.write_bytes(BASE.replace("  </circuit>", '<comp lib="0" name="Pin" loc="(100,100)"/>\n  </circuit>', 1).encode())
        self.rejected("remove_component", loc="(100,100)")
        self.call("remove_component", loc="(100,100)", name="Power")

    def test_comment_cdata_and_quotes_do_not_confuse_editing(self):
        fake = '<!-- <comp lib="0" name="Pin" loc="(999,999)"/> --><![CDATA[<comp lib="0" name="Pin" loc="(888,888)"/>]]>'
        text = BASE.replace('  <circuit name="main">', "  <circuit name='main'>" + fake)
        text = text.replace('<a name="label" val="halt"/>', "<a val='A&amp;B &quot;quoted&quot;' name='label'/>")
        self.file.write_bytes(text.encode())
        self.rejected("remove_component", loc="(999,999)")
        self.rejected("remove_component", loc="(888,888)")
        self.call("set_pin_label", old_label='A&B "quoted"', new_label='Q>R \\g<1>')
        self.assertIn(fake.encode(), self.file.read_bytes())
        self.assertEqual(self.call("list_pins")["pins"][0]["label"], 'Q>R \\g<1>')

    def test_newline_characters_in_labels_round_trip(self):
        self.call("set_pin_label", loc="(200,100)", new_label="A\tB\nC\rD")
        self.assertEqual(self.call("list_pins")["pins"][0]["label"], "A\tB\nC\rD")

    def test_selfclosing_circuit_pin_and_entity_name(self):
        self.file.write_bytes(b'<project source="2.7.1" version="1.0"><lib name="0" desc="#Wiring"/><main name="A&amp;B"/><circuit name="A&amp;B"/></project>')
        self.call("add_pin", loc="(-10,20)", label="one")
        self.call("set_pin_label", loc="(-10,20)", new_label="two")
        self.assertEqual(self.call("list_pins")["pins"][0]["label"], "two")
        self.call("remove_component", loc="(-10,20)")
        self.assertEqual(self.call("describe_circuit")["component_count"], 0)

    def test_wire_attribute_order_reverse_and_comments(self):
        text = BASE.replace('<wire from="(100,100)" to="(200,100)"/>', '<!-- <wire from="(999,999)" to="(888,999)"/> --><wire to = \'(200,100)\' from = \'(100,100)\' />')
        self.file.write_bytes(text.encode())
        self.rejected("remove_wire", from_xy="(999,999)", to_xy="(888,999)")
        self.call("remove_wire", from_xy="(200,100)", to_xy="(100,100)")
        self.assertEqual(self.call("describe_circuit")["wire_count"], 0)

    def test_orthogonal_duplicate_and_strict_coordinates(self):
        self.rejected("add_wire", from_xy="(300,300)", to_xy="(310,310)")
        self.rejected("add_wire", from_xy="(200,100)", to_xy="(100,100)")
        self.rejected("add_pin", loc="prefix (300,300) suffix")
        self.rejected("add_pin", loc="(300,300")
        self.call("add_wire", from_xy="-10, 20", to_xy="(-10,40)")

    def test_unsupported_source_cannot_edit(self):
        self.file.write_bytes(BASE.replace('source="2.7.1"', 'source="4.0.0"').encode())
        self.assertGreater(self.call("validate_circuit")["error_count"], 0)
        self.rejected("add_pin", loc="(300,300)")

    def test_base_library_and_subcircuit_classification(self):
        self.file.write_bytes(BASE.replace('source="2.7.1"', 'source="2.6.2.165"').replace('#Wiring', '#Base').encode())
        self.assertEqual(self.call("add_pin", loc="(300,300)")["lib_desc"], "#Base")
        text = BASE.replace('  </circuit>', '<comp lib="" loc="(50,50)" name="untouched"/>\n  </circuit>', 1)
        self.file.write_bytes(text.encode())
        self.assertEqual(self.call("validate_circuit")["error_count"], 0)
        self.assertEqual(self.call("describe_circuit")["subcircuit_refs"], ["untouched"])

    def test_classic_23_course_source_is_supported(self):
        self.file.write_bytes(BASE.replace('source="2.7.1"', 'source="2.3.2"').replace('#Wiring', '#Base').encode())
        self.assertEqual(self.call("validate_circuit")["error_count"], 0)
        self.assertEqual(self.call("add_pin", loc="(300,300)")["lib_desc"], "#Base")

    def test_warnings_do_not_make_ok_false(self):
        self.file.write_bytes(BASE.replace('val="halt"', 'val="Q"').encode())
        result = self.call("validate_circuit")
        self.assertTrue(result["ok"])
        self.assertGreater(result["warning_count"], 0)

    def test_failed_atomic_replace_preserves_original(self):
        with patch.object(s.os, "replace", side_effect=OSError("simulated failure")):
            self.rejected("add_pin", loc="(300,300)")
        self.assertFalse(list(self.root.glob("*.tmp")))
        self.assertEqual(len(s.list_backups(self.file)), 1)

    def test_stale_edit_preserves_external_changes(self):
        original = self.file.read_bytes()
        external = original.replace(b'This file is intended', b'Externally edited file intended')
        self.file.write_bytes(external)
        with self.assertRaises(s.ToolError):
            s.write_verified(self.file, original.decode(), s._postcondition(s.pick_circuit(s.parse_project_bytes(original), None)), original_text=original.decode())
        self.assertEqual(self.file.read_bytes(), external)

    def test_workspace_fence(self):
        outside = self.root.parent / "outside.circ"
        with self.assertRaises(s.ToolError):
            s.resolve_circ(str(outside), must_exist=False)


class TableTests(unittest.TestCase):
    def test_last_row_with_halt_message(self):
        result = s.parse_tty_table("Q\r\n1    Error！halted due to halt pin\r\n")
        self.assertEqual(result["header"], ["Q"])
        self.assertEqual(result["rows"], [["1"]])
        self.assertFalse(result["parse_warnings"])

    def test_tabs_preserve_labels_and_error_signal(self):
        result = s.parse_tty_table("Long label\tQ\n0\tE    Error！\n1\t1halted due to halt pin\n")
        self.assertEqual(result["header"], ["Long label", "Q"])
        self.assertEqual(result["rows"], [["0", "E"], ["1", "1"]])

    def test_malformed_rows_and_no_outputs(self):
        self.assertEqual(s.parse_tty_table("\n    Error！halted due to halt pin\n")["header"], [])
        result = s.parse_tty_table("A\tB\n1\n0\t1\n")
        self.assertEqual(result["rows"], [["0", "1"]])
        self.assertEqual(len(result["parse_warnings"]), 1)


class ProtocolTests(unittest.TestCase):
    def test_stdio_handshake_new_alias_and_invalid_input(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "logisim_env_info", "arguments": []}},
            {"jsonrpc": "2.0", "id": 4, "method": "ping"},
        ]
        result = subprocess.run([sys.executable, str(SERVER)], input="".join(json.dumps(x) + "\n" for x in requests), capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(x) for x in result.stdout.splitlines()]
        self.assertEqual([x["id"] for x in replies], [1, 2, 3, 4])
        names = {x["name"] for x in replies[1]["result"]["tools"]}
        self.assertEqual(names, set(s.TOOL_IMPL))
        self.assertIn("trace_propagation", names)
        self.assertIn("get_simulation_table", names)
        self.assertEqual(replies[2]["error"]["code"], -32602)

    def test_invalid_requests_do_not_crash_or_invoke_tools(self):
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": []}),
            json.dumps([{"jsonrpc": "2.0", "id": 2, "method": "ping"}]),
            "not JSON",
            json.dumps({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "no-tool"}}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "no-tool"}}),
            json.dumps({"jsonrpc": "2.0", "id": 4, "method": "ping"}),
        ]
        result = subprocess.run([sys.executable, str(SERVER)], input="\n".join(lines) + "\n", capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(x) for x in result.stdout.splitlines()]
        self.assertEqual(len(replies), 5)
        self.assertEqual(replies[0]["error"]["code"], -32600)
        self.assertEqual(replies[2]["error"]["code"], -32700)
        self.assertEqual(replies[3]["error"]["code"], -32602)
        self.assertEqual(replies[4]["result"], {})


class RealSimulationTests(CircuitFixture):
    def test_nonzero_exit_and_output_limit_are_failures(self):
        fake = unittest.mock.MagicMock()
        fake.poll.return_value = 42
        fake.returncode = 42
        with patch.object(s, "find_exe", return_value="unused"), patch.object(s, "find_java", return_value="unused"), patch.object(s.subprocess, "Popen", return_value=fake):
            result = self.call("simulate_tty", timeout_sec=1)
        self.assertFalse(result["process_ok"])
        self.assertEqual(result["verdict"], "error")
        try:
            s.find_exe()
            s.find_java()
        except s.ToolError as exc:
            self.skipTest(str(exc))
        with patch.dict(os.environ, {"LOGISIM_MCP_MAX_OUTPUT_BYTES": "1"}):
            result = self.call("simulate_tty", timeout_sec=3, include_output=True)
        self.assertEqual(result["verdict"], "output limit")
        self.assertFalse(result["process_ok"])
        self.assertLessEqual(len(result["stdout"].encode("utf-8")), 1)

    def test_real_simulation_last_row_timeout_and_cli_status(self):
        try:
            s.find_exe()
            s.find_java()
        except s.ToolError as exc:
            self.skipTest(str(exc))
        extra = '<comp lib="0" loc="(200,160)" name="Pin"><a name="output" val="true"/><a name="label" val="Q"/></comp><wire from="(100,100)" to="(100,160)"/><wire from="(100,160)" to="(200,160)"/>'
        self.file.write_bytes(BASE.replace("  </circuit>", extra + "\n  </circuit>", 1).encode())
        table = self.call("get_simulation_table", timeout_sec=3)
        self.assertEqual(table["header"], ["Q"])
        self.assertEqual(table["rows"], [["1"]])
        self.assertTrue(table["complete"])
        legacy = self.call("get_truth_table", timeout_sec=3)
        self.assertEqual(legacy["rows"], table["rows"])
        self.assertFalse(legacy["inputs_enumerated"])
        self.file.write_bytes(BASE.replace('val="halt"', 'val="Q"').encode())
        simulation = self.call("simulate_tty", timeout_sec=1, include_output=True)
        self.assertTrue(simulation["timed_out"])
        self.assertFalse(simulation["process_ok"])
        env = dict(os.environ, LOGISIM_MCP_MAX_TIMEOUT="1")
        cli = subprocess.run([sys.executable, str(SERVER), "--self-test", str(self.file)], capture_output=True, timeout=15, env=env)
        self.assertEqual(cli.returncode, 1)


class BuilderTests(RuntimeFixture):
    def fresh(self, name="built.circ"):
        self.file = self.root / name

    def test_new_project_no_overwrite_dry_run_and_nested_validation(self):
        self.fresh()
        result = self.call("create_project", dry_run=True)
        self.assertIn("candidate_xml", result)
        self.assertFalse(self.file.exists())
        self.call("create_project")
        self.assertTrue(self.file.exists())
        self.rejected("create_project")
        self.rejected("build_circuit", components=[{"id": "x", "name": "Pin", "attrs": {"width": []}}])
        self.rejected("build_circuit", components=[{"id": "x", "name": "Pin", "typo": 1}])
        self.rejected("build_project", circuits=[])

    def test_generic_catalog_ports_backups_and_rejected_candidates(self):
        catalog = s.call_tool("list_component_catalog", {})
        entries = json.loads(catalog["content"][0]["text"])["components"]
        self.assertFalse(catalog["isError"])
        self.assertTrue({"Counter", "RAM", "Multiplexer", "7400"} <= {x["name"] for x in entries})
        before = self.file.read_bytes()
        result = self.call("add_component", name="AND Gate", loc="(400,300)", attrs={"inputs": 3, "facing": "south"})
        ports = self.call("get_component_ports", loc="(400,300)", name="AND Gate")["components"][0]["ports"]
        self.assertEqual(len(ports), 4)
        self.call("restore_backup", backup=result["backup"])
        self.assertEqual(self.file.read_bytes(), before)
        for attrs in ({"no_such_attr": 1}, {"facing": "diagonal"}, {"width": 0}, {"negate0": "maybe"}):
            self.rejected("add_component", name="AND Gate", loc="(400,300)", attrs=attrs)
        self.rejected("add_component", name="Nonexistent Gate", loc="(400,300)")
        self.rejected("add_component", name="AND Gate", loc="(401,300)")

    def test_complete_full_adder_all_eight_inputs(self):
        def n(name, *ends):
            return {"name": name, "endpoints": [{"id": ident, "port": port} for ident, port in ends]}
        for a in range(2):
            for b in range(2):
                for cin in range(2):
                    self.fresh(f"adder-{a}{b}{cin}.circ")
                    nodes = [{"id": label, "name": "Constant", "attrs": {"value": hex(value)}} for label, value in (("A", a), ("B", b), ("Cin", cin))]
                    nodes += [{"id": ident, "name": gate} for ident, gate in (("x1", "XOR Gate"), ("x2", "XOR Gate"), ("a1", "AND Gate"), ("a2", "AND Gate"), ("or", "OR Gate"))]
                    nodes += [{"id": label, "name": "Pin", "attrs": {"output": True, "label": label}} for label in ("S", "C", "halt")]
                    nodes += [{"id": "stop", "name": "Power"}]
                    nets = [n("A", ("A", 0), ("x1", 1), ("a1", 1)), n("B", ("B", 0), ("x1", 2), ("a1", 2)),
                            n("Cin", ("Cin", 0), ("x2", 2), ("a2", 2)), n("axb", ("x1", 0), ("x2", 1), ("a2", 1)),
                            n("ab", ("a1", 0), ("or", 1)), n("abc", ("a2", 0), ("or", 2)),
                            n("S", ("x2", 0), ("S", 0)), n("C", ("or", 0), ("C", 0)), n("stop", ("stop", 0), ("halt", 0))]
                    result = self.call("build_circuit", components=nodes, nets=nets)
                    self.assertTrue(result["runtime_checked"])
                    table = self.call("get_simulation_table", timeout_sec=3)
                    self.assertTrue(table["complete"], table)
                    values = dict(zip(table["header"], table["rows"][-1]))
                    total = a + b + cin
                    self.assertEqual(values, {"S": str(total % 2), "C": str(total // 2)})

    def test_wires_connectivity_width_driver_and_transaction_failure(self):
        self.fresh()
        nodes = [{"id": "src", "name": "Power", "loc": "(100,100)"}, {"id": "out", "name": "Pin", "loc": "(300,100)", "attrs": {"output": True, "label": "Q"}}]
        self.call("build_circuit", components=nodes, nets=[{"name": "Q", "endpoints": [{"id": "src", "port": 0}, {"id": "out", "port": 0}], "waypoints": []}])
        self.assertEqual(len(s.parse_project(self.file)["circuits"][0]["wires"]), 1)
        self.rejected("connect_ports", nets=[{"name": "bad", "endpoints": [{"name": "Power", "loc": "(100,100)", "port": 9}, {"name": "Pin", "loc": "(300,100)", "port": 0}]}])
        before = self.file.read_bytes()
        net = {"name": "mismatch", "endpoints": [{"id": "a", "port": 0}, {"id": "b", "port": 0}]}
        self.rejected("build_circuit", components=[{"id": "a", "name": "Constant", "attrs": {"width": 8}}, {"id": "b", "name": "Pin", "attrs": {"output": True}}], nets=[net])
        self.rejected("build_circuit", components=[{"id": "a", "name": "Power"}, {"id": "b", "name": "Ground"}], nets=[net])
        with patch.object(s, "atomic_replace", side_effect=OSError("injected")):
            self.rejected("add_component", name="Ground", loc="(500,500)")
        self.assertEqual(before, self.file.read_bytes())

    def test_hierarchy_and_recursive_rejection(self):
        self.fresh()
        self.call("build_project", main="main", circuits=[{"name": "main", "components": [{"id": "sub", "name": "child"}]},
                        {"name": "child", "components": [{"id": "in", "name": "Pin", "loc": "(100,100)", "attrs": {"label": "A"}},
                           {"id": "out", "name": "Pin", "loc": "(300,100)", "attrs": {"output": True, "label": "Q"}}],
                         "nets": [{"name": "pass", "endpoints": [{"id": "in", "port": 0}, {"id": "out", "port": 0}]}]}])
        self.assertEqual(len(self.call("get_component_ports", name="child")["components"][0]["ports"]), 2)
        self.rejected("add_component", circuit="child", name="main", loc="(500,500)")
        self.call("add_circuit", name="new-child")
        self.rejected("add_circuit", name="new-child")

    def test_complete_clock_counter_register_and_mux(self):
        self.fresh()
        nodes = [{"id": "counter", "name": "Counter", "attrs": {"width": 2, "max": "0x3"}},
                 {"id": "register", "name": "Register", "attrs": {"width": 4}},
                 {"id": "mux", "name": "Multiplexer", "attrs": {"width": 4}},
                 {"id": "clock", "name": "Clock"}, {"id": "low", "name": "Ground"}, {"id": "high", "name": "Power"},
                 {"id": "zero2", "name": "Constant", "attrs": {"width": 2, "value": "0x0"}},
                 {"id": "data", "name": "Constant", "attrs": {"width": 4, "value": "0x3"}},
                 {"id": "alternative", "name": "Constant", "attrs": {"width": 4, "value": "0xc"}}]
        nodes += [{"id": ident, "name": "Pin", "attrs": {"output": True, "label": ident, "width": width}} for ident, width in (("count", 2), ("stored", 4), ("selected", 4), ("halt", 1))]
        def net(name, *ends):
            return {"name": name, "endpoints": [{"id": ident, "port": port} for ident, port in ends]}
        nets = [net("clock", ("clock", 0), ("counter", 2), ("register", 2)),
                net("ground", ("low", 0), ("counter", 3), ("counter", 4), ("counter", 5), ("counter", 7), ("register", 3), ("register", 5), ("register", 6)),
                net("enable", ("high", 0), ("counter", 8), ("register", 4), ("mux", 2)),
                net("counter_data", ("zero2", 0), ("counter", 1)), net("register_data", ("data", 0), ("register", 1)),
                net("stored", ("register", 0), ("stored", 0), ("mux", 0)), net("alternative", ("alternative", 0), ("mux", 1)),
                net("selected", ("mux", 3), ("selected", 0)), net("count", ("counter", 0), ("count", 0)), net("stop", ("counter", 6), ("halt", 0))]
        self.call("build_circuit", components=nodes, nets=nets)
        table = self.call("get_simulation_table", timeout_sec=5)
        self.assertTrue(table["complete"], table)
        columns = [dict(zip(table["header"], row)) for row in table["rows"]]
        self.assertEqual(columns[-1], {"count": "3", "stored": "3", "select": "c"})
        self.assertTrue({"0", "1", "2", "3"} <= {row["count"] for row in columns})
        self.assertEqual(table["value_radix"], 16)

    def test_rom_contents_and_all_builtin_types(self):
        self.fresh()
        result = s.call_tool("list_component_catalog", {})
        entries = json.loads(result["content"][0]["text"])["components"]
        nodes = [{"id": str(i), "name": x["name"], "library": x["library"]} for i, x in enumerate(entries)]
        result = self.call("build_circuit", components=nodes, dry_run=True)
        self.assertFalse(self.file.exists())
        self.assertEqual(result["added_components"]["main"], len(entries))
        self.call("build_circuit", components=[{"id": "rom", "name": "ROM", "attrs": {"addrWidth": 2, "dataWidth": 4, "contents": "addr/data: 2 4\n1 2 3 4\n"}}])
        rom = self.call("get_component_ports", name="ROM")["components"][0]
        self.assertEqual(rom["attributes"]["contents"], "addr/data: 2 4\n1 2 3 4\n")

    def test_accidental_join_and_builder_bom_restore(self):
        raw = ("\ufeff" + BASE.replace("\n", "\r\n")).encode("utf-8")
        self.file.write_bytes(raw)
        added = self.call("add_component", name="Ground", loc="(400,300)")
        self.assertTrue(self.file.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", self.file.read_bytes().replace(b"\r\n", b""))
        self.call("restore_backup", backup=added["backup"])
        self.assertEqual(raw, self.file.read_bytes())
        self.fresh("joined.circ")
        nodes = [{"id": "src", "name": "Power", "loc": "(100,100)"},
                 {"id": "dst", "name": "Pin", "loc": "(300,100)", "attrs": {"output": True}},
                 {"id": "other", "name": "Pin", "loc": "(200,100)", "attrs": {"output": True}}]
        result = s.call_tool("build_circuit", {"file": str(self.file), "components": nodes,
            "nets": [{"name": "bad", "endpoints": [{"id": "src", "port": 0}, {"id": "dst", "port": 0}], "waypoints": []}]})
        self.assertTrue(result["isError"], result)
        self.assertFalse(self.file.exists())

    def test_old_source_counter_ports_and_stdio_builder(self):
        result = self.call("add_component", name="Counter", loc="(500,300)", attrs={"width": 2})
        counter = self.call("get_component_ports", name="Counter")["components"][0]
        self.assertEqual(counter["attributes"]["behavior"], "old")
        self.call("restore_backup", backup=result["backup"])
        self.fresh("stdio-built.circ")
        args = {"file": str(self.file), "components": [{"id": "p", "name": "Power", "loc": "(100,100)"},
                 {"id": "halt", "name": "Pin", "loc": "(300,100)", "attrs": {"output": True, "label": "halt"}}],
                "nets": [{"name": "stop", "endpoints": [{"id": "p", "port": 0}, {"id": "halt", "port": 0}], "waypoints": []}]}
        requests = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": value}}
                    for i, (name, value) in enumerate((("build_circuit", args), ("get_component_ports", {"file": str(self.file)}), ("get_simulation_table", {"file": str(self.file), "timeout_sec": 3})), 1)]
        process = subprocess.run([sys.executable, str(SERVER)], input="".join(json.dumps(x) + "\n" for x in requests), capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        replies = [json.loads(line)["result"] for line in process.stdout.splitlines()]
        self.assertEqual(len(replies), 3)
        self.assertTrue(all(not r["isError"] for r in replies), replies)
        self.assertTrue(json.loads(replies[-1]["content"][0]["text"])["complete"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
