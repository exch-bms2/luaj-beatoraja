#!/usr/bin/env python3
"""Normalize javap instruction labels/constant-pool indices, retaining symbolic operands.

This is a structural comparison, not a proof of semantic equivalence. Raw javap
files remain the audit evidence, including exception handlers and declarations.
"""
import argparse
import collections
import difflib
import json
import pathlib
import re


def members(text):
    result = {}
    key = None
    for line in text.splitlines():
        if re.match(r"^  \S", line):
            declaration = line.strip()
            head = declaration.split(' = ')[0]
            if '(' in head:
                name = head.split('(')[0].split()[-1]
            elif declaration == 'static {};':
                name = '<clinit>'
            else:
                name = declaration.split(' = ')[0].rstrip(';').split()[-1]
            key = name
            result[key] = {'declaration': declaration, 'body': []}
        elif key is not None:
            if line.startswith('    descriptor:'):
                descriptor = line.split(': ', 1)[1]
                item = result.pop(key)
                key = key + ':' + descriptor
                item['descriptor'] = descriptor
                result[key] = item
            else:
                result[key]['body'].append(line)
    return result


def normalize(item, collapse_casts=False):
    lines = item['body']
    offsets = {}
    duplicate_offsets = set()
    previous_cast = None
    instruction_count = 0
    for line in lines:
        match = re.match(r'\s*(\d+):\s+([a-z][a-z_0-9]*)\b', line)
        if match:
            cast = re.sub(r'#\d+', '#', line.split('checkcast', 1)[1]).strip() if match[2] == 'checkcast' else None
            if collapse_casts and cast is not None and cast == previous_cast:
                offsets[match[1]] = instruction_count - 1
                duplicate_offsets.add(match[1])
            else:
                offsets[match[1]] = instruction_count
                instruction_count += 1
            previous_cast = cast
    def label(value, allow_end=False):
        if value in offsets:
            return 'L' + str(offsets[value])
        if allow_end:
            return 'END'
        raise ValueError('Unresolved instruction target: ' + value)
    result = []
    for line in lines:
        match = re.match(r'\s*(\d+):\s+([a-z][a-z_0-9]*)\b(.*)', line)
        if match:
            if match[1] in duplicate_offsets:
                continue
            op, operand = match.group(2), match.group(3).strip()
            if op.startswith('if') or op in ('goto', 'goto_w', 'jsr', 'jsr_w'):
                operand = label(operand)
            op = {'ldc_w': 'ldc', 'goto_w': 'goto', 'jsr_w': 'jsr'}.get(op, op)
            operand = re.sub(r'#\d+', '#', operand)
            result.append(' '.join((op + ' ' + operand).split()))
        elif re.match(r'\s*(?:-?\d+|default):\s+\d+\s*$', line):
            case, target = line.strip().split(':')
            result.append(case + ': ' + label(target.strip()))
        elif re.match(r'\s*\d+\s+\d+\s+\d+\s+(?:Class|any)', line):
            a,b,c,kind = line.strip().split(None, 3)
            result.append('handler ' + ' '.join((label(a),label(b, True),label(c),kind)))
    # Constant fields have no instructions but their values are observable.
    if not result and ' = ' in item['declaration']:
        result.append(item['declaration'].split(' = ', 1)[1])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('comparison', type=pathlib.Path)
    parser.add_argument('output', type=pathlib.Path)
    args = parser.parse_args()
    report = json.loads((args.comparison / 'report.json').read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    classified = {}
    for name in report['bytecode_differences']:
        left = members((args.comparison / (name + '.legacy.javap')).read_text())
        right = members((args.comparison / (name + '.candidate.javap')).read_text())
        changed = {}
        for key in sorted(left.keys() | right.keys()):
            a = normalize(left[key]) if key in left else None
            b = normalize(right[key]) if key in right else None
            if a != b:
                changed[key] = {'legacy': a, 'candidate': b}
        casts_only = bool(changed) and all(
            key in left and key in right and normalize(left[key], True) == normalize(right[key], True)
            for key in changed)
        category = 'redundant_checkcast_only' if casts_only else ('instruction_or_constant_difference' if changed else 'compiler_or_declaration_only')
        classified[name] = {'category': category, 'members': changed}
    result = {'legacy_sha256': report['legacy_sha256'], 'candidate_sha256': report['candidate_sha256'],
              'legacy_only': report['legacy_only'], 'candidate_only': report['candidate_only'],
              'classes': classified}
    (args.output / 'normalized.json').write_text(json.dumps(result, indent=2) + '\n')
    for name,item in classified.items():
        if item['members']:
            print(name)
            for key,body in item['members'].items():
                print(' ', key)
                diff = difflib.unified_diff(body['legacy'] or [], body['candidate'] or [], 'legacy', 'candidate')
                (args.output / (name + '.' + re.sub(r'[^\w.$-]', '_', key) + '.diff')).write_text('\n'.join(diff) + '\n')
    print('Summary:', dict(collections.Counter(x['category'] for x in classified.values())))

if __name__ == '__main__':
    main()
