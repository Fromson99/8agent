from common import *
import shutil,subprocess,ast
f=read(sorted(DES.glob('freeze-*.json'))[-1]);C=ROOT/f['code_root'];b=read(DES/'baseline.json')
tech=read(ART/'check-final.json');reg=read(ART/'regression-comparison.json')
assert tech['all_passed'] and not reg['new_regressions'] and not reg['status_differences']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
changed=[n for n,h in f['files'].items() if b['manifest']['files'].get(n)!=h]
engines={r['manifest'] for r in read(C/'00_SYSTEM/PIPELINE.json')['engines'].values()};pins=engines|{'00_SYSTEM/PIPELINE.json'}
products=[n for n in changed if n not in pins]
assert set(products)=={'02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('completion_execution.py','completion_v8.py','completion_contracts.py')}
for n,h in f['files'].items():assert sha(C/n)==h,n
for n,h in b['working_files'].items():assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==h,'Concurrent working modification: '+n
put(DES/'staging-final.json',{'code_root':str(C.relative_to(ROOT)),'files':f['files'],'changed':changed})
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','final-answer-preview-20261029-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files']
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Integrate final scope prompts and remove unsupported generic limitation; retain MAIN115 accumulated contracts.'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
for n in products+sorted(pins):
 dest=ART/'working-backup'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
# Replace only reviewed constant nodes in working code; preserve journal_text cache changes.
for n,key in [('02_BACKEND/semantic_runtime/legal_agent/completion_execution.py','MODERN_ASSESS_PROMPT'),('02_BACKEND/semantic_runtime/legal_agent/completion_v8.py','PROMPT')]:
 def node(t):return next(x for x in ast.parse(t).body if isinstance(x,ast.Assign) and any(isinstance(y,ast.Name) and y.id==key for y in x.targets))
 old=(ROOT/n).read_text();new=(C/n).read_text();a=node(old);z=node(new);lines=old.splitlines(True)
 out=''.join(lines[:a.lineno-1])+''.join(new.splitlines(True)[z.lineno-1:z.end_lineno])+''.join(lines[a.end_lineno:])
 before_tree=ast.parse(old);after_tree=ast.parse(out)
 for tree in (before_tree,after_tree):
  for x in tree.body:
   if isinstance(x,ast.Assign) and any(isinstance(y,ast.Name) and y.id==key for y in x.targets):x.value=ast.Constant('PROMPT')
 assert ast.dump(before_tree)==ast.dump(after_tree)
 (ROOT/n).write_text(out)
n='02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
assert sha(ROOT/n)==b['manifest']['files'][n]
shutil.copyfile(C/n,ROOT/n)
for n in engines:
 p=ROOT/n;v=read(p)
 for path in v['files']:v['files'][path]=sha(ROOT/path)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(ROOT/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
protected=[n for n in b['working_files'] if n not in products and n not in pins]
assert all(sha(ROOT/n)==b['working_files'][n] for n in protected)
put(ART/'working-integration.json',{'product_files':{n:sha(ROOT/n) for n in products},'pins':{n:sha(ROOT/n) for n in pins},'changed_files':changed,'protected_files':len(protected),'protected_unchanged':True,'prompt_only_merge_preserved_working_ast':True,'new_model_calls':0})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
print('Integrated',len(products),'product files; serving changed',len(changed),'inventory',len(actual))
