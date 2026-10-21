"""Frozen live command interpretation, synthetic metadata only, no retrieval."""
from pathlib import Path
from types import SimpleNamespace as S
import sys,json,hashlib,time
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0957-multiturn-structured-scope/artifacts'
stage=A/'code';sys.path[:0]=[str(stage/'02_BACKEND'),str(R/'02_BACKEND')]
from semantic_runtime.legal_agent.corrected_memory import Memory
from semantic_runtime.legal_agent import query_scope as qs
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def run():
 seal=json.loads((A/'stage.json').read_text())
 for n,h in seal['files'].items():assert sha(stage/n)==h,n
 manifest=json.loads((A.parent/'실험/manifest.json').read_text())
 dataset=A/'command-cases.json';assert sha(dataset)==manifest['dataset']['sha256']
 candidate=R/manifest['design']['code_isolation']['candidates'][0]['manifest_path'];c=json.loads(candidate.read_text())
 assert sha(candidate)==manifest['design']['code_isolation']['candidates'][0]['manifest_sha256']
 for row in c['revisions'][-1]['files']:
  assert sha(R/row['frozen_path'])==row['snapshot_sha256']
  target=next(r['target_path'] for r in c['files'] if r['snapshot_path']==row['snapshot_path'])
  assert sha(stage/target)==row['snapshot_sha256']
 client=ExperimentClient(R,A/'model',max_calls=28,max_output_tokens=1600)
 profile=json.loads((stage/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
 executor=S(binding={'code':sha(candidate),'data':'synthetic-scope-metadata-v1'},
  model=S(pipeline=S(term_agent=S(profile=profile))))
 repo=Memory(A/'command.sqlite',executor,lambda system,data,schema,phase:client.generate(system,data,schema,phase=phase))
 results=[];started=time.monotonic()
 for item in json.loads(dataset.read_text()):
  if time.monotonic()-started>600:raise RuntimeError('predeclared experiment deadline')
  context=item['context'];context['allowed_documents']=[{'id':str(i),'name':str(i)} for i in range(161)]
  result=repo.resolve(context);expected=item['expected'];scope=result.get('search_scope_change',{'operation':'KEEP','targets':[]})
  checks={'same_goal':result.get('target')==expected['target'],
   'operation':scope['operation']==expected['operation'],
   'document_inventory_null':result.get('document_ids') is None,
   'method':result.get('method_id') in expected['methods'],
   'document':not expected.get('document') or any(t.get('document')==expected['document'] for t in scope['targets']),
   'structure':not expected.get('structure') or any(t.get('structure')==expected['structure'] for t in scope['targets'])}
  results.append({'id':item['id'],'command':result,'checks':checks,'pass':all(checks.values())})
  save(A/'command-results.json',{'results':results,'model_calls':client.calls,'elapsed_seconds':time.monotonic()-started})
  print(item['id'],all(checks.values()),flush=True)
 repo.close()
 assert all(r['pass'] for r in results), 'command criteria failed; do not promote'
if __name__=='__main__':run()
