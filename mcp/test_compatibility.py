"""Portable protocol/security regressions and local 1.4 feature coverage."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_server import BASE, CircuitFixture, RuntimeFixture, s


class CompatibilityTests(CircuitFixture):
    def test_utf16_dtd_is_rejected_before_entity_expansion(self):
        xml = BASE.replace('<?xml version="1.0" encoding="UTF-8"?>',
            '<?xml version="1.0" encoding="UTF-16"?>\n'
            '<!DOCTYPE project [<!ENTITY example "expanded">]>')
        xml = xml.replace('This file is intended', '&example; This file is intended')
        for encoding in ('utf-8', 'utf-16', 'utf-16-le', 'utf-16-be'):
            with self.subTest(encoding=encoding), self.assertRaises(s.ToolError):
                s.parse_project_bytes(xml.encode(encoding))

    def test_initialize_invalid_version_is_invalid_params_and_session_survives(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for index, version in enumerate(([], {}, 7, None), 1):
                s.handle({'jsonrpc': '2.0', 'id': index, 'method': 'initialize',
                          'params': {'protocolVersion': version}})
            s.handle({'jsonrpc': '2.0', 'id': 5, 'method': 'ping'})
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r['error']['code'] for r in replies[:4]], [-32602] * 4)
        self.assertEqual(replies[-1]['result'], {})

    def test_java_home_without_path_java_accepts_posix_executable(self):
        home = self.root / 'jdk'
        (home / 'bin').mkdir(parents=True)
        java = home / 'bin' / 'java'
        java.touch()
        with patch.dict(os.environ, {'JAVA_HOME': str(home), 'LOGISIM_MCP_JAVA': ''}), \
             patch.object(s.shutil, 'which', return_value=None), \
             patch.object(s, '_registry_java_homes', return_value=[]):
            self.assertEqual(Path(s.find_java()), java.resolve())

    def test_subcircuit_named_pin_is_not_a_top_level_pin(self):
        text = BASE.replace('name="untouched"', 'name="Pin"')
        text = text.replace('  </circuit>',
            '<comp name="Pin" loc="(500,500)"><a name="label" val="module"/></comp>\n  </circuit>', 1)
        self.file.write_text(text, encoding='utf-8')
        self.assertEqual(self.call('list_pins')['pin_count'], 1)
        self.assertEqual(self.call('describe_circuit')['subcircuit_refs'], ['Pin'])
        self.assertEqual(self.call('describe_circuit')['pin_count'], 1)

    def test_builtin_same_name_as_circuit_is_not_a_subcircuit_reference(self):
        self.file.write_text(BASE.replace('name="untouched"', 'name="Power"'), encoding='utf-8')
        self.assertEqual(self.call('describe_circuit')['subcircuit_refs'], [])
        self.assertEqual(self.call('validate_circuit')['subcircuit_refs'], [])

    def test_atomic_replace_retries_only_transient_windows_lock(self):
        before = self.file.read_bytes()
        candidate = before.replace(b'halt', b'done')
        locked = PermissionError('simulated sharing violation')
        locked.winerror = 32
        replace = s.os.replace
        attempts = []
        def transient(src, dst):
            attempts.append(1)
            if len(attempts) == 1:
                raise locked
            replace(src, dst)
        with patch.object(s.os, 'replace', side_effect=transient):
            s.atomic_replace(self.file, candidate, before)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.file.read_bytes(), candidate)

    def test_external_change_during_replace_retry_cancels_commit(self):
        before = self.file.read_bytes()
        external = before.replace(b'halt', b'external')
        locked = PermissionError('simulated sharing violation')
        locked.winerror = 32
        def concurrent(src, dst):
            self.file.write_bytes(external)
            raise locked
        with patch.object(s.os, 'replace', side_effect=concurrent), self.assertRaises(s.ToolError):
            s.atomic_replace(self.file, before.replace(b'halt', b'candidate'), before)
        self.assertEqual(self.file.read_bytes(), external)
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_runtime_library_traversal_is_rejected_before_java_starts(self):
        text = BASE.replace('<main', '<lib name="9" desc="file#../outside.circ"/><main', 1)
        self.file.write_text(text, encoding='utf-8')
        with patch.object(s.subprocess, 'Popen') as launch:
            result = s.call_tool('simulate_tty', {'file': str(self.file)})
        self.assertTrue(result['isError'])
        self.assertIn('工作区', result['content'][0]['text'])
        launch.assert_not_called()

    def test_fenced_runtime_jar_library_requires_explicit_trust(self):
        text = BASE.replace('<main', '<lib name="9" desc="jar#plugin.jar#Example"/><main', 1)
        self.file.write_text(text, encoding='utf-8')
        (self.root / 'plugin.jar').touch()
        with patch.object(s.subprocess, 'Popen') as launch:
            result = s.call_tool('simulate_tty', {'file': str(self.file)})
        self.assertTrue(result['isError'])
        self.assertIn('LOGISIM_MCP_ALLOW_JAR_LIBRARIES', result['content'][0]['text'])
        launch.assert_not_called()

    def test_transitive_external_circuit_libraries_stay_in_fence(self):
        library = self.root / 'library.circ'
        library.write_text(BASE.replace('<main', '<lib name="8" desc="file#../escape.circ"/><main', 1), encoding='utf-8')
        self.file.write_text(BASE.replace('<main', '<lib name="9" desc="file#library.circ"/><main', 1), encoding='utf-8')
        with self.assertRaises(s.ToolError):
            s.check_runtime_libraries(self.file)

    def test_fenced_local_library_and_trusted_jar_are_supported(self):
        library = self.root / 'library.circ'
        library.write_text(BASE, encoding='utf-8')
        text = BASE.replace('<main', '<lib name="9" desc="file#library.circ"/><main', 1)
        self.file.write_text(text, encoding='utf-8')
        s.check_runtime_libraries(self.file)
        (self.root / 'plugin.jar').touch()
        self.file.write_text(text.replace('file#library.circ', 'jar#plugin.jar#Example'), encoding='utf-8')
        with patch.dict(os.environ, {'LOGISIM_MCP_ALLOW_JAR_LIBRARIES': '1'}):
            s.check_runtime_libraries(self.file)

    def test_hust_gui_source_suffix_and_classic_sources_preserve_bytes(self):
        for source in ('2.3.2', '2.6.2.165', '2.7.1', '2.15.0.2', '2.15.0.2.exe'):
            with self.subTest(source=source):
                raw = BASE.replace('source="2.7.1"', 'source="' + source + '"').encode()
                self.file.write_bytes(raw)
                self.assertTrue(self.call('validate_circuit')['ok'])
                self.call('add_pin', loc='(300,300)', dry_run=True)
                self.assertEqual(self.file.read_bytes(), raw)
        for source in ('4.0.0', '2.7.1.exe', '2.15.0.2.exe.extra'):
            self.assertFalse(s.supported_source(source))

    def test_every_runtime_read_preflights_external_library_paths(self):
        self.file.write_text(BASE.replace('<main', '<lib name="9" desc="file#../escape.circ"/><main', 1), encoding='utf-8')
        cases = [('get_component_ports', {}), ('validate_circuit', {'runtime': True}),
                 ('check_connections', {}), ('export_circuit_image', {'output': str(self.root/'out.png')}),
                 ('trace_propagation', {'output_dir': str(self.root/'trace'), 'initial_inputs': {}, 'inputs': {}, 'signals': ['halt']})]
        for name, args in cases:
            with self.subTest(name=name), patch.object(s.subprocess, 'Popen') as launch:
                result = s.call_tool(name, {'file': str(self.file), **args})
                self.assertTrue(result['isError'])
                self.assertIn('工作区', result['content'][0]['text'])
                launch.assert_not_called()

    def test_builder_detects_unrequested_port_at_requested_endpoint(self):
        data = s.parse_project_bytes(BASE.encode())
        runtime = {'circuits': [{'name': 'main', 'components': [
            {'name': 'Power', 'loc': '(100,100)', 'ports': [{'index': 0, 'loc': '(100,100)'}]},
            {'name': 'Pin', 'loc': '(200,100)', 'ports': [{'index': 0, 'loc': '(200,100)'}]},
            {'name': 'Buffer', 'loc': '(120,100)', 'ports': [{'index': 1, 'loc': '(100,100)'}]},
        ]}]}
        nets = [{'circuit': 'main', 'net': 'intended', 'ports': [
            {'loc': '(100,100)', 'component': 'Power', 'component_loc': '(100,100)', 'index': 0},
            {'loc': '(200,100)', 'component': 'Pin', 'component_loc': '(200,100)', 'index': 0}]}]
        with self.assertRaises(s.ToolError):
            s._builder.check_connectivity(s, data, runtime, nets)


class LocalFeatureTests(RuntimeFixture):
    def setUp(self):
        super().setUp()
        if not Path(s.__file__).with_name('PropagationTrace.class').is_file():
            self.skipTest('Compile PropagationTrace.java to enable propagation tests')
        example = Path(__file__).parents[1] / 'examples/half-adder.circ'
        self.file.write_bytes(example.read_bytes())

    def trace(self, **kwargs):
        args = {'output_dir': str(self.root/'trace'), 'initial_inputs': {'A': 0, 'B': 0},
                'inputs': {'A': 1, 'B': 1}, 'signals': ['A', 'B', 'SUM', 'CARRY'], **kwargs}
        return self.call('trace_propagation', **args)

    def test_native_propagation_stability_anchor_captures_and_source_bytes(self):
        before = self.file.read_bytes()
        result = self.trace(anchor_signal='A', capture_times=[0, 1, 2, 999])
        self.assertTrue(result['complete'], result)
        self.assertEqual(result['signals']['SUM']['final'], '0')
        self.assertEqual(result['signals']['CARRY']['final'], '1')
        self.assertGreaterEqual(result['signals']['CARRY']['final_stable_time'], result['anchor_first_change_time'])
        self.assertGreaterEqual(result['queue_empty_time'], result['signals']['CARRY']['final_stable_time'])
        self.assertIn(999, result['capture_times_not_observed'])
        self.assertTrue((self.root/'trace/capture-0.png').is_file())
        self.assertTrue((self.root/'trace/trace.csv').read_text().startswith('event_index,engine_time_from_request'))
        self.assertEqual(self.file.read_bytes(), before)

    def test_propagation_event_and_time_limits_are_incomplete(self):
        for key in ('max_events', 'max_time'):
            with self.subTest(limit=key):
                result = self.trace(output_dir=str(self.root/key), **{key: 1})
                self.assertFalse(result['complete'], result)
                self.assertFalse(result['ok'])
                self.assertIsNone(result['queue_empty_time'])
                self.assertTrue(all(v['final_stable_time'] is None for v in result['signals'].values()))

    def test_propagation_rejects_output_overwrite_and_bad_signal_without_artifacts(self):
        (self.root/'existing').mkdir()
        (self.root/'existing/sentinel').write_text('preserve')
        self.rejected('trace_propagation', output_dir=str(self.root/'existing'), initial_inputs={}, inputs={}, signals=['A'])
        self.assertEqual((self.root/'existing/sentinel').read_text(), 'preserve')
        for signals in (['A', 'A'], ['missing']):
            self.rejected('trace_propagation', output_dir=str(self.root/'absent'), initial_inputs={}, inputs={}, signals=signals)
            self.assertFalse((self.root/'absent').exists())

    def test_propagation_rejects_output_pin_drive_and_conflicting_crop(self):
        for extra in ({'inputs': {'SUM': 1}}, {'component': {'name': 'Pin', 'loc': '(100,100)'},
                      'viewport': {'x': 0, 'y': 0, 'width': 100, 'height': 100}}):
            args = {'output_dir': str(self.root/'absent'), 'initial_inputs': {'A': 0, 'B': 0},
                    'inputs': {'A': 1}, 'signals': ['SUM'], **extra}
            self.rejected('trace_propagation', **args)
            self.assertFalse((self.root/'absent').exists())

    def test_component_and_viewport_export_keep_circuit_unchanged(self):
        before = self.file.read_bytes()
        circuit = s.parse_project(self.file)['circuits'][0]
        gate = next(c for c in circuit['components'] if c['name'] == 'AND Gate')
        selected = self.call('export_circuit_image', output=str(self.root/'component.png'),
                             component={'name': gate['name'], 'loc': gate['loc']}, inputs={'A': 1, 'B': 1})
        self.assertEqual(selected['export_kind'], 'component')
        self.assertEqual(selected['pin_values']['CARRY'], '1')
        region = self.call('export_circuit_image', output=str(self.root/'viewport.png'),
                          viewport={'x': 0, 'y': 0, 'width': 100, 'height': 100}, padding=0, scale=1)
        self.assertEqual((region['width'], region['height']), (100, 100))
        self.assertEqual(region['export_kind'], 'viewport')
        self.assertEqual(self.file.read_bytes(), before)

    def test_builder_compact_response_retains_network_identities(self):
        self.file.unlink()
        args = {'components': [{'id': 'source', 'name': 'Power', 'loc': '(100,100)'},
                              {'id': 'out', 'name': 'Pin', 'loc': '(400,100)', 'attrs': {'output': True}}],
                'nets': [{'name': 'one', 'endpoints': [{'id': 'source', 'port': 0}, {'id': 'out', 'port': 0}]}],
                'dry_run': True}
        full = self.call('build_circuit', **args)
        short = self.call('build_circuit', **args, include_details=False)
        self.assertEqual(full['connection_manifest'], short['connection_manifest'])
        self.assertEqual(short['net_count'], 1)
        self.assertEqual(short['nets'][0]['port_count'], 2)
        self.assertNotIn('ports', short['nets'][0])
        self.assertNotIn('candidate_xml', short)
        hidden = self.call('build_circuit', **args, include_details=False, include_manifest=False)
        self.assertNotIn('connection_manifest', hidden)
        self.assertFalse(self.file.exists())


if __name__ == '__main__':
    unittest.main()
