#!/usr/bin/env python3
"""Rebuild archived stages in isolated directories and require byte-identical jars."""
import argparse,hashlib,json,os,pathlib,subprocess,tarfile,tempfile,zipfile
p=argparse.ArgumentParser()
p.add_argument('stages',type=pathlib.Path,nargs='+')
p.add_argument('--output',type=pathlib.Path,required=True)
a=p.parse_args()
repo=os.environ.get('MAVEN_REPO',str(pathlib.Path.home()/'.m2/repository'))
mvn=os.environ.get('MVN','mvn')
records={}
for stage in a.stages:
 stage=stage.resolve()
 with tempfile.TemporaryDirectory(prefix='luaj-performance-rebuild-') as directory:
  work=pathlib.Path(directory)
  with tarfile.open(stage/'complete-sources.tar.gz') as archive:archive.extractall(work)
  manifest=json.loads((work/'PERFORMANCE-SNAPSHOT.json').read_text())
  for name,digest in manifest['files'].items():
   if hashlib.sha256((work/name).read_bytes()).hexdigest()!=digest:raise SystemExit('Snapshot mismatch: '+name)
  with (stage/'rebuild.log').open('w') as log:
   subprocess.run([mvn,'-o','-Dmaven.repo.local='+repo,'-Dmaven.test.skip=true','package'],cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
  jar=work/'target/luaj-beatoraja-0.1.0-SNAPSHOT.jar'
  digest=hashlib.sha256(jar.read_bytes()).hexdigest()
  expected=hashlib.sha256((stage/'vm.jar').read_bytes()).hexdigest()
  if digest!=expected:
   with zipfile.ZipFile(jar) as x,zipfile.ZipFile(stage/'vm.jar') as y:
    differences=[name for name in set(x.namelist())|set(y.namelist()) if name not in x.namelist() or name not in y.namelist() or x.read(name)!=y.read(name)]
   raise SystemExit('Rebuilt jar mismatch: '+stage.name+' entries: '+str(differences))
  records[stage.name]={'vm_sha256':digest,'byte_identical':True,
                       'source_archive_sha256':hashlib.sha256((stage/'complete-sources.tar.gz').read_bytes()).hexdigest()}
  print(stage.name,'byte-identical jar confirmed')
a.output.write_text(json.dumps(records,indent=2,sort_keys=True)+'\n')
