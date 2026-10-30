from pathlib import Path
import json,hashlib,sys,shutil
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
P=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(P);assert active['generation']==120
release=read(R/active['manifest_path']);C=R/release['code_root'];assert all(sha(C/n)==h for n,h in release['files'].items())
put(D/'baseline.json',{'active':active,'pointer_sha256':sha(P),'release':release})
previous=R/'04_EXPERIMENTS/ADR/ADR-1212-gold-main120-engine-check/artifacts/design'
for n in ('documents.json','cases.json','config_b03.json'):shutil.copyfile(previous/n,D/n)
criteria={'hypothesis':'A separately published and scoped R12 extension plus explicit runtime adapter can satisfy unchanged MAIN120 source/search/navigation/glossary/vector contracts within the existing 13-table/60-column shape and 9.6GB Oracle cap.',
 'success_criteria':['Exact selected487 engine bytes and ACTIVE pointer preserved; only separate connection/publisher code changes','Required navigation rows and actual latest-selection proof, complete required glossary serving tables and reference reader contract supplied with immutable source/code bindings','Reuse sealed old rows by explicit hash-pinned publication inheritance; no serving SQLite source fallback, no whole corpus copy','Gold vector initial-search adapter uses same1024-dimension BGE-M3 model/preprocessing and exact scoped cosine; negative ACL/profile/hash/publication tests reject','Native startup/resources/source-only API pass, then CM007 and CM009 each once through real selected engine and policy transport with bounded budget and full raw/source audit','No Oracle user-data sum above9.6e9 bytes, disk reserve80GiB, running RAM reserve3GiB; no hidden dropping of required CM21 documents'],
 'failure_criteria':'No publish/activate on partial rows, stale source/code, missing required metadata, unknown writer outcome, ACL widening or failed readback. No empty glossary stand-in, forged proof, blind retries or model-answer rewriting. Preserve actual failed/limited answers separately from connector success.',
 'scope':'CM21 all original documents and dependency-complete serving projections. First inventory the full glossary serving-table set, excluding authoring/job/event history never used by the existing reader. If this cannot fit, stop before DB import and report measured shortfall; do not silently thin glossary.',
 'storage':'Add immutable extension rows/manifest in existing SRCH_ROW/SRCH_POST; inherit unchanged row kinds via explicit validated parent manifest. New separate channel cm-r12-engine. Prior cm-r12 stays valid. No existing publication mutation.',
 'vector':'Existing R12 vectors may be physically shared only when original query/source/doc/model/input identities are verified; wrapper records both current query pin and vector source-query pin. No regenerate unless needed. Local CPU encoder explicit, no embedding endpoint fallback.',
 'models':{'cases':['cm-007','cm-009'],'repeats':1,'physical_per_case':40,'tools_per_case':1024,'wall_seconds_per_case':1800,'provider':'selected MAIN120 Parasail FP8, confirmed429 only NearAI once','stop':'UNKNOWN, integrity/resource stop ends live batch; output rejection retained; no automatic same-case rerun','reference_answers_in_input':False},
 'resources':{'oracle_total_bytes_max':9600000000,'free_disk_GiB':80,'startup_available_GiB':5,'running_available_GiB':3,'worker_RSS_GiB':5,'swap_growth_MiB':128,'cpu_threads':4,'heavy_parallel':1},
 'failures':{'publisher':'single owner lease and resumable exact-prefix import; on uncertainty reconcile persisted rows before continuing; never activate partial','runtime':'existing engine error taxonomy and one owned model repair path; interface failures not converted to empty results','activation':'separate channel CAS; unchanged legacy channel; rollback by leaving new channel unused'},
 'assessment':'Known in-sample integration probes; not legal accuracy certification, GENOS deployment or MAIN promotion.'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Native unchanged-engine R12 integration and bounded real CM execution',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,criteria_freeze_evidence={'artifact_path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')},execution=criteria)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1212-experiment-v1/gold-engine'],'changes':'Historical failed compatibility probe','controls':'MAIN120/R12 same source corpus'},{'id':'connected','role':'candidate','derived_from':['baseline'],'changes':'Separate Gold data extension and explicit runtime adapter','controls':'Same MAIN120487files, unchanged model/schema/validators; same21documents'}]
m['runs'][0].update(arm_ids=['connected'],selection_rule='Deterministic CM21 dependencies and existing reader serving tables; CM007 thenCM009 one real run each after local gates',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='R12 CM21 engine integration',version='MAIN120/ADR1208source',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['retrieval_accounting']['not_applicable_reason']='Will replace with actual stage ledger if model retrieval starts; technical port checks are not recall.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='Pending native integration gates; no retrieval score before model execution.'
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
target='08_DEPLOYMENT/LOCAL/gold_connection_r12/gold_connection.py'
S=ac.snapshot(A,'connected',[target],experiment_id=m['experiment_id'],arm_id='connected',run_ids=['run-001'])
shutil.copyfile(R/'02_BACKEND/lawrag/research/candidates/adr_1208/gold-b03/revisions/rev-021/snapshot'/target,S/'snapshot'/target)
put(D/'candidate.json',{'root':str(S.relative_to(R))});print(S/'snapshot')
