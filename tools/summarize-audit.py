#!/usr/bin/env python3
"""Collect four fixed-inventory runs into a reviewable reference matrix."""
import argparse
import hashlib
import json
import pathlib
from audit_results import read_results

p = argparse.ArgumentParser()
p.add_argument('runs', type=pathlib.Path)
p.add_argument('output', type=pathlib.Path)
args = p.parse_args()
root = pathlib.Path(__file__).resolve().parent.parent
inventory = hashlib.sha256((root / 'documentation/audit-test-cases.list').read_bytes()).hexdigest()
variants = {}
for name in ('legacy','upstream','reconstructed','fork'):
    directory = args.runs / name
    if (directory / 'inventory.sha256').read_text().split()[0] != inventory:
        raise SystemExit('Inventory hash mismatch: ' + name)
    tests = read_results(directory)
    variants[name] = {'vm_sha256':(directory / 'vm.sha256').read_text().split()[0],
        'runtime':(directory / 'runtime.log').read_text().splitlines(), 'tests':tests,
        'failed':sum(v['status']=='fail' for v in tests.values()),
        'probes':dict(line.split('\t',1) for line in (directory / 'probes.tsv').read_text().splitlines())}
if len({tuple(sorted(v['tests'])) for v in variants.values()}) != 1:
    raise SystemExit('Different inventories across variants')
if variants['legacy']['tests'] != variants['reconstructed']['tests']:
    raise SystemExit('Reconstruction did not reproduce legacy test outcomes/outputs')
harness_files = [root/'pom.xml', *sorted((root/'test/junit').rglob('*.java')),
                 *sorted((root/'src/jme').rglob('*.java')),
                 *(root/'tools'/name for name in ('TestAuditRunner.java','CompatibilityProbes.java','audit_results.py','run-test-audit.sh'))]
result = {'date':'2026-11-24','inventory_sha256':inventory,
          'harness_sources':{str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in harness_files},
          'variants':variants}
args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
for name,v in variants.items(): print(name, 'cases=',len(v['tests']),'failures=',v['failed'])
