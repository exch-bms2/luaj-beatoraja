#!/usr/bin/env python3
"""Check the exact inventory, failure type/message, and complete script output."""
import argparse
import hashlib
import json
import pathlib
from audit_results import read_results

p = argparse.ArgumentParser()
p.add_argument('matrix', type=pathlib.Path)
p.add_argument('results', type=pathlib.Path)
p.add_argument('--variant', default='fork')
p.add_argument('--reviewed-changes', type=pathlib.Path)
p.add_argument('--stage')
args = p.parse_args()
reference = json.loads(args.matrix.read_text())
expected = dict(reference['variants'][args.variant]['tests'])
extra_sources = {}
if args.reviewed_changes:
    if args.variant != 'fork' or not args.stage:
        raise SystemExit('--reviewed-changes requires --variant fork and --stage')
    review = json.loads(args.reviewed_changes.read_text())
    if review['baseline_sha256'] != hashlib.sha256(args.matrix.read_bytes()).hexdigest():
        raise SystemExit('Reviewed changes belong to a different baseline')
    if review['inventory_sha256'] != reference['inventory_sha256']:
        raise SystemExit('Reviewed inventory mismatch')
    found = False
    for stage in review['stages']:
        for key, change in stage['changes'].items():
            if expected.get(key) != change['before']:
                raise SystemExit('Invalid reviewed change chain: ' + key)
            expected[key] = change['after']
        extra_sources.update(stage['regression_sources'])
        if stage['name'] == args.stage:
            found = True
            break
    if not found:
        raise SystemExit('Unknown reviewed stage: ' + args.stage)
elif args.stage:
    raise SystemExit('--stage requires --reviewed-changes')
observed = read_results(args.results)
problems = []
root = pathlib.Path(__file__).resolve().parent.parent
for name, expected_hash in {**reference.get('harness_sources', {}), **extra_sources}.items():
    path = root / name
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        problems.append('Test harness changed: ' + name)
if set(expected) != set(observed):
    problems.append('Test inventory mismatch')
if (args.results / 'inventory.sha256').read_text().split()[0] != reference['inventory_sha256']:
    problems.append('Inventory SHA-256 mismatch')
for key in sorted(set(expected) & set(observed)):
    before, after = expected[key], observed[key]
    if before['status'] == 'fail' and after['status'] == 'pass':
        print('IMPROVED:', key)
    elif before != after:
        problems.append(key + ': outcome or diagnostic output changed')
for problem in problems:
    print('REVIEW:', problem)
print(f"Cases: {len(observed)}; failures: {sum(x['status']=='fail' for x in observed.values())}; changes requiring review: {len(problems)}")
raise SystemExit(bool(problems))
