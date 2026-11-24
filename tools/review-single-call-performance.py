#!/usr/bin/env python3
"""Freeze measured VM/harness identities and require unchanged correctness results."""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from audit_results import read_results

p=argparse.ArgumentParser()
p.add_argument('output',type=pathlib.Path)
p.add_argument('--accepted',required=True,choices=['00-baseline','01-split-lock','02-primary-slot','03-overflow-tuning','04-array-overflow'])
p.add_argument('--interleaved',type=pathlib.Path)
p.add_argument('--reproduction',type=pathlib.Path)
a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent.parent
performance=r/'build/performance-stages'
review=r/'documentation/debug-vararg-fixes.json'
matrix=r/'documentation/audit-matrix.json'
original=json.loads(matrix.read_text())
chain=json.loads(review.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
if chain['baseline_sha256']!=sha(matrix):raise SystemExit('Historical baseline changed')
expected=dict(original['variants']['fork']['tests'])
for stage in chain['stages']:
 for key,change in stage['changes'].items():
  if expected[key]!=change['before']:raise SystemExit('Broken correctness chain')
  expected[key]=change['after']
base_sources=original['harness_sources'].copy()
for stage in chain['stages']:base_sources.update(stage['regression_sources'])
common=json.loads((performance/'environment.json').read_text())
base_sources.update(common['common_sources'])
for name,digest in base_sources.items():
 if sha(r/name)!=digest:raise SystemExit('Harness changed: '+name)
stages={}
for name,audit,patch in [('00-baseline','perf-00-clean',None),
                         ('01-split-lock','perf-01-clean','14-split-stack-lock-trial.patch'),
                         ('02-primary-slot','perf-02-primary-slot','15-single-call-primary-slot.patch'),
                         ('03-overflow-tuning','perf-03-overflow-tuning','17-overflow-cache-tuning.patch'),
                         ('04-array-overflow','perf-04-array-overflow','18-overflow-array-stack.patch')]:
 directory=performance/name
 if not (directory/'jmh/results.json').exists():continue
 audit_path=r/'build/audit'/audit
 observed=read_results(audit_path)
 if len(observed)!=649 or observed!=expected:raise SystemExit('Correctness results changed: '+name)
 if (audit_path/'inventory.sha256').read_text().split()[0]!=chain['inventory_sha256']:raise SystemExit('Inventory changed')
 jar_sha=sha(directory/'vm.jar')
 if jar_sha!=(audit_path/'vm.sha256').read_text().split()[0]:raise SystemExit('Wrong audit VM')
 if jar_sha!=(directory/'jmh/vm.sha256').read_text().split()[0]:raise SystemExit('Wrong JMH VM')
 if sha(performance/'benchmarks.jar')!=(directory/'jmh/harness.sha256').read_text().split()[0]:raise SystemExit('Wrong JMH harness')
 log=directory/('regressions-137.log' if name=='00-baseline' else 'regressions.log')
 if 'OK (137 tests)' not in log.read_text():raise SystemExit('Missing regressions: '+name)
 measurements=json.loads((directory/'jmh/results.json').read_text())
 if len(measurements)!=8:raise SystemExit('Benchmark inventory changed')
 for measurement in measurements:
  if (measurement['forks'],measurement['threads'],measurement['warmupIterations'],measurement['measurementIterations'],measurement['warmupTime'],measurement['measurementTime'])!=(3,1,5,5,'1 s','1 s'):
   raise SystemExit('Measurement settings changed')
  if measurement['jvmArgs']!=['-Xms512m','-Xmx512m']:raise SystemExit('Heap settings changed')
  if len(measurement['primaryMetric']['rawData'])!=3 or any(len(v)!=5 for v in measurement['primaryMetric']['rawData']):raise SystemExit('Incomplete fork measurements')
 source_manifest=json.loads((directory/'source-manifest.json').read_text())
 if source_manifest['vm_sha256']!=jar_sha or source_manifest['files']['src/core/org/luaj/vm2/LuaClosure.java']!=sha(directory/'LuaClosure.java'):raise SystemExit('Wrong source snapshot')
 stage={'vm_sha256':jar_sha,'source_sha256':sha(directory/'LuaClosure.java'),
        'complete_source_archive_sha256':sha(directory/'complete-sources.tar.gz'),
        'source_manifest_sha256':sha(directory/'source-manifest.json'),
        'correctness_cases':649,'passed':624,'failed':25,'diagnostic_changes':0,'regression_tests':137,
        'regression_log_sha256':sha(log),'jmh_results_sha256':sha(directory/'jmh/results.json'),
        'measurements':measurements,'adopted':name==a.accepted}
 if patch:
  path=r/'documentation/changes'/patch
  stage['patch']=str(path.relative_to(r));stage['patch_sha256']=sha(path)
 stages[name]=stage
if a.accepted not in stages:raise SystemExit('Accepted stage not measured')
if sha(r/'src/core/org/luaj/vm2/LuaClosure.java')!=stages[a.accepted]['source_sha256']:raise SystemExit('Working source differs from accepted stage')
if sha(r/'target/luaj-beatoraja-0.1.0-SNAPSHOT.jar')!=stages[a.accepted]['vm_sha256']:raise SystemExit('Target jar differs from accepted stage')
comparisons={}
for name in stages:
 if name=='00-baseline':continue
 output=performance/(name+'-comparison.json')
 subprocess.run([sys.executable,str(r/'tools/compare-jmh-stages.py'),str(performance/'00-baseline/jmh'),str(performance/name/'jmh'),str(output)],check=True)
 comparisons[name]=json.loads(output.read_text())
if '03-overflow-tuning' in stages:
 output=performance/'02-to-03-comparison.json'
 subprocess.run([sys.executable,str(r/'tools/compare-jmh-stages.py'),str(performance/'02-primary-slot/jmh'),str(performance/'03-overflow-tuning/jmh'),str(output)],check=True)
 comparisons['02-to-03']=json.loads(output.read_text())
if '04-array-overflow' in stages:
 output=performance/'03-to-04-comparison.json'
 subprocess.run([sys.executable,str(r/'tools/compare-jmh-stages.py'),str(performance/'03-overflow-tuning/jmh'),str(performance/'04-array-overflow/jmh'),str(output)],check=True)
 comparisons['03-to-04']=json.loads(output.read_text())
result={'kind':'JMH microbenchmarks; real skin/frame performance not measured','accepted_stage':a.accepted,
        'correctness_review_sha256':sha(review),'original_matrix_sha256':sha(matrix),
        'inventory_sha256':chain['inventory_sha256'],'harness_sha256':sha(performance/'benchmarks.jar'),
        'baseline_source_archive_sha256':sha(performance/'00-baseline/sources.tar.gz'),
        'benchmark_source_sha256':sha(r/'benchmarks/src/main/java/org/luaj/benchmark/ShortCallBenchmark.java'),
        'regression_sources':base_sources,'verification_sources':{str(path.relative_to(r)):sha(path) for path in [r/'tools/review-single-call-performance.py',r/'tools/compare-jmh-stages.py',r/'tools/review-interleaved-call-benchmarks.py',r/'tools/snapshot-performance-stage.py',r/'tools/verify-performance-builds.py']},'environment':common,'stages':stages,'comparisons':comparisons}
if a.interleaved:
 paired=json.loads(a.interleaved.read_text())
 if paired['vm_sha256']!={'A':stages['00-baseline']['vm_sha256'],'B':stages[a.accepted]['vm_sha256']}:raise SystemExit('Wrong paired VMs')
 result['interleaved_review']={'path':str(a.interleaved),'sha256':sha(a.interleaved),'summary':paired['summary']}
if a.reproduction:
 rebuilt=json.loads(a.reproduction.read_text())
 for name in ['00-baseline',a.accepted]:
  if rebuilt[name]['vm_sha256']!=stages[name]['vm_sha256'] or not rebuilt[name]['byte_identical']:raise SystemExit('Reproduction failed')
 result['reproduction']=rebuilt
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print('Verified',len(stages),'stages: fixed 649 results unchanged; 137 regressions passed per stage')
