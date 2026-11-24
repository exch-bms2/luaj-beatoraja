#!/usr/bin/env python3
"""Review vararg support and stack-level errors against the fixed 649 cases."""
import argparse
import collections
import copy
import difflib
import hashlib
import json
import pathlib
from audit_results import read_results, normalize

p = argparse.ArgumentParser()
p.add_argument('runs', type=pathlib.Path)
p.add_argument('output', type=pathlib.Path)
a = p.parse_args()
root = pathlib.Path(__file__).resolve().parent.parent
baseline_path = root/'documentation/audit-matrix.json'
prior_path = root/'documentation/debug-api-fixes.json'
prior = json.loads(prior_path.read_text())
baseline = json.loads(baseline_path.read_text())
if prior['baseline_sha256'] != hashlib.sha256(baseline_path.read_bytes()).hexdigest():
    raise SystemExit('Historical baseline changed')
expected = dict(baseline['variants']['fork']['tests'])
for stage in prior['stages']:
    for key, change in stage['changes'].items():
        if expected[key] != change['before']: raise SystemExit('Invalid preceding chain')
        expected[key] = change['after']
if expected != read_results(a.runs/'11-debug-setlocal-value'): raise SystemExit('Preceding results mismatch')

result = copy.deepcopy(prior)
result['debug_api_review_sha256'] = hashlib.sha256(prior_path.read_bytes()).hexdigest()
previous = a.runs/'11-debug-setlocal-value'
key = 'org.luaj.vm2.ErrorsTest#testDebugLibArgs'
for name, test, count, changed_cases in [
    ('12-debug-varargs','DebugVarargsRegressionTest',123,set()),
    ('13-debug-stack-level','DebugStackLevelRegressionTest',133,{key})]:
    directory = a.runs/name
    observed = read_results(directory)
    if set(observed) != set(expected) or len(observed) != 649: raise SystemExit('Inventory mismatch')
    if (directory/'inventory.sha256').read_text().split()[0] != prior['inventory_sha256']: raise SystemExit('Inventory hash mismatch')
    changed = {k for k in expected if expected[k] != observed[k]}
    if changed != changed_cases: raise SystemExit('Unexpected changed cases: '+str(changed ^ changed_cases))
    diffs = {}
    if changed:
        filename = 'org.luaj.vm2.ErrorsTest.debuglibargs.actual'
        before = normalize((previous/'output'/filename).read_text())
        after = normalize((directory/'output'/filename).read_text())
        corrected = before
        for expression in ['debug.getlocal(<thread>,100,1)',"debug.setlocal(10,1,'foo')"]:
            old = 'needcheck \t'+expression+'\tnil\n'
            if corrected.count(old) != 1: raise SystemExit('Unexpected transcript: '+expression)
            corrected = corrected.replace(old,'-\t\t'+expression+'\t...level out of range...\n')
        if corrected != after: raise SystemExit('Unexpected full-output change')
        if observed[key]['status'] != 'fail' or observed[key]['error_type'] != expected[key]['error_type']:
            raise SystemExit('Unexpected status or exception type')
        diffs[key] = list(difflib.unified_diff(before.splitlines(),after.splitlines(),n=1))
    source = root/'test/junit/org/luaj/vm2'/(test+'.java')
    patch = root/'documentation/changes'/(name+'.patch')
    if 'OK ('+str(count)+' tests)' not in (root/'build/correctness-stages'/(name[:2]+'-tests.log')).read_text():
        raise SystemExit('Missing focused regression log')
    stage = {'name':name,'vm_sha256':(directory/'vm.sha256').read_text().split()[0],
        'case_count':649,'failure_count':sum(v['status']=='fail' for v in observed.values()),
        'improved_cases':[],'partially_improved_cases':sorted(changed),'new_failures':[],
        'reviewed_transcript_diffs':diffs,
        'regression_sources':{str(source.relative_to(root)):hashlib.sha256(source.read_bytes()).hexdigest()},
        'patch':str(patch.relative_to(root)),'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
        'focused_regression_tests':count,'changes':{k:{'before':expected[k],'after':observed[k]} for k in sorted(changed)}}
    result['stages'].append(stage)
    print(name,': 649 cases;',stage['failure_count'],'failures;',len(changed),'partially improved; new failures: 0')
    expected = observed; previous = directory

records = {}
for label, before_dir, after_dir, before_stage, after_stage, cls, total in [
    ('varargs','debug-varargs-before','debug-varargs-after','11-debug-setlocal-value','12-debug-varargs','DebugVarargsRegressionTest',14),
    ('levels','debug-level-before','debug-vararg-level-after','12-debug-varargs','13-debug-stack-level','DebugStackLevelRegressionTest',10)]:
    before = json.loads((root/'build/correctness-stages'/before_dir/'results.json').read_text())
    after = json.loads((root/'build/correctness-stages'/after_dir/'results.json').read_text())
    hashes = {s['name']:s['vm_sha256'] for s in result['stages']}
    if before['vm_sha256'] != hashes[before_stage] or after['vm_sha256'] != hashes[after_stage]:
        raise SystemExit('Wrong bounded regression VM')
    selected = {k:v for k,v in after['cases'].items() if k.startswith('org.luaj.vm2.'+cls+'#')}
    if set(before['cases']) != set(selected) or len(selected) != total or any(v['status']!='pass' for v in selected.values()):
        raise SystemExit('Regression missing or failed')
    records[label] = {'before_vm_sha256':before['vm_sha256'],'after_vm_sha256':after['vm_sha256'],
        'before_counts':dict(collections.Counter(v['status'] for v in before['cases'].values())),
        'after_counts':dict(collections.Counter(v['status'] for v in selected.values())),
        'before_cases':{k:v['status'] for k,v in before['cases'].items()}}
result['debug_vararg_level_regressions'] = records
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
