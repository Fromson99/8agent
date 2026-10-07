"""Seal public provenance, identical base runtime and explicit candidate before sends."""
from pathlib import Path
import json, hashlib, shutil, datetime, sqlite3, sys, os
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0554-qwen38-catalogue-first-routing'
P=R/'04_EXPERIMENTS/ADR/ADR-0496-qwen-source-workflow-cm51-fsc10'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0554/catalogue-router'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8388608):h.update(b)
 return h.hexdigest()
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 assert not (A/'artifacts/frozen-design.json').exists()
 fixture=read(A/'product-cases.json');gen=R/fixture['generation'];manifest=read(gen/'manifest.json')
 grant=read(P/'artifacts/export-rebinding.json');policy=A/'artifacts/scoped-model-policy.json'
 assert set(grant['scope_document_ids'])==set(fixture['public_scope_document_ids'])
 assert grant['source_store_sha256']==manifest['store_sha256']==sha(gen/'store.sqlite')
 assert grant['generation_id']==manifest['generation_id']
 assert grant['source_authorization_sha256']==sha(R/'08_DEPLOYMENT/CONFIG/legal-source-export.json')
 for doc in grant['document_provenance']:
  assert sha(R/'01_DATA/RAW'/doc['raw_relative_path'])==doc['raw_sha256']
 grant.update(experiment_policy_path=str(policy.relative_to(R)),policy_sha256=sha(policy),model='qwen/qwen3.8-27b',
              basis='Explicit latest user model and experiment authorization; same hash-proven public originals; immutable flags unchanged',parent_rebinding_sha256=sha(P/'artifacts/export-rebinding.json'))
 write(A/'artifacts/export-rebinding.json',grant)
 rev=read(C/'candidate.json')['revisions'][-1]
 roots={arm:str((A/'artifacts/sealed-runtime'/arm).relative_to(R)) for arm in ('baseline','catalogue-router')}
 for arm,root in roots.items():
  target=R/root
  for part in ('02_BACKEND/semantic_runtime','02_BACKEND/ENGINES','00_SYSTEM'):
   shutil.copytree(R/part,target/part,ignore=shutil.ignore_patterns('__pycache__','*.pyc'),dirs_exist_ok=True)
  for src in (R/'02_BACKEND/lawrag').rglob('*.py'):
   if 'candidates' in src.parts or '__pycache__' in src.parts:continue
   dst=target/src.relative_to(R);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
  for entry in read(R/'00_SYSTEM/PIPELINE.json')['engines'].values():
   for file in read(R/entry['manifest'])['files']:
    dst=target/file
    if not dst.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/file,dst)
  for profile in read(R/'00_SYSTEM/PIPELINE.json')['profiles'].values():
   for node in profile.get('nodes',[]):
    term=node.get('parameters',{}).get('term_agent')
    if not term:continue
    idx=Path(term['index']['path'])
    parts=[idx]
    if term.get('fulltext'):parts.append(idx.parent/term['fulltext']['path'])
    for part in parts:
     if not (target/part).exists():shutil.copytree(R/part,target/part,copy_function=os.link)
    for key in ('origin_projections','alias_projections'):
     for binding in term.get(key,[]):
      part=Path(binding['path']);dst=target/part
      if not dst.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/part,dst)
  if arm=='catalogue-router':
   for row in rev['files']:
    rel=Path(row['frozen_path']).parts
    path=Path(*rel[rel.index('snapshot')+1:])
    if 'semantic_runtime' in path.parts:shutil.copyfile(R/row['frozen_path'],target/path)
  shared=next(row for row in rev['files'] if row['frozen_path'].endswith('/semantic_runtime/fulltext.py'))
  shutil.copyfile(R/shared['frozen_path'],target/'02_BACKEND/semantic_runtime/fulltext.py')
  sys.path.insert(0,str(target/'02_BACKEND'))
  # Rehash only this sealed runtime; MAIN/working descriptors untouched.
  from semantic_runtime.control import rehash_engines
  rehash_engines(target,apply=True)
  sys.path.pop(0)
 transport=next(row['frozen_path'] for row in rev['files'] if row['frozen_path'].endswith('/experiment_client.py'))
 m=read(A/'실험/manifest.json');runner=Path(__file__).with_name('run_probe.py')
 stages=[{'stage_id':'discovered','kind':'source','parent_stage_ids':[]},
         {'stage_id':'read','kind':'filter','parent_stage_ids':['discovered']},
         {'stage_id':'selected','kind':'select','parent_stage_ids':['read']},
         {'stage_id':'presented','kind':'present','parent_stage_ids':['selected']}]
 m['design']['retrieval_stage_plan']['stages_by_arm']={arm:stages for arm in roots}
 m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
     'candidate_id':'catalogue-router','experiment_id':m['experiment_id'],'arm_id':'catalogue-router','run_ids':['run-001'],
     'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
     'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
     'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}])
 m['dataset'].update(name='Historical CM core8 plus utility6, public145 only',version='20260929-catalogue-routing14',
     frozen_source=str((A/'product-cases.json').relative_to(R)),sha256=sha(A/'product-cases.json'),legal_version_checked=False,reference_version_checked=True)
 paths=[A/'PLAN.md',A/'product-cases.json',policy,A/'artifacts/export-rebinding.json',C/'candidate.json',
        R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',
        R/'02_BACKEND/lawrag/research/openrouter_legal_adapter.py',R/'06_TOOLS/COMMANDS/adr_structure.py']
 paths+=list(Path(__file__).parent.glob('*.py'))+[R/x['frozen_path'] for x in rev['files']]
 for root in roots.values():paths+=sorted(p for p in (R/root).rglob('*') if p.is_file() and '__pycache__' not in str(p) and (p.suffix in ('.py','.json') or '01_DATA' not in p.parts))
 paths+=[gen/x for x in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
 old={c['case_id']:P/'artifacts/run-001'/c['case_id']/'repaired/result.json' for c in fixture['cases'] if c['kind']=='legal'}
 paths+=[p for p in old.values() if p.exists()]
 design={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime_roots':roots,
     'generations':{arm:fixture['generation'] for arm in roots},'transport_path':transport,
     'scope_authorization':read(policy)['authorization'],
     'configs':{arm:{'model':'qwen/qwen3.8-27b','thinking_level':'none'} for arm in roots},
     'export_authorization':grant,'design':m['design'],'runs':m['runs'],
     'file_hashes':{str(p.relative_to(R)):sha(p) for p in paths},
     'grader_only_hashes':{str((A/'gold-cases.json').relative_to(R)):sha(A/'gold-cases.json')},
     'workers':3,'product_gold_visible':False,'model':'qwen/qwen3.8-27b','max_physical_calls':392,
     'historical_paths':{cid:str(p.relative_to(R)) for cid,p in old.items() if p.exists()}}
 write(A/'artifacts/frozen-design.json',design)
 m['llm_policy']['experiment_override']={'schema_version':'user-authorized-openrouter-product-v2',
     'policy_path':str(policy.relative_to(R)),'policy_sha256':sha(policy),
     'frozen_design_path':str((A/'artifacts/frozen-design.json').relative_to(R)),
     'frozen_design_sha256':sha(A/'artifacts/frozen-design.json')}
 write(A/'실험/manifest.json',m)
 print('Frozen',len(paths),'files; public145;14paired cases; no calls')
if __name__=='__main__':main()
