#!/usr/bin/env python3
"""Standard-library setup helper; never edits an existing client configuration."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = 'logisim-classic-lab-workflow'
CLIENTS = ('generic', 'codex', 'claude', 'cursor', 'gemini', 'opencode', 'zcode', 'harness', 'vscode', 'copilot')


def server_module():
    sys.path.insert(0, str(ROOT / 'mcp'))
    spec = importlib.util.spec_from_file_location('logisim_setup_server', ROOT / 'mcp/server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configuration(client, workspace, exe=None):
    env = {'LOGISIM_MCP_WORKSPACE': str(Path(workspace).expanduser().resolve())}
    exe = exe or os.environ.get('LOGISIM_HUST_EXE')
    if exe:
        env['LOGISIM_HUST_EXE'] = str(Path(exe).expanduser().resolve())
    if os.environ.get('LOGISIM_MCP_JAVA'):
        env['LOGISIM_MCP_JAVA'] = str(Path(os.environ['LOGISIM_MCP_JAVA']).expanduser().resolve())
    row = {'command': sys.executable, 'args': [str(ROOT / 'mcp/server.py')], 'env': env}
    name = 'logisim-classic-lab'
    if client == 'codex':
        # JSON basic strings are valid TOML strings, including Windows escapes.
        q = lambda value: json.dumps(value, ensure_ascii=False)
        lines = ['[mcp_servers.' + name + ']', 'command = ' + q(row['command']),
                 'args = [' + q(row['args'][0]) + ']', '', '[mcp_servers.' + name + '.env]']
        return '\n'.join(lines + [key + ' = ' + q(value) for key, value in env.items()]) + '\n'
    if client == 'harness':
        # JSON double-quoted scalars are also valid YAML. All values are literal.
        q = lambda value: json.dumps(value, ensure_ascii=False)
        lines = ['- insert:', '    - id: mcp-logisim-classic-lab',
                 "      name: '@deepseek-ai/dsh-mcp-client'", '      config:',
                 '        serverName: ' + name, '        transport: stdio',
                 '        command: ' + q(row['command']), '        args: [' + q(row['args'][0]) + ']',
                 '        env:']
        return '\n'.join(lines + ['          ' + key + ': ' + q(value) for key, value in env.items()]) + '\n'
    if client == 'opencode':
        result = {'$schema': 'https://opencode.ai/config.json', 'mcp': {name: {
            'type': 'local', 'command': [row['command'], *row['args']], 'environment': env, 'enabled': True}}}
    elif client == 'zcode':
        result = {'mcp': {'servers': {name: row}}}
    elif client == 'vscode':
        result = {'servers': {name: {'type': 'stdio', **row}}}
    else:
        result = {'mcpServers': {name: row}}
    return json.dumps(result, ensure_ascii=False, indent=2) + '\n'


def install_skill(destination):
    destination = Path(destination).expanduser().resolve()
    if destination.name != SKILL_NAME:
        raise ValueError('destination must end in ' + SKILL_NAME)
    # Existing installs are never replaced; users can compare/update deliberately.
    destination.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copytree(ROOT / 'skills' / SKILL_NAME, destination, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.bak', '*.bak-*', '*.tmp'))
    except BaseException:
        # Keep an incomplete install for inspection rather than deleting a tree
        # another process might have touched. Report failure to the caller.
        raise
    return destination


def compile_bridges(exe, javac=None):
    exe = Path(exe).expanduser().resolve()
    if not exe.is_file():
        raise ValueError('Logisim executable/JAR does not exist')
    javac = javac or shutil.which('javac')
    if not javac:
        home = os.environ.get('JAVA_HOME')
        if home:
            javac = next((str(p) for p in (Path(home)/'bin/javac', Path(home)/'bin/javac.exe') if p.is_file()), None)
    if not javac:
        raise ValueError('javac not found; install a JDK or pass --javac')
    version = subprocess.run([javac, '-version'], capture_output=True, timeout=15, check=True)
    text = (version.stdout + version.stderr).decode('utf-8', 'replace')
    flags = ['-source', '8', '-target', '8'] if 'javac 1.8' in text else ['--release', '8']
    sources = [str(ROOT / 'mcp' / name) for name in ('PortProbe.java', 'CircuitImage.java', 'PropagationTrace.java')]
    subprocess.run([javac, *flags, '-encoding', 'UTF-8', '-classpath', str(exe), *sources], check=True, timeout=90)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('doctor', help='report runtime and compiled-bridge availability')
    compile_parser = commands.add_parser('compile', help='compile Java bridges locally')
    compile_parser.add_argument('--exe', default=os.environ.get('LOGISIM_HUST_EXE'))
    compile_parser.add_argument('--javac')
    install_parser = commands.add_parser('install-skill', help='copy the one canonical Skill into a new destination')
    install_parser.add_argument('--destination', required=True)
    config_parser = commands.add_parser('config', help='print a client entry for manual merging')
    config_parser.add_argument('--client', required=True, choices=CLIENTS)
    config_parser.add_argument('--workspace', required=True)
    config_parser.add_argument('--exe', default=None)
    config_parser.add_argument('--output', help='write a NEW local file; contains your absolute paths')
    args = parser.parse_args(argv)
    try:
        if args.action == 'doctor':
            s = server_module()
            result = s.tool_env_info({'probe_version': True})
            result['bridges'] = {name: (ROOT/'mcp'/name).is_file() for name in ('PortProbe.class', 'CircuitImage.class', 'PropagationTrace.class')}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get('exe_exists') and result.get('java') and result.get('probe', {}).get('ok') and all(result['bridges'].values()) else 1
        if args.action == 'compile':
            if not args.exe:
                parser.error('set LOGISIM_HUST_EXE or pass --exe')
            compile_bridges(args.exe, args.javac)
            print('Compiled three Java 8 bridges (local output only).')
        elif args.action == 'install-skill':
            print(install_skill(args.destination))
        elif args.action == 'config':
            workspace = Path(args.workspace).expanduser().resolve()
            if not workspace.is_dir():
                raise ValueError('workspace must be an existing directory')
            rendered = configuration(args.client, workspace, args.exe)
            if args.output:
                with Path(args.output).expanduser().open('x', encoding='utf-8', newline='\n') as stream:
                    stream.write(rendered)
                print('Wrote local configuration; merge the entry without replacing other settings.')
            else:
                print(rendered, end='')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('setup: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
