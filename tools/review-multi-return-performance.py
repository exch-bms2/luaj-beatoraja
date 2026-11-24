#!/usr/bin/env python3
"""Verify the complete correctness baseline and freeze multi-return measurements."""
import argparse,hashlib,json,pathlib,re,subprocess,sys,zipfile
from audit_results import read_results
p=argparse.ArgumentParser()
p.add_argument('output',type=pathlib.Path)
p.add_argument('--reproduction',type=pathlib.Path)
a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent.parent
root=r/'build/multi-return-stages'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
parent_path=r/'documentation/single-call-performance.json'
parent=json.loads(parent_path.read_text())
review_path=r/'documentation/debug-vararg-fixes.json'
review=json.loads(review_path.read_text())
matrix_path=r/'documentation/audit-matrix.json'
matrix=json.loads(matrix_path.read_text())
if review['baseline_sha256']!=sha(matrix_path):raise SystemExit('Historical matrix changed')
expected=dict(matrix['variants']['fork']['tests'])
for stage in review['stages']:
 for key,change in stage['changes'].items():
  if expected[key]!=change['before']:raise SystemExit('Invalid review chain')
  expected[key]=change['after']
sources=dict(parent['regression_sources'])
for name,digest in sources.items():
 if sha(r/name)!=digest:raise SystemExit('Existing regression source changed: '+name)
for name in ['test/junit/org/luaj/vm2/MultiReturnOwnershipTest.java','tools/run-multi-return-regressions.py']:
 sources[name]=sha(r/name)
new_count=len(re.findall(r'public void test\w+\(', (r/'test/junit/org/luaj/vm2/MultiReturnOwnershipTest.java').read_text()))
if new_count!=12:raise SystemExit('New test inventory changed')
if sha(root/'00-baseline/vm.jar')!=parent['stages']['04-array-overflow']['vm_sha256']:
 raise SystemExit('Baseline is not the latest single-call stage')
if any(name.startswith('org/luaj/vm2/') for name in zipfile.ZipFile(root/'benchmarks.jar').namelist()):raise SystemExit('VM embedded in harness')
benchmark_names={'org.luaj.benchmark.MultiReturnBenchmark.'+name for name in ['twoResults','prefixedResults','borrowedPassthrough','discardedResults']}|{'org.luaj.benchmark.ShortCallBenchmark.'+name for name in ['zeroArguments','oneArgument','fourArguments','multipleResults']}
stages={};comparisons={}
names=['00-baseline','01-owned-snapshots','02-fixed-results','03-owned-prefix']
patches=[None,'19-owned-varargs-snapshots.patch','20-fixed-return-snapshot.patch','21-owned-prefix-return.patch']
for name,patch in zip(names,patches):
 directory=root/name; audit=r/'build/audit'/('multi-'+name)
 observed=read_results(audit)
 if len(observed)!=649 or observed!=expected:raise SystemExit('Correctness results changed: '+name)
 if (audit/'inventory.sha256').read_text().split()[0]!=review['inventory_sha256']:raise SystemExit('Inventory changed')
 vm_sha=sha(directory/'vm.jar')
 if any((path.read_text().split()[0]!=vm_sha) for path in [audit/'vm.sha256',directory/'jmh/vm.sha256']):raise SystemExit('Wrong VM: '+name)
 if (directory/'jmh/harness.sha256').read_text().split()[0]!=sha(root/'benchmarks.jar'):raise SystemExit('Harness changed')
 if 'OK (149 tests)' not in (directory/'regressions.log').read_text():raise SystemExit('Regression tests missing')
 snapshot=json.loads((directory/'source-manifest.json').read_text())
 if snapshot['vm_sha256']!=vm_sha:raise SystemExit('Wrong source snapshot')
 for source,digest in sources.items():
  if snapshot['files'].get(source)!=digest:raise SystemExit('Archived regression source mismatch: '+name+' '+source)
 source_hashes={}
 for source in ['LuaClosure.java','Varargs.java']:
  source_hashes[source]=sha(directory/source)
  path='src/core/org/luaj/vm2/'+source
  if snapshot['files'][path]!=source_hashes[source]:raise SystemExit('Snapshot source mismatch')
 measurements=json.loads((directory/'jmh/results.json').read_text())
 if len(measurements)!=8 or {v['benchmark'] for v in measurements}!=benchmark_names:raise SystemExit('Benchmark inventory mismatch')
 for v in measurements:
  if (v['forks'],v['threads'],v['warmupIterations'],v['measurementIterations'],v['warmupTime'],v['measurementTime'],v['jvmArgs'])!=(3,1,5,5,'1 s','1 s',['-Xms512m','-Xmx512m']):raise SystemExit('Different JMH settings')
  if len(v['primaryMetric']['rawData'])!=3 or any(len(xs)!=5 for xs in v['primaryMetric']['rawData']):raise SystemExit('Incomplete fork results')
 stage={'vm_sha256':vm_sha,'source_sha256':source_hashes,'correctness_cases':649,'passed':624,'failed':25,
        'diagnostic_changes':0,'existing_regressions':137,'new_regressions':new_count,'regression_tests':149,
        'regression_log_sha256':sha(directory/'regressions.log'),'source_archive_sha256':sha(directory/'complete-sources.tar.gz'),
        'source_manifest_sha256':sha(directory/'source-manifest.json'),'measurements':measurements,
        'jmh_results_sha256':sha(directory/'jmh/results.json')}
 if patch:
  path=r/'documentation/changes'/patch;stage['patch']=str(path.relative_to(r));stage['patch_sha256']=sha(path)
 stages[name]=stage
