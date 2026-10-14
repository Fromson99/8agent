"""Merge evaluated narrative code onto known R3 inventories, retaining field overlays."""
import ast,base64,difflib,gzip,hashlib,importlib.util,json,subprocess,zlib
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
NAME='GENOS_RAG_NARRATIVE_STREAM_20261013_R1'
A=ROOT/'04_EXPERIMENTS/ADR/ADR-0767-polished-narrative-qualification'
NEW=ROOT/json.loads((A/'artifacts/design/freeze.json').read_text())['code_root']
BASE=ROOT/'08_DEPLOYMENT/RELEASES/focused-rules-20261013-r1/code'
sha=lambda b:hashlib.sha256(b).hexdigest()
encoded=lambda o:(json.dumps(o,ensure_ascii=False,indent=2)+'\n').encode()
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
@lru_cache(maxsize=1)
def source_material():
 r1=OUT.with_name('rag_focused_rules_20261013_r1');r2=OUT.with_name('rag_focused_rules_20261013_r2');r3=OUT.with_name('rag_focused_rules_20261013_r3')
 b=load('narrative_r1_build',r1/'build_delivery.py');a=load('narrative_r2_apply',r2/'apply_patch.py');c=load('narrative_r3_apply',r3/'apply_patch.py')
 catalogue,states,budget=b.source_material();spec1=json.loads(gzip.decompress((r1/'PATCH_SPEC.json.gz').read_bytes()));spec2=json.loads(gzip.decompress((r2/'PATCH_SPEC.json.gz').read_bytes()));spec3=json.loads(gzip.decompress((r3/'PATCH_SPEC.json.gz').read_bytes()))
 finalstates=[]
 for state in states:
  payload={n:catalogue[h] for n,h in state['pins'].items()};manifest=json.loads(payload.pop('CODE_MANIFEST.json'))
  pin=a.signature(payload,manifest,spec1);patch=spec1['signatures'][pin]
  final={**payload,**{n:base64.b64decode(spec1['blobs'][p['after_sha256']]) for n,p in patch['patches'].items()}}
  pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
  for entry in pipeline['engines'].values():
   n=entry['manifest'];engine=json.loads(payload[n])
   for target in set(engine['files'])&set(patch['patches']):engine['files'][target]=sha(final[target])
   for target in spec1['engine_additions'].get(n,[]):engine['files'][target]=sha(final[target])
   final[n]=encoded(engine);entry['sha256']=sha(final[n])
  final['00_SYSTEM/PIPELINE.json']=encoded(pipeline);assert a.signature(final,manifest,spec1)==patch['output_signature']
  final.update(a.repinned(final,spec2));final.update(c.repinned(final,spec3));c.verify_bindings(final)
  # Restore a valid materialized code inventory for standalone test checkouts.
  manifest['files']=[{'path':n,'sha256':sha(v),'bytes':len(v)} for n,v in sorted(final.items())]
  final['CODE_MANIFEST.json']=encoded(manifest)
  finalstates.append({'label':state['label']+'/focused-r3','payload':final})
 return finalstates,budget

def paths():return [r['path'] for r in json.loads((A/'artifacts/design/integration.json').read_text())['changes'] if not r['path'].startswith('02_BACKEND/ENGINES/') and r['path']!='00_SYSTEM/PIPELINE.json']
@lru_cache(maxsize=None)
def merged(n,field):
 new=(NEW/n).read_bytes();old=(BASE/n).read_bytes() if (BASE/n).exists() else None
 if field in (None,old,new):return new
 assert old is not None,n
 with TemporaryDirectory(prefix='narrative-merge-') as td:
  d=Path(td)
  for name,raw in [('field',field),('base',old),('new',new)]:(d/name).write_bytes(raw)
  p=subprocess.run(['git','merge-file','-p','--diff3',str(d/'field'),str(d/'base'),str(d/'new')],capture_output=True)
  if p.returncode:
   dest=OUT/'merge-review'/f'{Path(n).name}.{sha(field)[:12]}.txt';dest.parent.mkdir(exist_ok=True);dest.write_bytes(p.stdout)
   raise ValueError('Review required '+str(dest))
  return p.stdout

