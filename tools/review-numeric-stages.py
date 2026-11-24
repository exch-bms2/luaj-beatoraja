#!/usr/bin/env python3
"""Review min/max and finite formatting against the preceding fixed inventory.

Only the named regions may change: min/max must match the existing C oracle,
and the Fibonacci transcript must contain the independently computed finite
value. The historical matrix and first three fix records remain unchanged.
"""
import argparse
import collections
import copy
import difflib
import hashlib
import json
import math
import pathlib
import re
from audit_results import read_results, normalize

p=argparse.ArgumentParser()
p.add_argument('runs',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
a=p.parse_args()
root=pathlib.Path(__file__).resolve().parent.parent
baseline_path=root/'documentation/audit-matrix.json'
baseline=json.loads(baseline_path.read_text())
prior_path=root/'documentation/correctness-fixes.json'
prior=json.loads(prior_path.read_text())
if prior['baseline_sha256']!=hashlib.sha256(baseline_path.read_bytes()).hexdigest():
    raise SystemExit('Historical baseline changed')
expected=dict(baseline['variants']['fork']['tests'])
for stage in prior['stages']:
    for key,change in stage['changes'].items():
        if expected[key]!=change['before']:raise SystemExit('Invalid preceding change chain')
        expected[key]=change['after']
if expected!=read_results(a.runs/'03-modf'):raise SystemExit('Preceding stage does not match reference')
math_cases={'org.luaj.vm2.CompatibiltyTest$'+flavor+'CompatibilityTest#testMathLib' for flavor in ('Jme','Jse','LuaJC')}
fib_cases={'org.luaj.vm2.CompatibiltyTest$'+flavor+'CompatibilityTest#testManyUpvals' for flavor in ('Jme','Jse','LuaJC')}
args_case='org.luaj.vm2.ErrorsTest#testMathLibArgs'
passed_math={key for key in math_cases if '$Jme' not in key}
result=copy.deepcopy(prior)
result['prior_review_sha256']=hashlib.sha256(prior_path.read_bytes()).hexdigest()
previous=a.runs/'03-modf'
for name,changes,improvements,test,patch,regressions in [
    ('04-minmax',math_cases|{args_case},passed_math,'MinMaxRegressionTest.java','04-minmax.patch',31),
    ('05-double-format',fib_cases,set(),'LuaDoubleFormattingTest.java','05-double-format.patch',40)]:
    directory=a.runs/name
    observed=read_results(directory)
    if set(observed)!=set(expected) or len(observed)!=649:raise SystemExit('Inventory mismatch')
    if (directory/'inventory.sha256').read_text().split()[0]!=prior['inventory_sha256']:raise SystemExit('Inventory hash mismatch')
    changed={key for key in expected if expected[key]!=observed[key]}
    if changed!=changes:raise SystemExit('Unexpected changed cases: '+str(changed^changes))
    diffs={}
    for key in sorted(changed):
        cls,method=key.split('#')
        filename=cls+'.'+method[4:].lower()+'.actual'
        before=normalize((previous/'output'/filename).read_text())
        after=normalize((directory/'output'/filename).read_text())
        if name=='04-minmax':
            oracle=normalize((directory/'output'/filename.replace('.actual','.expected')).read_text())
            if key==args_case:
                start,end='====== math.max ======\n','====== math.random ======\n'
            else:
                start,end='---------- math.max ----------\n','----------- Random number tests\n'
            for text in (before,after,oracle):
                if text.count(start)!=1 or text.count(end)!=1:raise SystemExit('Missing or duplicate min/max boundary')
            oracle_region=oracle[oracle.index(start):oracle.index(end)]
            transformed=before[:before.index(start)]+oracle_region+before[before.index(end):]
            if transformed!=after:raise SystemExit('Change outside numeric min/max oracle region: '+key)
        else:
            old='199th fibonacci number is\tInfinity\n'
            match=re.search(r'^199th fibonacci number is\t([^\n]+)\n',after,re.M)
            if before.count(old)!=1 or match is None:raise SystemExit('Missing Fibonacci line')
            x,y=1.0,1.0
            for i in range(3,200):x,y=y,x+y
            actual=float(match[1])
            if not math.isfinite(actual) or actual!=y:raise SystemExit('Incorrect finite Fibonacci value')
            if before.replace(old,match[0])!=after:raise SystemExit('Unexpected formatting transcript change: '+key)
        if key in improvements:
            if expected[key]['status']!='fail' or observed[key]['status']!='pass':raise SystemExit('Improvement missing')
        elif expected[key]['status']!='fail' or observed[key]['status']!='fail' or expected[key]['error_type']!=observed[key]['error_type']:
            raise SystemExit('Unexpected partial failure type: '+key)
        diffs[key]=list(difflib.unified_diff(before.splitlines(),after.splitlines(),n=1))
    source=root/'test/junit/org/luaj/vm2'/test
    patch_path=root/'documentation/changes'/patch
    stage={'name':name,'vm_sha256':(directory/'vm.sha256').read_text().split()[0],
           'case_count':649,'failure_count':sum(v['status']=='fail' for v in observed.values()),
           'improved_cases':sorted(improvements),'new_failures':[], 'reviewed_transcript_diffs':diffs,
           'regression_sources':{str(source.relative_to(root)):hashlib.sha256(source.read_bytes()).hexdigest()},
           'patch':str(patch_path.relative_to(root)),'patch_sha256':hashlib.sha256(patch_path.read_bytes()).hexdigest(),
           'cumulative_new_regression_tests':regressions,
           'changes':{key:{'before':expected[key],'after':observed[key]} for key in sorted(changed)}}
    log=(root/'build/correctness-stages'/(name.split('-')[0]+'-tests.log')).read_text()
    if 'OK ('+str(regressions)+' tests)' not in log:raise SystemExit('Missing regression log')
    result['stages'].append(stage)
    print(name,': 649 cases;',stage['failure_count'],'failures;',len(improvements),'improved; new failures: 0')
    expected=observed
    previous=directory
before=json.loads((root/'build/correctness-stages/numeric-before/results.json').read_text())
after=json.loads((root/'build/correctness-stages/numeric-after/results.json').read_text())
if before['vm_sha256']!=prior['stages'][-1]['vm_sha256'] or after['vm_sha256']!=result['stages'][-1]['vm_sha256']:
    raise SystemExit('Wrong regression VM snapshots')
if set(before['cases'])!=set(after['cases']) or len(after['cases'])!=17 or any(x['status']!='pass' for x in after['cases'].values()):
    raise SystemExit('Numeric regressions missing or failed')
result['numeric_regressions']={'before_vm_sha256':before['vm_sha256'],'after_vm_sha256':after['vm_sha256'],
    'before_counts':dict(collections.Counter(x['status'] for x in before['cases'].values())),
    'after_counts':dict(collections.Counter(x['status'] for x in after['cases'].values())),
    'before_cases':{key:value['status'] for key,value in before['cases'].items()}}
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
