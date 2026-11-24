#!/usr/bin/env python3
"""Classify every common class, and reject unexplained reconstruction differences."""
import argparse
import collections
import copy
import hashlib
import json
import pathlib

p = argparse.ArgumentParser()
p.add_argument('baseline_comparison', type=pathlib.Path)
p.add_argument('reconstructed_comparison', type=pathlib.Path)
p.add_argument('output', type=pathlib.Path)
a = p.parse_args()
base = json.loads((a.baseline_comparison/'report.json').read_text())
rebuilt = json.loads((a.reconstructed_comparison/'report.json').read_text())
base_code = json.loads((a.baseline_comparison/'normalized/normalized.json').read_text())['classes']
rebuilt_code = json.loads((a.reconstructed_comparison/'normalized/normalized.json').read_text())['classes']
branding = {'lua','luac','luajc','org.luaj.vm2.Lua','org.luaj.vm2.lib.BaseLib','org.luaj.vm2.script.LuaScriptEngine'}


def strip_generated(metadata, strip_inner=False):
    result = copy.deepcopy(metadata)
    result.pop('attribute_census')
    attributes = [result['attributes']] + [m['attributes'] for m in result['fields'].values()] + [m['attributes'] for m in result['methods'].values()]
    for attrs in attributes:
        for key in ('Code','Signature','SourceFile'):
            attrs.pop(key, None)
        if strip_inner: attrs.pop('InnerClasses', None)
    return result


def signatures(metadata):
    result = {'class':metadata['attributes'].get('Signature')}
    for section in ('fields','methods'):
        for name,item in metadata[section].items(): result[section+':'+name] = item['attributes'].get('Signature')
    return result

classes = {}
for name in base['common_classes']:
    normalized = base_code.get(name, {'category':'javap_equal','members':{}})
    category = normalized['category']
    if name in branding: category = 'distribution_version_branding'
    if name == 'org.luaj.vm2.LuaClosure': category = 'unsafe_stack_cache_customization'
    item = base['classfiles'][name]
    ls, rs = signatures(item['legacy_metadata']), signatures(item['candidate_metadata'])
    signature_changes = [k for k in sorted(ls.keys()|rs.keys()) if ls.get(k)!=rs.get(k)]
    classes[name] = {'category':category,'changed_members':sorted(normalized['members']),
                     'generic_signature_changes':signature_changes}
unexplained_code = [n for n,item in rebuilt_code.items() if item['category']=='instruction_or_constant_difference']
unexplained_metadata = []
code_header_changes = []
inner_reference_changes = {}
for name,item in rebuilt['classfiles'].items():
    left,right = item['legacy_metadata'],item['candidate_metadata']
    for method in left['methods'].keys() & right['methods'].keys():
        lc = left['methods'][method]['attributes'].get('Code')
        rc = right['methods'][method]['attributes'].get('Code')
        if (lc is None) != (rc is None) or (lc is not None and any(lc[k] != rc[k] for k in ('max_stack','max_locals','handlers'))):
            code_header_changes.append(name + '::' + method)
    if strip_generated(left) != strip_generated(right):
        if strip_generated(left,True) != strip_generated(right,True): unexplained_metadata.append(name)
        else:
            li = left['attributes'].get('InnerClasses',[])
            ri = right['attributes'].get('InnerClasses',[])
            inner_reference_changes[name] = {'legacy_only':[x for x in li if x not in ri], 'candidate_only':[x for x in ri if x not in li]}
# Ant strips List<Exp.VarExp>; javac then has no reason to emit that reference.
expected_inner = ['org/luaj/vm2/ast/Exp$VarExp','org/luaj/vm2/ast/Exp','VarExp',1033]
for name,change in inner_reference_changes.items():
    if name not in ('org.luaj.vm2.ast.Stat','org.luaj.vm2.ast.Stat$Assign') or change != {'legacy_only':[], 'candidate_only':[expected_inner]}:
        unexplained_metadata.append(name)
if unexplained_code or unexplained_metadata or code_header_changes or rebuilt['binary_api_differences'] or rebuilt['legacy_only'] or rebuilt['candidate_only']:
    raise SystemExit('Unexplained reconstruction difference: ' + str((unexplained_code,unexplained_metadata,rebuilt['binary_api_differences'])))
result = {'source_commit':'daf3da94e3cdba0ac6a289148d7e38bd53d3fe64',
          'legacy_sha256':base['legacy_sha256'],'baseline_sha256':base['candidate_sha256'],
          'reconstructed_sha256':rebuilt['candidate_sha256'],
          'class_count':len(classes), 'class_categories':dict(collections.Counter(x['category'] for x in classes.values())),
          'binary_api_differences':base['binary_api_differences'], 'generic_public_api_display_differences':base['public_api_differences'],
          'classfile_versions':sorted({x['legacy_metadata']['major'] for x in base['classfiles'].values()}),
          'attribute_kinds':sorted({k for x in base['classfiles'].values() for side in ('legacy_metadata','candidate_metadata') for k in x[side]['attribute_census']}),
          'resources':base['resources'], 'reconstructed_inner_reference_changes':inner_reference_changes,
          'reconstruction_unexplained_code':unexplained_code,'reconstruction_unexplained_metadata':unexplained_metadata,
          'reconstructed_code_header_differences':code_header_changes,
          'classes':classes}
root = pathlib.Path(__file__).resolve().parent.parent
result['comparison_sources_sha256'] = {
    str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [*(root/'tools'/name for name in ('compare-jars.py','classify-bytecode.py','classfile_metadata.py','summarize-bytecode-audit.py','build-baseline.sh')),
                 root/'documentation/legacy-reconstruction.patch']}
a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print('Classified classes:',len(classes),result['class_categories'])
print('Unexplained reconstructed instruction/metadata differences: 0')
