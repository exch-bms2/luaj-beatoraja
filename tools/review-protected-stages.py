#!/usr/bin/env python3
"""Review reader EOF and protected-call scope without replacing old baselines."""
import argparse
import collections
import copy
import difflib
import hashlib
import json
import pathlib
from audit_results import read_results, normalize

p=argparse.ArgumentParser()
p.add_argument('runs',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
a=p.parse_args()
root=pathlib.Path(__file__).resolve().parent.parent
baseline_path=root/'documentation/audit-matrix.json'
baseline=json.loads(baseline_path.read_text())
prior_path=root/'documentation/numeric-fixes.json'
prior=json.loads(prior_path.read_text())
if prior['baseline_sha256']!=hashlib.sha256(baseline_path.read_bytes()).hexdigest():raise SystemExit('Baseline changed')
expected=dict(baseline['variants']['fork']['tests'])
for stage in prior['stages']:
    for key,change in stage['changes'].items():
        if expected[key]!=change['before']:raise SystemExit('Invalid preceding change chain')
        expected[key]=change['after']
if expected!=read_results(a.runs/'05-double-format'):raise SystemExit('Preceding results mismatch')
base_cases={'org.luaj.vm2.CompatibiltyTest$'+flavor+'CompatibilityTest#testBaseLib' for flavor in ('Jme','Jse','LuaJC')}
interpreted={key for key in base_cases if '$LuaJC' not in key}
result=copy.deepcopy(prior)
result['numeric_review_sha256']=hashlib.sha256(prior_path.read_bytes()).hexdigest()
previous=a.runs/'05-double-format'
for name,changes,improvements,test,patch,count in [
    ('06-reader',base_cases,set(),'LoadReaderRegressionTest.java','06-reader-eof.patch',50),
    ('07-protected-call',interpreted,interpreted,'PcallScopeRegressionTest.java','07-protected-call-scope.patch',62)]:
    directory=a.runs/name
    observed=read_results(directory)
    if set(observed)!=set(expected) or len(observed)!=649:raise SystemExit('Inventory mismatch')
    if (directory/'inventory.sha256').read_text().split()[0]!=prior['inventory_sha256']:raise SystemExit('Inventory hash mismatch')
    changed={key for key in expected if expected[key]!=observed[key]}
    if changed!=changes:raise SystemExit('Unexpected changed cases: '+str(changed^changes))
    diffs={}
    for key in sorted(changed):
        cls,method=key.split('#');filename=cls+'.'+method[4:].lower()+'.actual'
        before=normalize((previous/'output'/filename).read_text())
        after=normalize((directory/'output'/filename).read_text())
        if name=='06-reader':
            old,new='after empty string\n',''
        else:
            old="pcall(xpcall(wrappedbad))\tfalse\tstring\n  in errfunc\tstring\nxpcall(wrappedbad,errfunc)\ttrue\n"
            new="pcall(xpcall(wrappedbad))\tfalse\tstring\nxpcall(wrappedbad,errfunc)\ttrue\n"
        if before.count(old)!=1 or before.replace(old,new)!=after:raise SystemExit('Unexpected full-output change: '+key)
        if key in improvements:
            oracle=normalize((directory/'output'/filename.replace('.actual','.expected')).read_text())
            if observed[key]['status']!='pass' or after!=oracle:raise SystemExit('Expected oracle match missing')
        elif observed[key]['status']!='fail' or observed[key]['error_type']!=expected[key]['error_type']:
            raise SystemExit('Unexpected partial failure change')
        diffs[key]=list(difflib.unified_diff(before.splitlines(),after.splitlines(),n=1))
    source=root/'test/junit/org/luaj/vm2'/test
    patch_path=root/'documentation/changes'/patch
    stage={'name':name,'vm_sha256':(directory/'vm.sha256').read_text().split()[0],
        'case_count':649,'failure_count':sum(v['status']=='fail' for v in observed.values()),
        'improved_cases':sorted(improvements),'new_failures':[], 'reviewed_transcript_diffs':diffs,
        'regression_sources':{str(source.relative_to(root)):hashlib.sha256(source.read_bytes()).hexdigest()},
        'patch':str(patch_path.relative_to(root)),'patch_sha256':hashlib.sha256(patch_path.read_bytes()).hexdigest(),
        'cumulative_new_regression_tests':count,
        'changes':{key:{'before':expected[key],'after':observed[key]} for key in sorted(changed)}}
    log=(root/'build/correctness-stages'/(name.split('-')[0]+'-tests.log')).read_text()
    if 'OK ('+str(count)+' tests)' not in log:raise SystemExit('Missing regression log')
    result['stages'].append(stage)
    print(name,': 649 cases;',stage['failure_count'],'failures;',len(improvements),'improved; new failures: 0')
    expected=observed;previous=directory
before=json.loads((root/'build/correctness-stages/protected-before/results.json').read_text())
after=json.loads((root/'build/correctness-stages/protected-after/results.json').read_text())
if before['vm_sha256']!=prior['stages'][-1]['vm_sha256'] or after['vm_sha256']!=result['stages'][-1]['vm_sha256']:
    raise SystemExit('Wrong regression VM')
if set(before['cases'])!=set(after['cases']) or len(after['cases'])!=22 or any(x['status']!='pass' for x in after['cases'].values()):
    raise SystemExit('Protected-call regression failed or missing')
result['protected_regressions']={'before_vm_sha256':before['vm_sha256'],'after_vm_sha256':after['vm_sha256'],
    'before_counts':dict(collections.Counter(x['status'] for x in before['cases'].values())),
    'after_counts':dict(collections.Counter(x['status'] for x in after['cases'].values())),
    'before_cases':{key:value['status'] for key,value in before['cases'].items()}}
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
