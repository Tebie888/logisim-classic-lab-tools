#!/usr/bin/env python3
"""Review an explicit publication allowlist; never stages or uploads files."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT/'scripts/publish-allowlist.txt'
MAX_BYTES = 2 * 1024 * 1024
PATTERNS = {
    'credential': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)'),
    'private_windows_home': re.compile(rb'[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+[^\\/\s<>"\']+', re.I),
    'private_posix_home': re.compile(rb'/(?:Users|home)/[^/\s<>"\']+/'),
    'email': re.compile(rb'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
}
ALLOWED_SUFFIXES = {'.py', '.java', '.md', '.json', '.toml', '.yml', '.cmd', '.ps1', '.circ', '.png', '.txt'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def read_allowlist():
    names = [line.strip() for line in ALLOWLIST.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.startswith('#')]
    if len(names) != len(set(names)):
        raise ValueError('duplicate allowlist entries')
    for name in names:
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name:
            raise ValueError('allowlist paths must be normalized repository-relative paths')
    return set(names)


def scan(name, data):
    findings = []
    if len(data) > MAX_BYTES:
        findings.append('file exceeds 2 MiB review limit')
    path = Path(name)
    if path.suffix not in ALLOWED_SUFFIXES and name not in {'.gitignore', '.gitattributes', 'LICENSE'}:
        findings.append('unexpected publication file type')
    if path.suffix == '.png':
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            findings.append('invalid PNG header')
        offset = 8
        while offset + 12 <= len(data):
            length = int.from_bytes(data[offset:offset+4], 'big')
            kind = data[offset+4:offset+8]
            if kind in {b'tEXt', b'zTXt', b'iTXt', b'eXIf'}:
                findings.append('PNG contains metadata requiring manual review')
            offset += 12 + length
        if offset != len(data):
            findings.append('PNG chunk boundary/trailing data requires review')
    else:
        try:
            data.decode('utf-8-sig')
        except UnicodeError:
            findings.append('non-UTF-8 publication text')
        for label, pattern in PATTERNS.items():
            if pattern.search(data):
                findings.append(label + ' pattern (value redacted)')
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--staged', action='store_true', help='inspect staged blobs, not working copies')
    scope.add_argument('--revision', help='inspect all files from an exact Git revision')
    args = parser.parse_args(argv)
    try:
        allowed = read_allowlist()
        if args.staged:
            names = git('diff', '--cached', '--name-only', '-z').decode().strip('\0').split('\0')
        elif args.revision:
            names = git('ls-tree', '-r', '--name-only', '-z', args.revision).decode().strip('\0').split('\0')
        else:
            names = git('ls-files', '--cached', '--others', '--exclude-standard', '-z').decode().strip('\0').split('\0')
        names = sorted(set(filter(None, names)))
        problems = {}
        for name in names:
            findings = []
            if name not in allowed:
                findings.append('not on publication allowlist')
            path = ROOT/name
            if not args.revision and path.is_symlink():
                findings.append('publication symlink is not allowed')
            if args.staged or args.revision:
                revision = '' if args.staged else args.revision
                mode = git('ls-files', '-s', '--', name) if args.staged else git('ls-tree', revision, '--', name)
                if mode.startswith((b'120000', b'160000')):
                    findings.append('symlink/submodule is not allowed')
                try:
                    data = git('show', revision + ':' + name)
                except subprocess.CalledProcessError:
                    findings.append('deleted or unreadable blob requires manual review')
                    data = b''
            else:
                data = path.read_bytes()
            findings.extend(scan(name, data))
            if findings:
                problems[name] = findings
        result = {'ok': not problems, 'scope': 'staged' if args.staged else args.revision or 'working-tree',
                  'files_checked': len(names), 'allowlist_entries': len(allowed), 'findings': problems,
                  'limits': 'Pattern/size/allowlist checks assist manual review; they cannot prove absence of all sensitive content.'}
        print(json.dumps(result, indent=2))
        return 0 if result['ok'] else 1
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('release check failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
