"""Prepare a bounded compatibility check of selected MAIN120 and existing Gold."""
from pathlib import Path
import hashlib,json,sys,shutil
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1212-gold-main120-engine-check'
D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(pointer);assert active['generation']==120
release=read(R/active['manifest_path']);C=R/release['code_root']
assert all(sha(C/n)==h for n,h in release['files'].items())
put(D/'baseline.json',{'active':active,'pointer_sha256':sha(pointer),'release':release})
G=R/'08_DEPLOYMENT/LOCAL/gold_connection_cm_r12'
for n in ('config_b03.json','documents.json'):shutil.copyfile(G/n,D/n)
criteria={'hypothesis':'The unchanged selected MAIN120 reasoning engine can consume the existing R12 CM Gold projection through its Oracle Store interface.',
 'success_criteria':['Exact MAIN120 selected code, no corpus SQLite fallback and read-only Gold connection','Application initialization, native API source-only request, glossary, navigation references and original read all succeed','If preflight succeeds, one CM007 and one CM009 real model request reach an explicit final response with source/hash/ACL checks; failures retained','Identify whether the existing engine actually calls the Gold vector reader; availability alone is not vector use','MAIN pointer/product code/Gold publications unchanged, no capacity expansion or heavy parallel run'],
 'failure_criteria':'Any missing descriptor/table, incompatible source/query contract, bootstrap/API error, source/ACL violation, UNKNOWN or missing final response fails end-to-end compatibility. Never replace missing assets with empty stand-ins or original SQLite to obtain a pass.',
 'selection':'Known CM007 and CM009 from prior frozen requests, question only, all 21 published documents. No reference answer or expected coordinates in model input.',
 'plan':['Read-only engine preflight and native source-only API; independent required-port checks','Only after every preflight gate passes: CM007 once, then CM009 once unless integrity/resource/UNKNOWN stop','Preserve errors and report exact missing connection requirements; no product or Gold publication repair in this diagnostic'],
 'resources':{'minimum_available_RAM_GiB':5,'minimum_free_disk_GiB':20,'max_RSS_GiB':4,'max_swap_growth_MiB':128,'one_heavy_process':True,'local_preflight_seconds':600,'live_case_wall_seconds':1800,'max_physical_per_case':40},
 'boundaries':{'state':'Explicit experiment-local request journals only; this does not certify production NFS/CIFS deployment','vector':'Use existing selected engine retrieval policy unchanged; separately inspect actual vector wiring','main_wiring':'unchanged','legal_quality_certified':False,'automatic_retry':False,'external_calls_if_preflight_fails':0}}
put(D/'criteria.json',criteria)
cases=[]
for adr in ('ADR-1198-main117-live-cm007','ADR-1205-need-continuity-live-cm009'):
    rows=read(R/'04_EXPERIMENTS/ADR'/adr/'artifacts/design/cases.json')
    for c in rows:
        if c['id'] in ('cm-007','cm-009') and c['id'] not in [x['id'] for x in cases]:
            c['request']['json']['document_ids']=[d['document_id'] for d in read(D/'documents.json')['documents']];cases.append(c)
assert {c['id'] for c in cases}=={'cm-007','cm-009'}
put(D/'cases.json',cases)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Unmodified engine/Gold interface and end-to-end compatibility',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,criteria_freeze_evidence={'artifact_path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')},execution=criteria)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1208-experiment-v1/gold-b03'],'changes':'Historical completed Gold data API contracts only','controls':'Same sealed Gold publications; historical result, not reexecuted'},{'id':'gold-engine','role':'candidate','derived_from':['baseline'],'changes':'Explicit injection of existing Gold SQL transport into selected MAIN120 Oracle Store and native app','controls':'No engine code changes, no SQLite corpus fallback, no schema or prompt changes'}]
m['runs'][0].update(arm_ids=['gold-engine'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='R12 CM21 Gold / known CM007 and CM009',version='MAIN120 plus ADR1208 sealed projection',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[]
m['retrieval_accounting']['not_applicable_reason']='Compatibility gate first; no retrieval-quality comparison. Actual candidates recorded if engine reaches retrieval.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='Compatibility diagnostic; no measured retrieval-quality claim. Failed stages remain failed.'
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
target='08_DEPLOYMENT/LOCAL/gold_connection_r12/gold_connection.py'
S=ac.snapshot(A,'gold-engine',[target],experiment_id=m['experiment_id'],arm_id='gold-engine',run_ids=['run-001'])
previous=R/'02_BACKEND/lawrag/research/candidates/adr_1208/gold-b03/revisions/rev-021/snapshot'/target
shutil.copyfile(previous,S/'snapshot'/target)
put(D/'candidate.json',{'root':str(S.relative_to(R))})
print(S/'snapshot')