def build():
 assert not (OUT/(NAME+'.zip')).exists(),'Preserve sealed delivery'
 app=load('narrative_apply',OUT/'apply_patch.py');states,budget=source_material();targets=paths()
 selected=json.loads((NEW/'00_SYSTEM/PIPELINE.json').read_bytes())
 additions={e['manifest']:[n for n in json.loads((NEW/e['manifest']).read_bytes())['files'] if n in targets] for e in selected['engines'].values()}
 spec={'revision':NAME,'signatures':{},'blobs':{},'budget_policy':budget,'engine_additions':additions};bindings=[];deltas=set()
 for state in states:
  before=state['payload'];manifest=json.loads(before['CODE_MANIFEST.json']);final=dict(before);patches={}
  for n in targets:
   raw=merged(n,before.get(n))
   if raw==before.get(n):continue
   if n.endswith('.py'):ast.parse(raw,feature_version=(3,10))
   final[n]=raw;h=sha(raw);spec['blobs'][h]=base64.b64encode(raw).decode();patches[n]={'before_sha256':sha(before[n]) if n in before else None,'after_sha256':h}
   if raw!=(NEW/n).read_bytes():deltas.add(n)
  pipeline=json.loads(before['00_SYSTEM/PIPELINE.json'])
  for e in pipeline['engines'].values():
   n=e['manifest'];engine=json.loads(before[n])
   for target in set(engine['files'])&set(patches):engine['files'][target]=sha(final[target])
   for target in additions.get(n,[]):engine['files'][target]=sha(final[target])
   final[n]=encoded(engine);e['sha256']=sha(final[n])
  final['00_SYSTEM/PIPELINE.json']=encoded(pipeline);app.verify_bindings(final)
  key=app.signature(before,manifest,spec);output=app.signature(final,manifest,spec)
  spec['signatures'][key]={'label':state['label'],'patches':patches,'output_signature':output}
  protected=['service.py',app.CONFIG,'02_BACKEND/semantic_runtime/runtime_cache.py','02_BACKEND/semantic_runtime/resident_data.py','02_BACKEND/semantic_runtime/legal_agent/transport.py','02_BACKEND/semantic_runtime/progress.py','02_BACKEND/semantic_runtime/chat_adapter.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py','02_BACKEND/semantic_runtime/unit_fulltext.py']
  assert all(final.get(n)==before.get(n) for n in protected)
  bindings.append({'label':state['label'],'before_signature':key,'after_signature':output,'protected_paths_unchanged':True})
 (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0));(OUT/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(encoded(bindings),mtime=0))
 (OUT/'SOURCE_BINDING.json').write_bytes(encoded({'candidate':'ADR0767/polished/rev001','candidate_code_root':str(NEW),'candidate_manifest_sha256':sha((ROOT/'02_BACKEND/lawrag/research/candidates/adr_0767/polished/candidate.json').read_bytes()),'source_files':{n:sha((NEW/n).read_bytes()) for n in targets},'field_composition_differences':sorted(deltas),'field_validation':'NOT_RUN','model_calls':0}))
 code=(OUT/'apply_patch.py').read_bytes();bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
 py=('import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'+"bundle=json.loads(raw);module=types.ModuleType('narrative_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
 old=(OUT.with_name('rag_focused_rules_20261013_r1')/'GENOS_RAG_FOCUSED_RULES_20261013_R1_RUN.txt').read_text()
 run=old[:old.index('python3 - "$@"')].replace('rag-focused-rules-r1','rag-narrative-stream-r1').replace('FOCUSED_RAG','NARRATIVE_RAG')+'python3 - "$@" <<\'NARRATIVE_RAG_PY\'\n'+py+'NARRATIVE_RAG_PY\n'
 (OUT/(NAME+'_RUN.txt')).write_text(run);subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
 (OUT/'HANDOFF.json').write_bytes(encoded({'version':NAME,'source_candidate':'ADR0767/polished/rev001','known_r3_inventories':len(bindings),'source_code_root':str(NEW),'run_txt_sha256':sha(run.encode()),'field_code_root':'~/DEV','field_git_commit':None,'field_generation':None,'field_generation_manifest_sha256':None,'field_code_serving_revision':None,'genos_applied':False,'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT','rebuild_required':False,'workflow_editor_change_required':False,'source_status':'evaluation_in_progress'}))
 print(json.dumps({'inventories':len(bindings),'variants':len(spec['blobs']),'field_differences':sorted(deltas)}),flush=True)
if __name__=='__main__':build()
