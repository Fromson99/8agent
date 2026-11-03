"""User-directed SQLite test of byte-identical selected MAIN135."""
from pathlib import Path
import sys,json,shutil,hashlib
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1303-main135-nearai-answer-probe';ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1305-main135-nearai-sqlite';ART=ADR/'artifacts';DES=ART/'design'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for name in ('common.py','live.py','resource_guard.py','pinned_imports.py','authorization.py','audit.py','ledger.py','archive_runtime.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1303'/name).read_text().replace('ADR-1303-main135-nearai-answer-probe','ADR-1305-main135-nearai-sqlite').replace('adr_1303','adr_1305').replace('adr1303','adr1305').replace('ADR1303','ADR1305').replace('ADR-1303','ADR-1305')
 if name=='live.py':
  s=s.replace("assert arm in ('baseline','ontology-on')","assert arm=='sqlite'")
  begin=s.index(" if not case.get('synthetic'):\n")
  end=s.index(' from semantic_runtime.app import create_app',begin)
  s=s[:begin]+""" data=ROOT/read(DES/'baseline.json')['release']['data_path']
 source_manifest=read(data/'manifest.json')
 assert sha(data/'store.sqlite')==source_manifest['store_sha256']
 profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
 assert profile['candidate_navigation']['ontology_enabled'] is False
 # No Oracle connector is imported or opened in this experiment.
 if 'oracledb' in sys.modules:raise RuntimeError('SQLite experiment cannot load Oracle driver')
"""+s[end:]
  s=s.replace('if total>=120:', 'if total>=80:').replace('Global experiment120 physical cap','Global experiment80 physical cap')
  s=s.replace("'state_storage':'isolated local SQLite','oracle_writes':0", "'data_path':str(data.relative_to(ROOT)),'source_storage':'selected local SQLite','state_storage':'isolated local SQLite','oracle_connections':0,'oracle_writes':0")
  s=s.replace("getattr(getattr(sql_request,'sql',None),'calls',0)","None")
  s=s.replace("'selected_code_unchanged':all", "'oracle_driver_loaded':'oracledb' in sys.modules,'selected_code_unchanged':all")
 if name=='ledger.py':
  s=s.replace("for arm in ('baseline','ontology-on'):","for arm in ('sqlite',):")
 (T/name).write_text(s)
sys.path.insert(0,str(T));from common import put
DES.mkdir(exist_ok=False)
for name in ('baseline.json','scoring-only-originals.json','nearai-only.json','authorization.json','provider-endpoints.json','endpoint-check.json'):
 shutil.copyfile(OLD/'artifacts/design'/name,DES/name)
cases=read(OLD/'artifacts/design/cases.json')
for c in cases:c['arms']=['sqlite']
put(DES/'cases.json',cases)
criteria=read(OLD/'artifacts/design/criteria.json')
criteria.update(primary_metric='Complete supported answers /2 SQLite ordinary-RAG questions; each3 required rules, final versus intermediate findings separated.',success=['Both requests HTTP200, validated final claims cover all3 frozen source rules with correct conditions, scope and thresholds.','Source/version/ACL/wire match, NearAI only, no fallback/output cap, same saved answer on duplicate query with0new model calls.'],failure=['Source-only/incomplete and technical error are distinct from incorrect delivered answers.','UNKNOWN, resource stop or runner failure stops new sends. Known per-case model/API failure is preserved, next independent case may run once; no automatic cell retry.'],order=['ontology-365/baseline','ontology-369/baseline'],scope='Selected MAIN135516files exact; actual selected SQLite generation, no Oracle connector/connection; ordinary ontologyOFF default; isolated SQLite journals; source/reference text same as previous Oracle tests. Fresh process per question.',quality='Two known questions, single attempts; manual source-based scoring; externaljudge0. Not broad accuracy or provider causal comparison.',user_steering='오라클말고 sqli로 돌려보바ㅘ')
criteria['limits']['total_physical_calls']=80;put(DES/'criteria.json',criteria)
auth=read(DES/'authorization.json');auth['sqlite_instruction']=criteria['user_steering'];auth['total_physical_limit']=80
# Preserve the copied original approval and append a separate SQLite request grant.
put(DES/'sqlite-authorization.json',auth)
shutil.copytree(OLD/'artifacts/transport',ART/'transport')
release=read(DES/'baseline.json')['release'];code=ROOT/release['code_root'];data=ROOT/release['data_path']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation']==135
put(DES/'sqlite-source.json',{'data_path':release['data_path'],'manifest_sha256':sha(data/'manifest.json'),'store_sha256':sha(data/'store.sqlite'),'same_source_manifest_as_oracle':read(data/'manifest.json')['store_sha256']==read(DES/'baseline.json')['release'].get('store_sha256',read(data/'manifest.json')['store_sha256']),'oracle_connections':0})
put(DES/'inherited-admission.json',{'parent':str(OLD.relative_to(ROOT)),'routing_selfcheck':{'path':str((OLD/'artifacts/routing-selfcheck/result.json').relative_to(ROOT)),'sha256':sha(OLD/'artifacts/routing-selfcheck/result.json')},'same_product516':True,'network_mock_calls':0})
m=read(ADR/'실험/manifest.json');old=read(OLD/'실험/manifest.json')
for k in ('design','llm_policy','dataset','retrieval_accounting'):m[k]=old[k]
m['design'].update(primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1301-experiment-v1/verified'],'changes':'Inherited selected MAIN135 reference, no new calls','controls':'Same selected code'}, {'id':'sqlite','role':'candidate','derived_from':['ADR-1301-experiment-v1/verified'],'changes':'SQLite selected generation; ordinary defaultOFF; NearAI FP8 only','controls':'Same selectedMAIN135516productfiles, source version, questions, model/reasoning, prompt and budget'}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'sqlite':m['design']['retrieval_stage_plan']['stages_by_arm']['baseline']};m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']='User-directed selectedSQLite actual RAG evaluation, noOracle; sameNearAI andMAIN135.'
m['llm_policy']['provider_override'].update(path=str((DES/'nearai-only.json').relative_to(ROOT)),sha256=sha(DES/'nearai-only.json'))
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),version='20261103-selected-sqlite-v1')
m['runs'][0].update(arm_ids=['sqlite'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),selection_rule='Sameknown2publicquestions eachonce onSQLite;NearAIonly;nogoldreferencesinproduct;stopUNKNOWN/resource;preservefailedcells')
for q in m['questions']:
 p=next((OLD/'실험').glob('*'+q['case_id']+'.md'));s=p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\nNot dispatched yet; SQLite2question design frozen.\n';s=s.replace('baseline=NearAI ordinary OFF,ontology-on=NearAI published ON','baseline=NearAI ordinaryOFF on selectedSQLite');(ADR/'실험'/q['file']).write_text(s)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((code/n).relative_to(ROOT)) for n in release['files']]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
candidate=ac.snapshot(ADR,'selected-main135',paths,experiment_id=m['experiment_id'],arm_id='sqlite',run_ids=['run-001']);ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];snap=candidate/'revisions'/rev['revision_id']/'snapshot'
put(DES/'candidate.json',{'code_root':str((snap/release['code_root']).relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':{'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']},'selected_files':release['files']})
print('Prepared selectedSQLite; two questions, MAIN135516, NearAIonly, Oracle0')
