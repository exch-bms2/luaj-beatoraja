#!/usr/bin/env python3
"""Compare raw javap output; compiler differences require manual classification."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import zipfile
from classfile_metadata import inspect

parser = argparse.ArgumentParser()
parser.add_argument("legacy", type=pathlib.Path)
parser.add_argument("candidate", type=pathlib.Path)
parser.add_argument("output", type=pathlib.Path)
parser.add_argument("--expected-legacy-sha256")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

def classes(path):
    with zipfile.ZipFile(path) as jar:
        return {n[:-6].replace("/", ".") for n in jar.namelist() if n.endswith(".class")}

def disassemble(path, names, api=False):
    if not names:
        return {}
    flags = ["-public", "-s"] if api else ["-private", "-c", "-constants", "-s"]
    javap = str(pathlib.Path(os.environ['JAVA_HOME']) / 'bin/javap') if 'JAVA_HOME' in os.environ else 'javap'
    output = subprocess.check_output([javap, *flags, "-classpath", str(path), *sorted(names)], text=True)
    result = {}
    for block in re.split(r'(?=Compiled from ")', output):
        match = re.search(r"(?:class|interface) ([\w.$]+)", block)
        if match:
            result[match.group(1)] = block
    return result

def binary_surface(text):
    """Compare erased public names, JVM descriptors and access modifiers."""
    header = next(line for line in text.splitlines() if re.search(r'\b(class|interface)\b', line))
    while re.search(r'<[^<>]*>', header):
        header = re.sub(r'<[^<>]*>', '', header)
    members = []
    declaration = ''
    modifiers = {'public', 'protected', 'static', 'final', 'abstract', 'native', 'synchronized', 'volatile', 'transient'}
    for line in text.splitlines():
        if re.match(r'^  \S', line):
            declaration = line.strip()
        elif line.startswith('    descriptor:'):
            head = declaration.split('(')[0].rstrip(';')
            name = head.split()[-1]
            flags = sorted(set(head.split()) & modifiers)
            members.append((name, line.strip(), flags))
    return header, sorted(members)

left, right = classes(args.legacy), classes(args.candidate)
report = {
    "legacy_sha256": hashlib.sha256(args.legacy.read_bytes()).hexdigest(),
    "candidate_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
    "legacy_only": sorted(left - right), "candidate_only": sorted(right - left),
    "bytecode_differences": [], "public_api_differences": [], "binary_api_differences": [],
    "common_classes": sorted(left & right), "classfiles": {}, "resources": {}
}
if args.expected_legacy_sha256 and report['legacy_sha256'] != args.expected_legacy_sha256:
    raise SystemExit('Legacy jar SHA-256 does not match the pinned artifact')
with zipfile.ZipFile(args.legacy) as a, zipfile.ZipFile(args.candidate) as b:
    for name in sorted(left & right):
        entry = name.replace('.', '/') + '.class'
        x, y = a.read(entry), b.read(entry)
        report['classfiles'][name] = {'identical_bytes': x == y,
            'legacy_metadata': inspect(x), 'candidate_metadata': inspect(y)}
    resources = {n for n in a.namelist() + b.namelist() if not n.endswith(('/', '.class'))}
    for name in sorted(resources):
        x = a.read(name) if name in a.namelist() else None
        y = b.read(name) if name in b.namelist() else None
        report['resources'][name] = {'legacy_sha256': hashlib.sha256(x).hexdigest() if x is not None else None,
            'candidate_sha256': hashlib.sha256(y).hexdigest() if y is not None else None}
legacy_code = disassemble(args.legacy, left & right)
candidate_code = disassemble(args.candidate, left & right)
legacy_api = disassemble(args.legacy, left & right, True)
candidate_api = disassemble(args.candidate, left & right, True)
for name in sorted(left & right):
    a, b = legacy_code[name], candidate_code[name]
    if a != b:
        report["bytecode_differences"].append(name)
        (args.output / (name + ".legacy.javap")).write_text(a)
        (args.output / (name + ".candidate.javap")).write_text(b)
    if legacy_api[name] != candidate_api[name]:
        report["public_api_differences"].append(name)
    if binary_surface(legacy_api[name]) != binary_surface(candidate_api[name]):
        report["binary_api_differences"].append(name)
(args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
