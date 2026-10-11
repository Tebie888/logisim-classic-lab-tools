"""Suggest nearby wire-endpoint offsets for Logisim-HUST components.

For every component instance we take its `loc` and every wire endpoint, and
tally the offset (endpoint - loc) for endpoints within +/-100 units. Offsets
that occur many times are candidates, not verified ports: endpoints belonging
to nearby components are included. Do not generate wiring from these alone.

Usage: python port-geometry.py <dir-or-circ> [<dir-or-circ> ...]
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict


def parse_loc(text):
    m = re.fullmatch(r'\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)', (text or '').strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def collect(path, tally, instances):
    root = ET.parse(path).getroot()
    libs = {lib.get('name'): (lib.get('desc') or '') for lib in root.findall('lib')}
    for circuit in root.findall('circuit'):
        endpoints = set()
        for w in circuit.findall('wire'):
            for k in ('from', 'to'):
                p = parse_loc(w.get(k))
                if p:
                    endpoints.add(p)
        for comp in circuit.findall('comp'):
            loc = parse_loc(comp.get('loc'))
            if not loc:
                continue
            name = comp.get('name')
            lib = libs.get(comp.get('lib'), comp.get('lib'))
            attrs = {a.get('name'): a.get('val') for a in comp.findall('a')}
            facing = attrs.get('facing', 'east')
            key = (name, lib, facing, attrs.get('size', '(default)'), attrs.get('inputs', '(default)'))
            instances[key] += 1
            seen = set()
            for ep in endpoints:
                dx, dy = ep[0] - loc[0], ep[1] - loc[1]
                if abs(dx) <= 100 and abs(dy) <= 100 and (dx, dy) not in seen:
                    seen.add((dx, dy))
                    tally[key][(dx, dy)] += 1


def main(argv):
    tally = defaultdict(lambda: defaultdict(int))
    instances = defaultdict(int)
    files = 0
    for arg in argv:
        if os.path.isdir(arg):
            for dirpath, _dirs, names in os.walk(arg):
                for n in names:
                    if n.lower().endswith('.circ'):
                        try:
                            collect(os.path.join(dirpath, n), tally, instances)
                            files += 1
                        except ET.ParseError as exc:
                            print('skip %s: %s' % (n, exc))
        elif os.path.isfile(arg):
            collect(arg, tally, instances)
            files += 1
    print('扫描 %d 个 .circ 文件；覆盖率 >=90%% 的附近端点候选（非已验证端口；按 facing/size/inputs 分组）\n' % files)
    for key in sorted(instances, key=lambda k: -instances[k]):
        n = instances[key]
        if n < 3:
            continue
        ports = [(off, c) for off, c in tally[key].items() if c >= 0.9 * n]
        if not ports:
            continue
        ports.sort(key=lambda kv: -kv[1])
        desc = ', '.join('(%+d,%+d)[%d/%d]' % (dx, dy, c, n) for (dx, dy), c in ports)
        print('%-24s lib=%-10s facing=%-6s size=%s inputs=%s n=%-4d 候选: %s' % (key[0], key[1], key[2], key[3], key[4], n, desc))


if __name__ == '__main__':
    main(sys.argv[1:])
