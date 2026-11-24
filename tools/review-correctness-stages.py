#!/usr/bin/env python3
"""Verify the narrow expected changes, then export reviewed result fingerprints.

The historical 649-case inventory and baseline are never rewritten. This export
rejects changes beyond the named fixes and the exact math transcript edits.
"""
import argparse
import collections
import difflib
import hashlib
import json
import pathlib
from audit_results import read_results, normalize

p = argparse.ArgumentParser()
p.add_argument('runs', type=pathlib.Path)
p.add_argument('output', type=pathlib.Path)
p.add_argument('--baseline', type=pathlib.Path, default=pathlib.Path('documentation/audit-matrix.json'))
a = p.parse_args()
root = pathlib.Path(__file__).resolve().parent.parent
reference = json.loads(a.baseline.read_text())
causes = json.loads((root/'documentation/failure-causes.json').read_text())
expected = dict(reference['variants']['fork']['tests'])
weak_cases = {key.rsplit('.',1)[0]+'#'+key.rsplit('.',1)[1] for key,info in causes['cases'].items()
              if info['group'] in ('weak_integer_routing','weak_storage_layout_assertion')}
math_cases = {'org.luaj.vm2.CompatibiltyTest$'+flavor+'CompatibilityTest#testMathLib' for flavor in ('Jme','Jse','LuaJC')}
fmod_case = 'org.luaj.vm2.MathLibTest#testFmod'
fmod_edits = {'math.fmod('+args+")\tfalse\t/ by zero\n": 'math.fmod('+args+")\ttrue\t<nan>\n" for args in ('2,0','-2,0',"'2','0'")}
modf_edits = {"math.modf('0')\ttrue\t0\t<zero>\n": "math.modf('0')\ttrue\t<zero>\t<zero>\n"}
config = [
    ('01-weak', weak_cases, set(), {}, '01-weak-integer-keys.patch', 'WeakIntegerKeyTest.java',12),
    ('02-fmod', {fmod_case}, math_cases, fmod_edits, '02-fmod.patch', 'FmodRegressionTest.java',17),
    ('03-modf', set(), math_cases, modf_edits, '03-modf.patch', 'ModfRegressionTest.java',23)]
result = {'baseline_sha256':hashlib.sha256(a.baseline.read_bytes()).hexdigest(),
          'inventory_sha256':reference['inventory_sha256'],'stages':[]}
before = json.loads((root/'build/correctness-stages/bounded-before/results.json').read_text())
if before['vm_sha256'] != reference['variants']['fork']['vm_sha256'] or len(before['cases'])!=23:
    raise SystemExit('Invalid pre-fix regression snapshot')
result['before_regressions'] = {
    'vm_sha256':before['vm_sha256'], 'timeout_seconds':before['timeout_seconds'], 'per_case_heap':before['per_case_heap'],
    'counts':dict(collections.Counter(x['status'] for x in before['cases'].values())),
    'cases':{key:{k:v for k,v in value.items() if k!='diagnostic'} for key,value in before['cases'].items()}}
previous_directory = None
for name,improvements,partials,edits,patch_name,test_name,count in config:
    directory = a.runs/name
    observed = read_results(directory)
    if set(observed) != set(expected) or len(observed)!=649:
        raise SystemExit('Inventory changed: ' + name)
    if (directory/'inventory.sha256').read_text().split()[0]!=reference['inventory_sha256']:
        raise SystemExit('Inventory hash changed: ' + name)
    changed = {key for key in expected if expected[key]!=observed[key]}
    if changed != improvements|partials:
        raise SystemExit('Unexpected changed cases: ' + str((name,changed^(improvements|partials))))
    for key in improvements:
        if expected[key]['status']!='fail' or observed[key]['status']!='pass':
            raise SystemExit('Expected improvement missing: ' + key)
    diffs = {}
    for key in partials:
        if expected[key]['status']!='fail' or observed[key]['status']!='fail' or observed[key]['error_type']!=expected[key]['error_type']:
            raise SystemExit('Unexpected math test outcome: ' + key)
        cls,method = key.split('#')
        filename = cls+'.'+method[4:].lower()+'.actual'
        before = normalize((previous_directory/'output'/filename).read_text())
        after = normalize((directory/'output'/filename).read_text())
        transformed = before
        for old,new in edits.items():
            if transformed.count(old)!=1:
                raise SystemExit('Expected math line missing or duplicated: ' + old)
            transformed = transformed.replace(old,new)
        if transformed!=after:
            raise SystemExit('Unreviewed transcript change: ' + key)
        diffs[key] = list(difflib.unified_diff(before.splitlines(),after.splitlines(),n=1))
    source = root/'test/junit/org/luaj/vm2'/test_name
    patch = root/'documentation/changes'/patch_name
    stage = {'name':name, 'vm_sha256':(directory/'vm.sha256').read_text().split()[0],
             'case_count':len(observed), 'failure_count':sum(v['status']=='fail' for v in observed.values()),
             'improved_cases':sorted(improvements),'new_failures':[], 'reviewed_transcript_diffs':diffs,
             'patch':str(patch.relative_to(root)), 'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
             'regression_sources':{str(source.relative_to(root)):hashlib.sha256(source.read_bytes()).hexdigest()},
             'cumulative_new_regression_tests':count,
             'changes':{key:{'before':expected[key],'after':observed[key]} for key in sorted(changed)}}
    result['stages'].append(stage)
    print(name, '649 cases;',stage['failure_count'],'failures;',len(improvements),'improved;',len(partials),'partial outputs reviewed; new failures: 0')
    expected = observed
    previous_directory = directory
# Verify new tests against each VM snapshot, separately from the frozen inventory.
for stage in result['stages']:
    log = root/'build/correctness-stages'/(stage['name'].split('-')[0]+'-tests.log')
    if ('OK ('+str(stage['cumulative_new_regression_tests'])+' tests)') not in log.read_text():
        raise SystemExit('Regression result missing: ' + str(log))
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
