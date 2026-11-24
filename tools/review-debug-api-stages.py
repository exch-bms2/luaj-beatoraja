#!/usr/bin/env python3
"""Review function-form getlocal and missing-value setlocal separately."""
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
prior_path = root/'documentation/debug-local-fixes.json'
prior = json.loads(prior_path.read_text())
baseline = json.loads(baseline_path.read_text())
if prior['baseline_sha256'] != hashlib.sha256(baseline_path.read_bytes()).hexdigest():
    raise SystemExit('Historical baseline changed')
expected = dict(baseline['variants']['fork']['tests'])
for stage in prior['stages']:
    for key, change in stage['changes'].items():
        if expected[key] != change['before']: raise SystemExit('Invalid preceding chain')
        expected[key] = change['after']
if expected != read_results(a.runs/'09-debug-java-frame'): raise SystemExit('Preceding results mismatch')

def replace_once(text, old, new):
    if text.count(old) != 1: raise SystemExit('Unexpected transcript: '+old)
    return text.replace(old,new)

def function_correction(text):
    for expression, name in [('debug.getlocal(<function>,1)','x'),
                             ("debug.getlocal(<function>,'2')",'y'),
                             ('debug.getlocal(<thread>,<function>,1)','x')]:
        text = replace_once(text, 'fail \t'+expression+"\t'bad argument: int expected, got function'\n",
                            '-\t\t'+expression+"\t'"+name+"'\n")
    for index, kind in [('nil','nil'),('true','boolean'),('<table>','table'),('<thread>','thread')]:
        prefix = 'badmsg \tdebug.getlocal(<function>,'+index+")\ttemplate='number expected' actual='bad argument: int expected, got "
        text = replace_once(text, prefix+"function'\n",prefix+kind+"'\n")
    text = replace_once(text, "badmsg \tdebug.getlocal(<function>,'abc')\ttemplate='number expected' actual='bad argument: int expected, got function'\n",
                        "-\t\tdebug.getlocal(<function>,'abc')\t...number expected...\n")
    prefix = "badmsg \tdebug.getlocal(<thread>,<function>)\ttemplate='got no value' actual='bad argument: int expected, got "
    return replace_once(text,prefix+"function'\n",prefix+"nil'\n")

def value_correction(text):
    for expression in ['debug.setlocal(1,1)','debug.setlocal(<thread>,1,2)']:
        text = replace_once(text,'needcheck \t'+expression+'\tnil\n',
                            '-\t\t'+expression+'\t...value expected...\n')
    return text

result = copy.deepcopy(prior)
result['debug_local_review_sha256'] = hashlib.sha256(prior_path.read_bytes()).hexdigest()
previous = a.runs/'09-debug-java-frame'
key = 'org.luaj.vm2.ErrorsTest#testDebugLibArgs'
for name, test, count, correction in [
    ('10-debug-function','DebugFunctionLocalRegressionTest',100,function_correction),
    ('11-debug-setlocal-value','DebugSetLocalValueRegressionTest',109,value_correction)]:
    directory = a.runs/name
    observed = read_results(directory)
    if set(observed) != set(expected) or len(observed) != 649: raise SystemExit('Inventory mismatch')
    if (directory/'inventory.sha256').read_text().split()[0] != prior['inventory_sha256']: raise SystemExit('Inventory hash mismatch')
    changed = {k for k in expected if expected[k] != observed[k]}
    if changed != {key}: raise SystemExit('Unexpected changed cases: '+str(changed))
    filename = 'org.luaj.vm2.ErrorsTest.debuglibargs.actual'
    before = normalize((previous/'output'/filename).read_text())
    after = normalize((directory/'output'/filename).read_text())
    if correction(before) != after: raise SystemExit('Unexpected full-output change: '+name)
    if observed[key]['status'] != 'fail' or observed[key]['error_type'] != expected[key]['error_type']:
        raise SystemExit('Unexpected status or exception type')
    source = root/'test/junit/org/luaj/vm2'/(test+'.java')
    patch = root/'documentation/changes'/(name+'.patch')
    if 'OK ('+str(count)+' tests)' not in (root/'build/correctness-stages'/(name[:2]+'-tests.log')).read_text():
        raise SystemExit('Missing focused regression log')
    result['stages'].append({'name':name,'vm_sha256':(directory/'vm.sha256').read_text().split()[0],
        'case_count':649,'failure_count':sum(v['status']=='fail' for v in observed.values()),
        'improved_cases':[],'partially_improved_cases':[key],'new_failures':[],
        'reviewed_transcript_diffs':{key:list(difflib.unified_diff(before.splitlines(),after.splitlines(),n=1))},
        'regression_sources':{str(source.relative_to(root)):hashlib.sha256(source.read_bytes()).hexdigest()},
        'patch':str(patch.relative_to(root)),'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
        'focused_regression_tests':count,'changes':{key:{'before':expected[key],'after':observed[key]}}})
    print(name,': 649 cases; 25 failures; 1 partially improved; new failures: 0')
    expected = observed; previous = directory

records = {}
for label, before_dir, after_dir, before_stage, after_stage, cls, total in [
    ('function','debug-function-before','debug-function-after','09-debug-java-frame','10-debug-function','DebugFunctionLocalRegressionTest',10),
    ('value','debug-value-before','debug-api-after','10-debug-function','11-debug-setlocal-value','DebugSetLocalValueRegressionTest',9)]:
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
result['debug_api_regressions'] = records
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
