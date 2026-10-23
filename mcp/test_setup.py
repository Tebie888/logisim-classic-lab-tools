"""Install/configuration helper tests; no third-party runtimes required."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('logisim_setup_under_test', ROOT/'scripts/setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
release_spec = importlib.util.spec_from_file_location('logisim_release_under_test', ROOT/'scripts/check_release.py')
release = importlib.util.module_from_spec(release_spec)
release_spec.loader.exec_module(release)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='logisim-setup-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_installed_skill_is_self_contained_and_existing_install_is_preserved(self):
        destination = self.root/setup.SKILL_NAME
        setup.install_skill(destination)
        self.assertTrue((destination/'SKILL.md').is_file())
        self.assertTrue((destination/'scripts/inspect-circ.py').is_file())
        self.assertTrue((destination/'propagation-measurement.md').is_file())
        before = (destination/'SKILL.md').read_bytes()
        with self.assertRaises(FileExistsError):
            setup.install_skill(destination)
        self.assertEqual((destination/'SKILL.md').read_bytes(), before)

    def test_generated_json_formats_preserve_exact_paths_without_shell_quoting(self):
        workspace = self.root/'circuits with spaces'
        workspace.mkdir()
        exe = workspace/'classic runtime.jar'
        for client in ('generic', 'claude', 'cursor', 'gemini', 'copilot', 'zcode', 'vscode', 'opencode'):
            with self.subTest(client=client):
                result = json.loads(setup.configuration(client, workspace, str(exe)))
                if client == 'zcode': row = result['mcp']['servers']['logisim-classic-lab']
                elif client == 'vscode': row = result['servers']['logisim-classic-lab']
                elif client == 'opencode': row = result['mcp']['logisim-classic-lab']
                else: row = result['mcpServers']['logisim-classic-lab']
                env = row.get('env', row.get('environment'))
                self.assertEqual(env['LOGISIM_MCP_WORKSPACE'], str(workspace.resolve()))
                self.assertEqual(env['LOGISIM_HUST_EXE'], str(exe.resolve()))
                if client != 'opencode':
                    self.assertEqual(row['command'], sys.executable)
                    self.assertEqual(row['args'], [str(ROOT/'mcp/server.py')])
                else:
                    self.assertEqual(row['command'], [sys.executable, str(ROOT/'mcp/server.py')])

    def test_config_output_is_exclusive_and_workspace_must_exist(self):
        output = self.root/'config.json'
        output.write_text('preserve', encoding='utf-8')
        result = subprocess.run([sys.executable, str(ROOT/'scripts/setup.py'), 'config',
            '--client', 'generic', '--workspace', str(self.root), '--output', str(output)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(output.read_text(), 'preserve')
        result = subprocess.run([sys.executable, str(ROOT/'scripts/setup.py'), 'config',
            '--client', 'generic', '--workspace', str(self.root/'absent')], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)

    def test_config_stdout_is_utf8_even_with_ascii_launch_environment(self):
        workspace = self.root/'电路空间'
        workspace.mkdir()
        result = subprocess.run([sys.executable, str(ROOT/'scripts/setup.py'), 'config',
            '--client', 'generic', '--workspace', str(workspace)],
            env=dict(os.environ, PYTHONIOENCODING='ascii'), capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.decode('utf-8'))
        self.assertEqual(payload['mcpServers']['logisim-classic-lab']['env']['LOGISIM_MCP_WORKSPACE'], str(workspace.resolve()))

    def test_generated_codex_toml_is_parseable_when_parser_available(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest('TOML round-trip uses Python 3.11+ test support only')
        result = tomllib.loads(setup.configuration('codex', self.root))
        self.assertEqual(result['mcp_servers']['logisim-classic-lab']['args'], [str(ROOT/'mcp/server.py')])

    def test_compile_selects_java8_target_without_a_shell(self):
        executable = self.root/'classic.jar'
        executable.touch()
        for version, flags in ((b'javac 1.8.0_442', ['-source', '8', '-target', '8']),
                               (b'javac 17.0.20', ['--release', '8'])):
            with self.subTest(version=version), patch.object(setup.subprocess, 'run') as run:
                run.return_value.stdout = version
                run.return_value.stderr = b''
                setup.compile_bridges(executable, 'javac')
                arguments = run.call_args_list[-1].args[0]
                self.assertEqual(arguments[1:1+len(flags)], flags)
                self.assertIn(str(ROOT/'mcp/PropagationTrace.java'), arguments)
                self.assertNotIn('shell', run.call_args_list[-1].kwargs)

    def test_release_scan_redacts_sensitive_values_and_rejects_unexpected_files(self):
        secret = b'gh' + b'p_' + b'a'*36
        path = b'C:' + b'/Users/' + b'example-user/private'
        windows = path.replace(b'/', bytes([92]))
        escaped = json.dumps(windows.decode()).encode()
        for data, expected in ((secret, 'credential'), (path, 'private_windows_home'),
                               (windows, 'private_windows_home'), (escaped, 'private_windows_home')):
            findings = release.scan('test.py', data)
            self.assertTrue(any(expected in finding for finding in findings))
            self.assertNotIn(data.decode(), repr(findings))
        self.assertTrue(release.scan('program.jar', b'data'))
        self.assertTrue(release.scan('large.txt', b'x'*(release.MAX_BYTES+1)))
        self.assertEqual(release.scan('README.md', b'Generic public documentation.'), [])

    def test_release_scan_flags_png_metadata_and_preserves_safe_example(self):
        safe = (ROOT/'examples/half-adder-preview.png').read_bytes()
        self.assertEqual(release.scan('example.png', safe), [])
        metadata = b'tEXt' + b'note\0private metadata'
        chunk = (len(metadata)-4).to_bytes(4, 'big') + metadata + b'\x00'*4
        altered = safe[:-12] + chunk + safe[-12:]
        self.assertTrue(any('metadata' in finding for finding in release.scan('example.png', altered)))

    @unittest.skipUnless(os.name == 'nt', 'Windows batch launcher regression')
    def test_windows_launcher_returns_the_child_exit_code(self):
        shell = shutil.which('powershell.exe')
        if not shell:
            self.skipTest('Windows PowerShell not installed')
        launcher = ROOT/'skills/logisim-classic-lab-workflow/scripts/launch-logisim.cmd'
        # Use a harmless Python child to exercise the console-launch branch.
        quoted = str(launcher).replace("'", "''")
        result = subprocess.run([shell, '-NoProfile', '-Command',
            "& '" + quoted + "' '-c' 'raise SystemExit(7)'; exit $LASTEXITCODE"],
            env=dict(os.environ, LOGISIM_HUST_EXE=sys.executable), capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 7, result.stderr)


if __name__ == '__main__':
    unittest.main()
