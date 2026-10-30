from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1164-genos-vector-initial-build';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
a=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');m=read(R/a['manifest_path']);files=list(m['files']);extra=['02_BACKEND/lawrag/pipeline/oracle_query_dataiku.py']
files+=extra
put(D/'baseline.json',{'active':a,'manifest':m,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(R/n) for n in files}})
criteria={'scope':'technical implementation audit, not legal quality promotion','requirements':['existing keyword/exact/READ contracts preserved','Oracle vector release immutable and CAS activation','same source/vector/profile and authorized source IDs before top100','embedding finite normalized unique index complete no model fallback','navigation vector first20 same order and paging reuse','Dataiku recipe bounded source reads, restart verified rows, partial release never active','packaged service dependency/pins match tested bytes','SQL supported by actual isolated local Oracle and mocked internal embedding','no generation model calls or field deployment claims'], 'numbers':{'display':20,'candidate_roots':100,'chunk_chars':800,'overlap_chars':100,'embedding_batch':16},'failure':'Any new invariant violation blocks promotion; failure artifact preserved before new candidate revision. Existing historical failures separately recorded.'}
put(D/'criteria.json',criteria)
f=read(A/'실험/manifest.json');f['design'].update(hypothesis='GENOS native embedding and Oracle vector initial candidates can attach to existing source navigation and a Dataiku resumable publication without changing exact/READ/ACL contracts.',primary_metric='prospectively fixed technical contracts only',success_criteria=criteria['requirements'],failure_criteria=criteria['failure']);f['llm_policy']['llm_calls']=[];f['dataset'].update(name='Synthetic independent technical vector/publication fixtures',version='v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));f['runs'][0].update(arm_ids=['integrated'],selection_rule='Technical synthetic contracts, actual local Oracle, no live model calls',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));f['retrieval_accounting'].update(changed=False,not_applicable_reason='Technical API/storage invariant tests, no legal retrieval benchmark',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':None,'sha256':None,'not_applicable_reason':'Synthetic API/storage contracts only'});f['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}};put(A/'실험/manifest.json',f)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(A,'integrated',files,experiment_id=f['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n in m['files']:
 shutil.copyfile(R/m['code_root']/n,S/n)
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
print(S)
