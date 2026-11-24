#!/usr/bin/env python3
"""Summarize matching JMH runs without equating microbenchmarks to frame time."""
import argparse
import hashlib
import json
import pathlib
p=argparse.ArgumentParser()
p.add_argument('before',type=pathlib.Path)
p.add_argument('after',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
a=p.parse_args()
def read(directory):
 data=json.loads((directory/'results.json').read_text())
 return {r['benchmark']:r for r in data}
before=read(a.before);after=read(a.after)
if before.keys()!=after.keys():raise SystemExit('Benchmark inventory mismatch')
if (a.before/'harness.sha256').read_text().split()[0]!=(a.after/'harness.sha256').read_text().split()[0]:raise SystemExit('Different harnesses')
records={}
for key,x in before.items():
 y=after[key]
 for setting in ['jmhVersion','mode','threads','forks','jvm','jvmArgs','jdkVersion','vmName','vmVersion','warmupIterations','warmupTime','measurementIterations','measurementTime']:
  if x[setting]!=y[setting]:raise SystemExit('Different '+setting)
 name=key.rsplit('.',1)[-1];px=x['primaryMetric'];py=y['primaryMetric']
 bx=x['secondaryMetrics']['gc.alloc.rate.norm'];by=y['secondaryMetrics']['gc.alloc.rate.norm']
 records[name]={'before_ns':px['score'],'after_ns':py['score'],'time_change_percent':100*(py['score']/px['score']-1),
                'before_time_confidence':px['scoreConfidence'],'after_time_confidence':py['scoreConfidence'],
                'before_fork_means':[sum(v)/len(v) for v in px['rawData']],
                'after_fork_means':[sum(v)/len(v) for v in py['rawData']],
                'before_bytes':bx['score'],'after_bytes':by['score']}
 print('%-24s %8.3f -> %8.3f ns/op (%+6.1f%%), %8.4f -> %8.4f B/op' %(name,px['score'],py['score'],records[name]['time_change_percent'],bx['score'],by['score']))
result={'before_vm_sha256':(a.before/'vm.sha256').read_text().split()[0],
        'after_vm_sha256':(a.after/'vm.sha256').read_text().split()[0],
        'harness_sha256':(a.before/'harness.sha256').read_text().split()[0],
        'before_results_sha256':hashlib.sha256((a.before/'results.json').read_bytes()).hexdigest(),
        'after_results_sha256':hashlib.sha256((a.after/'results.json').read_bytes()).hexdigest(),'results':records}
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
