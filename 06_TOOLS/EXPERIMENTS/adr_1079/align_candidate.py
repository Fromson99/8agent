"""Merge three performance hunks into a new unexecuted ontology revision.

This prepares candidate code only. Completion parents, active MAIN binding and
the live design freeze remain blocked until the owner verifies them separately.
"""
import ast
from pathlib import Path
import json
import sys
from common import ROOT, ART, read, save, sha, exact_write
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as candidates


def node_text(text,name):
    node=next(n for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
    return ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('ambiguous hunk: '+old[:100])
    return text.replace(old,new,1)


def edit_function(text,name,changes):
    before=node_text(text,name);after=before
    for old,new in changes:after=replace_once(after,old,new)
    return replace_once(text,before,after)


def main():
    plan=read(ART/'main105-alignment-plan.json')
    checked=ROOT/plan['performance_design']['path']
    assert sha(checked)==plan['performance_design']['sha256']
    source=ROOT/plan['performance_code_root'];base=ROOT/plan['base_unexecuted_revision']
    directory=base.parent.parent.parent;code=directory/'snapshot'
    manifest=read(directory/'candidate.json')
    assert len(manifest['revisions'])==1,'only one unexecuted revision expected'
    old_map={r['target_path']:r['snapshot_sha256'] for r in manifest['files']}
    assert all(sha(code/p)==h and sha(base/p)==h for p,h in old_map.items())
    for p,h in plan['source_hunks'].items():assert sha(source/p)==h
    relative='02_BACKEND/semantic_runtime/legal_agent/unit_relations.py'
    text=(code/relative).read_text();perf=(source/relative).read_text()
    helpers='\n\n'.join(node_text(perf,n).rstrip() for n in
        ('_UncacheablePreparation','_preparation_key','CatalogReadPreparation'))+'\n\n'
    old=node_text(text,'acquired_blocks')
    text=replace_once(text,old,helpers+node_text(perf,'acquired_blocks'))
    text=edit_function(text,'catalog',[
        ('max_connections=None, grant_reads=True):','max_connections=None, grant_reads=True, preparation=None):'),
        ('acquired_blocks(s, selected)','acquired_blocks(s, selected, preparation=preparation)')])
    (code/relative).write_text(text)
    relative='02_BACKEND/semantic_runtime/legal_agent/connection_scope.py'
    text=(code/relative).read_text()
    text=edit_function(text,'offer_choices',[
        ('    from .law_candidates import token\n','    from .law_candidates import token\n    from .unit_relations import CatalogReadPreparation\n    preparation = CatalogReadPreparation()\n'),
        ('inspect_directory(inv, scope)','inspect_directory(inv, scope, preparation=preparation)')])
    text=edit_function(text,'inspect_directory',[
        ('def inspect_directory(inv, scope):','def inspect_directory(inv, scope, *, preparation=None):'),
        ('preview(inv, scope)','preview(inv, scope, preparation=preparation)'),
        ('rel.acquired_blocks(inv.s, inv.read_records())','rel.acquired_blocks(inv.s, inv.read_records(), preparation=preparation)')])
    text=edit_function(text,'preview',[
        ('def preview(inv, scope):','def preview(inv, scope, *, preparation=None):'),
        ('max_connections=None)','max_connections=None, preparation=preparation)')])
    (code/relative).write_text(text)
    relative='02_BACKEND/semantic_runtime/search_selection.py'
    before=(code/relative).read_text();after=(source/relative).read_text()
    old="view(name, 'original.reference_id IN (SELECT id FROM temp.reference)')"
    new="view(name, 'EXISTS (SELECT 1 FROM temp.reference r WHERE r.id=original.reference_id)')"
    assert replace_once(before,old,new)==after,'SQL source has changes beyond the declared membership hunk'
    (code/relative).write_text(after)
    for relative in plan['preserve_exact']:assert sha(code/relative)==old_map[relative]
    for path in (code/'02_BACKEND/ENGINES').rglob('*.json'):
        obj=read(path)
        if isinstance(obj.get('files'),dict):
            obj['files']={p:sha(code/p) for p in obj['files']};save(path,obj)
    path=code/'00_SYSTEM/PIPELINE.json';obj=read(path)
    for engine in obj['engines'].values():engine['sha256']=sha(code/engine['manifest'])
    def visit(value):
        if isinstance(value,dict):
            if isinstance(value.get('path'),str) and 'sha256' in value and (code/value['path']).is_file():
                value['sha256']=sha(code/value['path'])
            for k,v in list(value.items()):
                if k.endswith('_path') and isinstance(v,str) and k[:-5]+'_sha256' in value and (code/v).is_file():
                    value[k[:-5]+'_sha256']=sha(code/v)
                visit(v)
        elif isinstance(value,list):
            for row in value:visit(row)
    visit(obj);save(path,obj)
    new_map={p:sha(code/p) for p in old_map}
    changed=[p for p in new_map if old_map[p]!=new_map[p]]
    product=[p for p in changed if p.endswith('.py')]
    assert set(product)==set(plan['permitted_product_files'])
    assert len(changed)==34 and all(p in product or p=='00_SYSTEM/PIPELINE.json'
        or p.startswith('02_BACKEND/ENGINES/') for p in changed)
    candidates.refresh(directory);candidates.freeze(directory)
    assert candidates.validate(directory)==[]
    final=read(directory/'candidate.json');revision=final['revisions'][-1]
    assert revision['revision_id']=='rev-002'
    frozen=directory/'revisions/rev-002/snapshot'
    assert {str(p.relative_to(frozen)):sha(p) for p in frozen.rglob('*') if p.is_file()}==new_map
    exact_write(ART/'main105-alignment-rev2.json',{'schema_version':'adr1079-alignment-prepared-v1',
        'code_root':str(frozen.relative_to(ROOT)),'candidate_manifest':str((directory/'candidate.json').relative_to(ROOT)),
        'candidate_manifest_sha256':sha(directory/'candidate.json'),'revision_id':'rev-002',
        'revision_sha256':revision['revision_sha256'],'files':new_map,'old_files':old_map,
        'changed_files':[{'path':p,'before':old_map[p],'after':new_map[p]} for p in changed],
        'source_plan':{'path':str((ART/'main105-alignment-plan.json').relative_to(ROOT)),
            'sha256':sha(ART/'main105-alignment-plan.json')},'performance_source_files':plan['source_hunks'],
        'final_parents_bound':False,'main_binding_verified':False,'live_design_frozen':False,
        'model_calls':0,'real_corpus_loads':0,'working_code_changed':False})
    print(json.dumps({'revision':'rev-002','files':len(new_map),'changed':len(changed),'product':product,'live_authorized':False}))


if __name__=='__main__':main()
