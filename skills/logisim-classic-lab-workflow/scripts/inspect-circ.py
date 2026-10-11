#!/usr/bin/env python3
"""Inspect classic Logisim 2.7 (.circ) files used by Logisim-HUST / 计组虚拟实验.

Usage:
  python inspect-circ.py lab.circ                 # summary of the main circuit
  python inspect-circ.py lab.circ --circuit sub   # summary of one named circuit
  python inspect-circ.py lab.circ --all           # every circuit
  python inspect-circ.py lab.circ --json          # full structured dump

Exit codes: 0 ok, 1 usage/IO error, 2 parse error.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter


def parse(path):
    root = ET.parse(path).getroot()
    if root.tag != 'project':
        raise ValueError('not a Logisim project (root <%s>)' % root.tag)

    libs = {}
    for lib in root.findall('lib'):
        libs[lib.get('name')] = lib.get('desc') or ''

    main_el = root.find('main')
    main = main_el.get('name') if main_el is not None else None

    circuits = []
    for c in root.findall('circuit'):
        comps = []
        for comp in c.findall('comp'):
            attrs = {}
            for a in comp.findall('a'):
                attrs[a.get('name')] = a.get('val')
            libid = comp.get('lib')
            comps.append({
                'lib': libid,
                'libdesc': libs.get(libid, libid),
                'name': comp.get('name'),
                'loc': comp.get('loc'),
                'attrs': attrs,
            })
        wires = [{'from': w.get('from'), 'to': w.get('to')} for w in c.findall('wire')]
        circuits.append({'name': c.get('name'), 'components': comps, 'wires': wires})

    return {
        'file': path,
        'source': root.get('source'),
        'version': root.get('version'),
        'libs': libs,
        'main': main,
        'circuits': circuits,
    }


def pin_info(comp):
    """Return (label, direction, width) for a wiring Pin component."""
    a = comp['attrs']
    label = a.get('label', '')
    direction = 'out' if str(a.get('output', 'false')).lower() == 'true' else 'in'
    width = a.get('width', '1')
    return label, direction, width


def print_circuit(circ, all_names=()):
    comps, wires = circ['components'], circ['wires']
    print('电路 [%s]  元件 %d, 连线 %d' % (circ['name'], len(comps), len(wires)))

    pins = [c for c in comps if c['name'] == 'Pin']
    if pins:
        print('  引脚 %d:' % len(pins))
        for c in sorted(pins, key=lambda x: (pin_info(x)[0] or '~', x['loc'] or '')):
            label, direction, width = pin_info(c)
            print('    %-10s %-3s w%-3s %s' % (label or '(无名)', direction, width, c['loc']))
    else:
        print('  引脚 0: (无 Pin 元件)')

    by_lib = Counter('%s/%s' % (c['name'], c['libdesc']) for c in comps)
    print('  元件分布: ' + ', '.join('%s×%d' % (k, v) for k, v in sorted(by_lib.items())))

    names = sorted({c['name'] for c in comps if c['name'] in set(all_names)})
    if names:
        print('  引用的子电路: ' + ', '.join(names))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Inspect classic Logisim 2.7 .circ files')
    ap.add_argument('circ_file')
    ap.add_argument('--circuit', help='circuit name to show (default: main circuit)')
    ap.add_argument('--all', action='store_true', help='show every circuit')
    ap.add_argument('--json', action='store_true', help='dump parsed structure as JSON')
    args = ap.parse_args(argv)

    try:
        data = parse(args.circ_file)
    except (OSError, ET.ParseError, ValueError) as exc:
        print('ERROR: %s' % exc, file=sys.stderr)
        return 2

    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write('\n')
        return 0

    print('文件: %s' % data['file'])
    print('格式: project source=%s version=%s   主电路=%s' % (data['source'], data['version'], data['main']))
    print('库: ' + ' | '.join('%s=%s' % (k, v) for k, v in sorted(data['libs'].items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 99)))
    print('共 %d 个电路' % len(data['circuits']))
    print('-' * 60)

    if args.all:
        names = [c['name'] for c in data['circuits']]
        for circ in data['circuits']:
            print_circuit(circ, names)
            print('-' * 60)
        return 0

    target = args.circuit or data['main']
    if not target:
        print('未指定 --circuit 且文件中没有 <main>；用 --all 查看全部', file=sys.stderr)
        return 2
    names = [c['name'] for c in data['circuits']]
    for circ in data['circuits']:
        if circ['name'] == target:
            print_circuit(circ, names)
            return 0
    print('ERROR: 找不到电路 %r（可用: %s）' % (target, ', '.join(c['name'] for c in data['circuits'])), file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
