#!/usr/bin/env python3
"""Archive a complete build/test tree with a selected stage's LuaClosure source."""
import argparse
import hashlib
import io
import json
import pathlib
import tarfile
p=argparse.ArgumentParser()
p.add_argument('stage',type=pathlib.Path)
a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent.parent
stage=a.stage.resolve()
selected=stage/'LuaClosure.java'
files={}
for name in ['src','test','tools','documentation','benchmarks/src','benchmarks/pom.xml','pom.xml','README.md','LICENSE']:
 path=r/name
 for f in (sorted(path.rglob('*')) if path.is_dir() else [path]):
  if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ['.class','.pyc']:
   relative=str(f.relative_to(r))
   files[relative]=selected if relative=='src/core/org/luaj/vm2/LuaClosure.java' else f
manifest={'vm_sha256':hashlib.sha256((stage/'vm.jar').read_bytes()).hexdigest(),
          'files':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}}
with tarfile.open(stage/'complete-sources.tar.gz','w:gz') as tar:
 for name,path in sorted(files.items()):tar.add(path,arcname=name,recursive=False)
 data=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
 info=tarfile.TarInfo('PERFORMANCE-SNAPSHOT.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
(stage/'source-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print(stage.name,len(files),'files archived')
