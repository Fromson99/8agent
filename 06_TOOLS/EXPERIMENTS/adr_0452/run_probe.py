"""Gold-free product runner. No automatic retries, prompt changes, or source exports."""
import argparse,time,sys
from runtime import *

def prepare():
 if (A/'input-lock.json').exists():raise ValueError('already sealed')
 m=read(D/'실험/manifest.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1]
 m['design']['code_isolation']['candidates']=[{'candidate_id':'mapped','experiment_id':m['experiment_id'],'arm_id':'mapped','run_ids':['run-001'],'manifest_path':rel(C/'candidate.json'),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':rel(__file__),'runner_sha256':sha(__file__)}]
 (D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 paths=list(T.glob('*.py'))+list((A/'dataset').glob('*.json'))+[A/'grading/gold.json',A/'design-before-snapshot.json',A/'authorization.json',A/'source-inventory.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',C/'candidate.json']+[R/f['frozen_path'] for f in rev['files']]
 # Transitive selected frozen generations and runtime bindings, never arbitrary newest files.
 for n in [445,446,447,448,449,450,451]:
  folder=R/f'02_BACKEND/lawrag/research/candidates/adr_{n:04d}'
  for manifest in folder.glob('*/candidate.json'):
   cm=read(manifest)
   if cm['revisions']:paths+=[manifest]+[R/f['frozen_path'] for f in cm['revisions'][-1]['files']]
  tools=R/f'06_TOOLS/EXPERIMENTS/adr_{n:04d}';paths+=list(tools.glob('runtime.py'))+list(tools.glob('binding_runtime.py'))
 new(A/'input-lock.json',{'files':{rel(p):sha(p) for p in sorted(set(paths))},'gold_visible_to_product':False});new(A/'pre-call-manifest.json',m);print('sealed',len(set(paths)),'inputs')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');args=ap.parse_args()
 if args.prepare:return prepare()
 if (A/'runs').exists():raise ValueError('already run: preserve failures, use a new ADR')
 for p,h in read(A/'input-lock.json')['files'].items():
  if sha(R/p)!=h:raise ValueError('input drift '+p)
 mod,typed,multi,mods,root,binding=load();limits=read(A/'pre-call-manifest.json')['design']['limits'];cases=read(A/'dataset/product-cases.json');results={};(A/'runs').mkdir();started=time.monotonic()
 for i,case in enumerate(cases):
  cid=case['id']
  for arm in ARMS[i%2:]+ARMS[:i%2]:
   store,m,g=build(multi);client=binding.GeminiExperimentClient(R,A/'calls'/cid/arm,max_calls=limits['max_calls']*(2 if case['followup'] else 1));began=time.monotonic();ledger=A/'ledgers'/f'{cid}-{arm}.sqlite';mapping=mod.MappingStore(ledger,m,store.manifest,case['scope_document_ids'],'synthetic-user')
   for item in case['initial_mappings']:mapping.add(item['expression'],item['target'],'사전 고정한 사용자 입력; 정답 라벨 아님')
   p=mods['pipeline'].Pipeline(root,store,binding.Provider(client));c=binding.conversation(arm,mod,typed,p,m,g,case['scope_document_ids'],ledger,limits)
   try:
    out=c.run(case['question']);p.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result');record={'case_id':cid,'arm_id':arm,'output':out,'downstream_contract':'PASS','mappings_after_first':mapping.list()}
    if case['followup']:
     proposals=(out.get('retrieval') or {}).get('term_agent',{}).get('mapping_proposal_ids',[])
     record['simulated_user_review']=mapping.review(proposals[0],'APPROVED','사전 지정 절차: 사용자가 첫 제안 선택') if proposals else None
     c=binding.conversation(arm,mod,typed,p,m,g,case['scope_document_ids'],ledger,limits);record['followup_output']=c.run(case['followup']);p.contracts.validate(record['followup_output'],'urn:8-agent:term-runtime-v1','Result');record['mappings_after_followup']=mapping.list()
   except Exception as e:record={'case_id':cid,'arm_id':arm,'output':None,'downstream_contract':'FAIL','failure':{'type':type(e).__name__,'message':str(e)}}
   finally:store.db.close()
   record.update(calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-began);new(A/'runs'/f'{cid}-{arm}.json',record);results.setdefault(cid,{})[arm]=record
   s=(record.get('output') or {}).get('retrieval',{}).get('term_agent',{});print(json.dumps({'case':cid,'arm':arm,'calls':client.calls,'status':s.get('status'),'kind':s.get('navigation_output',{}).get('kind'),'documents':s.get('catalogue',{}).get('total'),'read':len(s.get('read_source_ids',[])),'failure':record.get('failure') or s.get('failure')},ensure_ascii=False),flush=True)
 new(A/'results.json',{'cases':results,'elapsed_seconds':time.monotonic()-started,'main_wiring':'unchanged','gold_visible_to_product':False})
if __name__=='__main__':main()