for i,name in enumerate(names[1:],1):
 for label,before in [('baseline',names[0]),('previous',names[i-1])]:
  path=root/(name+'-'+label+'-comparison.json')
  subprocess.run([sys.executable,str(r/'tools/compare-jmh-stages.py'),str(root/before/'jmh'),str(root/name/'jmh'),str(path)],check=True,stdout=subprocess.DEVNULL)
  comparisons[name+'-'+label]=json.loads(path.read_text())
control_dirs=[root/'controls-00-baseline/jmh',root/'controls-03-owned-prefix/jmh']
control_measurements={}
for name,directory in zip([names[0],names[-1]],control_dirs):
 if (directory/'vm.sha256').read_text().split()[0]!=stages[name]['vm_sha256']:raise SystemExit('Wrong control VM')
 if (directory/'harness.sha256').read_text().split()[0]!=sha(root/'benchmarks.jar'):raise SystemExit('Wrong control harness')
 rows=json.loads((directory/'results.json').read_text())
 if len(rows)!=2 or {v['benchmark'].rsplit('.',1)[-1] for v in rows}!={'recursiveSingleResult','tailRecursion'}:raise SystemExit('Control inventory mismatch')
 control_measurements[name]=rows
control_output=root/'controls-comparison.json'
subprocess.run([sys.executable,str(r/'tools/compare-jmh-stages.py'),str(control_dirs[0]),str(control_dirs[1]),str(control_output)],check=True,stdout=subprocess.DEVNULL)
last=names[-1]
if sha(r/'target/luaj-beatoraja-0.1.0-SNAPSHOT.jar')!=stages[last]['vm_sha256']:raise SystemExit('Target differs from final VM')
for name,digest in stages[last]['source_sha256'].items():
 if sha(r/'src/core/org/luaj/vm2'/name)!=digest:raise SystemExit('Working source differs from measured final stage')
result={'kind':'JMH microbenchmarks; real-skin performance not measured','parent_performance_sha256':sha(parent_path),
        'correctness_review_sha256':sha(review_path),'original_matrix_sha256':sha(matrix_path),
        'inventory_sha256':review['inventory_sha256'],'harness_sha256':sha(root/'benchmarks.jar'),
        'benchmark_sources':{str(path.relative_to(r)):sha(path) for path in (r/'benchmarks/src/main/java').rglob('*.java')},
        'regression_sources':sources,'regression_patch':{'path':'documentation/changes/22-multi-return-regressions.patch','sha256':sha(r/'documentation/changes/22-multi-return-regressions.patch')},'verification_sources':{str(path.relative_to(r)):sha(path) for path in [pathlib.Path(__file__).resolve(),r/'tools/snapshot-multi-return-stage.py',r/'tools/compare-jmh-stages.py',r/'tools/verify-performance-builds.py']},
        'stages':stages,'comparisons':comparisons,'controls':{'measurements':control_measurements,'comparison':json.loads(control_output.read_text())}}
if a.reproduction:
 rebuilt=json.loads(a.reproduction.read_text())
 for name in names:
  if not rebuilt[name]['byte_identical'] or rebuilt[name]['vm_sha256']!=stages[name]['vm_sha256'] or rebuilt[name]['source_archive_sha256']!=stages[name]['source_archive_sha256']:raise SystemExit('Reproduction failed')
 result['reproduction']=rebuilt
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print('Verified 4 stages: fixed 649 outputs unchanged; 137 existing + 12 new regressions passed per stage')
