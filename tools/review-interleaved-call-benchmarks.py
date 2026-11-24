#!/usr/bin/env python3
"""Summarize three time-adjacent A/B pairs, alternating execution order."""
import argparse,hashlib,json,pathlib,statistics
p=argparse.ArgumentParser()
p.add_argument('directory',type=pathlib.Path)
p.add_argument('candidate',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent.parent
base=r/'build/performance-stages/00-baseline/vm.jar'
hashes={'A':hashlib.sha256(base.read_bytes()).hexdigest(),'B':hashlib.sha256(a.candidate.read_bytes()).hexdigest()}
expected={'zeroArguments','oneArgument','recursiveSingleResult','tailRecursion'}
blocks=[]
reference=None
for i,label in enumerate('ABBAAB'):
 directory=a.directory/('%02d-%s'%(i,label))
 if (directory/'vm.sha256').read_text().split()[0]!=hashes[label]:raise SystemExit('Wrong VM')
 if (directory/'harness.sha256').read_text().split()[0]!=hashlib.sha256((r/'build/performance-stages/benchmarks.jar').read_bytes()).hexdigest():raise SystemExit('Wrong harness')
 rows=json.loads((directory/'results.json').read_text())
 if len(rows)!=4 or {x['benchmark'].rsplit('.',1)[-1] for x in rows}!=expected:raise SystemExit('Wrong inventory')
 for x in rows:
  identity={key:x[key] for key in ['jmhVersion','mode','jvm','jdkVersion','vmName','vmVersion']}
  if reference is None:reference=identity
  if identity!=reference:raise SystemExit('Different JVM or measurement mode')
  if len(x['primaryMetric']['rawData'])!=1 or len(x['primaryMetric']['rawData'][0])!=5:raise SystemExit('Incomplete fork')
  if (x['forks'],x['threads'],x['warmupIterations'],x['measurementIterations'],x['warmupTime'],x['measurementTime'],x['jvmArgs'])!=(1,1,5,5,'1 s','1 s',['-Xms512m','-Xmx512m']):raise SystemExit('Wrong settings')
 blocks.append({'variant':label,'results_sha256':hashlib.sha256((directory/'results.json').read_bytes()).hexdigest(),'measurements':rows})
summary={}
for name in sorted(expected):
 values={'A':[],'B':[]};by_block=[];alloc={'A':[],'B':[]}
 for block in blocks:
  row=next(x for x in block['measurements'] if x['benchmark'].endswith('.'+name))
  score=row['primaryMetric']['score'];values[block['variant']].append(score);by_block.append(score)
  alloc[block['variant']].append(row['secondaryMetrics']['gc.alloc.rate.norm']['score'])
 ratios=[]
 for i in (0,2,4):
  pair={blocks[j]['variant']:by_block[j] for j in (i,i+1)}
  ratios.append(100*(pair['B']/pair['A']-1))
 before=statistics.median(values['A']);after=statistics.median(values['B'])
 summary[name]={'baseline_fork_means_ns':values['A'],'candidate_fork_means_ns':values['B'],
                'baseline_median_ns':before,'candidate_median_ns':after,'median_change_percent':100*(after/before-1),
                'paired_time_change_percent':ratios,'baseline_bytes':statistics.mean(alloc['A']),
                'candidate_bytes':statistics.mean(alloc['B'])}
 print(name, '%.3f -> %.3f ns/op (%+.1f%%); pairs:'%(before,after,summary[name]['median_change_percent']),[round(v,1) for v in ratios])
a.output.write_text(json.dumps({'order':'ABBAAB','independent_jvms_per_variant_per_benchmark':3,
                                'vm_sha256':hashes,'blocks':blocks,'summary':summary},indent=2,sort_keys=True)+'\n')
