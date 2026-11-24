#!/usr/bin/env python3
"""Review only the named-local and Java-frame transcript corrections."""
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
prior_path = root/'documentation/protected-call-fixes.json'
prior = json.loads(prior_path.read_text())
baseline = json.loads(baseline_path.read_text())
if prior['baseline_sha256'] != hashlib.sha256(baseline_path.read_bytes()).hexdigest():
    raise SystemExit('Baseline changed')
expected = dict(baseline['variants']['fork']['tests'])
for stage in prior['stages']:
    for key, change in stage['changes'].items():
        if expected[key] != change['before']: raise SystemExit('Invalid preceding chain')
        expected[key] = change['after']
if expected != read_results(a.runs/'07-protected-call'): raise SystemExit('Preceding results mismatch')

def local_correction(text):
    edits = {
        '3-7': [('get=nil,function: @debuglib.lua:19-24', 'get=nil,nil'), ('get=nil,#', 'get=nil,nil')],
        '2-4': [('get=nil,function: @debuglib.lua:9-18', 'get=nil,nil'), ('get=nil,#', 'get=nil,nil')],
        '1-4': [('get=#,function: getlocal', 'get=#,nil')],
        '1-6': [('get=nil,6', 'get=nil,nil')],
        '1-7': [('get=nil,7', 'get=nil,nil')],
    }
    for i in range(5,8): edits['2-'+str(i)] = [('get=nil,#', 'get=nil,nil')]
    lines = text.splitlines(True)
    for tag, replacements in edits.items():
        matches = [i for i,s in enumerate(lines) if s.startswith('true\th-'+tag+' -> ')]
        if len(matches) != 1: raise SystemExit('Missing local transcript row '+tag)
        i = matches[0]
        for old,new in replacements:
            if lines[i].count(old) != 1: raise SystemExit('Unexpected local transcript '+tag)
            lines[i] = lines[i].replace(old,new)
    return ''.join(lines)

def java_correction(text):
    for expression in ['debug.getlocal(1,1)', "debug.getlocal(1,'2')", 'debug.setlocal(1,1,nil)',
                       "debug.setlocal(1,1,'foo')", 'debug.setlocal(<thread>,1,2,nil)',
                       "debug.setlocal(<thread>,1,2,'bar')"]:
        old = 'fail \t'+expression+'\t\'Cannot read the array length because "this.stack" is null\'\n'
        if text.count(old) != 1: raise SystemExit('Missing Java frame diagnostic '+expression)
        text = text.replace(old, '-\t\t'+expression+'\t\n')
    # Missing value validation is a separate, pre-existing API discrepancy.
    for expression in ['debug.setlocal(1,1)', 'debug.setlocal(<thread>,1,2)']:
        old = 'badmsg \t'+expression+'\ttemplate=\'value expected\' actual=\'Cannot read the array length because "this.stack" is null\'\n'
        if text.count(old) != 1: raise SystemExit('Missing missing-value diagnostic '+expression)
        text = text.replace(old, 'needcheck \t'+expression+'\tnil\n')
    return text

result = copy.deepcopy(prior)
result['protected_review_sha256'] = hashlib.sha256(prior_path.read_bytes()).hexdigest()
previous = a.runs/'07-protected-call'
for name, cases, test, count, correction in [
    ('08-debug-locals', {'org.luaj.vm2.CompatibiltyTest$'+flavor+'CompatibilityTest#testDebugLib' for flavor in ('Jme','Jse')},
     'DebugLocalRegressionTest',84,local_correction),
    ('09-debug-java-frame', {'org.luaj.vm2.ErrorsTest#testDebugLibArgs'},'DebugJavaFrameRegressionTest',90,java_correction)]:
    directory = a.runs/name
    observed = read_results(directory)
    if set(observed) != set(expected) or len(observed) != 649: raise SystemExit('Inventory mismatch')
    if (directory/'inventory.sha256').read_text().split()[0] != prior['inventory_sha256']: raise SystemExit('Inventory hash mismatch')
    changed = {key for key in expected if expected[key] != observed[key]}
    if changed != cases: raise SystemExit('Unexpected changed cases: '+str(changed ^ cases))
    diffs = {}
    for key in sorted(cases):
        cls,method = key.split('#'); filename = cls+'.'+method[4:].lower()+'.actual'
        before = normalize((previous/'output'/filename).read_text())
        after = normalize((directory/'output'/filename).read_text())
        if correction(before) != after: raise SystemExit('Unexpected full-output change: '+key)
        if observed[key]['status'] != 'fail' or observed[key]['error_type'] != expected[key]['error_type']:
            raise SystemExit('Unexpected status or exception type: '+key)
        diffs[key] = list(difflib.unified_diff(before.splitlines(),after.splitlines(),n=1))
    source = root/'test/junit/org/luaj/vm2'/(test+'.java')
    patch = root/'documentation/changes'/(name+'.patch')
    if 'OK ('+str(count)+' tests)' not in (root/'build/correctness-stages'/(name[:2]+'-tests.log')).read_text():
        raise SystemExit('Missing focused regression log')
    stage = {'name':name,'vm_sha256':(directory/'vm.sha256').read_text().split()[0],
             'case_count':649,'failure_count':sum(v['status']=='fail' for v in observed.values()),
             'improved_cases':[],'partially_improved_cases':sorted(cases),'new_failures':[],
             'reviewed_transcript_diffs':diffs,
             'regression_sources':{str(source.relative_to(root)):hashlib.sha256(source.read_bytes()).hexdigest()},
             'patch':str(patch.relative_to(root)),'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
             'focused_regression_tests':count,
             'changes':{key:{'before':expected[key],'after':observed[key]} for key in sorted(cases)}}
    result['stages'].append(stage)
    print(name, ': 649 cases;',stage['failure_count'],'failures;',len(cases),'partially improved; new failures: 0')
    expected = observed; previous = directory

records = {}
for label, before_dir, after_dir, jar_stage, class_name, total in [
    ('locals','debug-locals-before','debug-locals-after','07-protected-call','DebugLocalRegressionTest',8),
    ('java','debug-java-before','debug-after','08-debug-locals','DebugJavaFrameRegressionTest',6)]:
    before = json.loads((root/'build/correctness-stages'/before_dir/'results.json').read_text())
    after = json.loads((root/'build/correctness-stages'/after_dir/'results.json').read_text())
    expected_jar = next(s['vm_sha256'] for s in result['stages'] if s['name']==jar_stage)
    after_stage = '08-debug-locals' if label=='locals' else '09-debug-java-frame'
    if before['vm_sha256'] != expected_jar or after['vm_sha256'] != next(s['vm_sha256'] for s in result['stages'] if s['name']==after_stage):
        raise SystemExit('Wrong bounded regression VM')
    selected = {k:v for k,v in after['cases'].items() if k.startswith('org.luaj.vm2.'+class_name+'#')}
    if set(before['cases']) != set(selected) or len(selected) != total or any(v['status']!='pass' for v in selected.values()):
        raise SystemExit('Regression missing or failed')
    records[label] = {'before_vm_sha256':before['vm_sha256'],'after_vm_sha256':after['vm_sha256'],
                     'before_counts':dict(collections.Counter(v['status'] for v in before['cases'].values())),
                     'after_counts':dict(collections.Counter(v['status'] for v in selected.values())),
                     'before_cases':{k:v['status'] for k,v in before['cases'].items()}}
result['debug_regressions'] = records
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
