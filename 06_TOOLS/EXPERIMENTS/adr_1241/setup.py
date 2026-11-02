from pathlib import Path
import json,hashlib,sys,ast
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation';D=A/'artifacts/design';O=A/'artifacts/run-001';P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
D.mkdir(parents=True,exist_ok=True);O.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
put=write_summary
old=R/'04_EXPERIMENTS/ADR/ADR-1235-gold-ontology-transport-live';old2=R/'04_EXPERIMENTS/ADR/ADR-1232-gold-connected-live-revalidation'
cases=[read(old/'artifacts/design/cases.json')[0],next(x for x in read(old2/'artifacts/design/cases.json') if x['id']=='cm-009')];put(D/'cases.json',cases)
criteria=read(old/'artifacts/design/criteria.json');criteria.update(hypothesis='Selected MAIN125 fixes the Oracle scope-key port and current Gold ON/DB preserves original-evidence/claim namespaces and incomplete review; a real known ontology question reaches a saved answer, then a known vector question does. UNKNOWN must stop without later physical calls.',sample='gold-369 once; only after every ontology functional gate passes, cm-009 once; existing known questions, in-sample and not decision eligible.',deploy_scope='No code, DB content, MAIN selection or field deployment mutation. Actual selected MAIN125 with frozen R18 physical mapping.',failures='Any unknown, resource failure, source/ACL/wire mismatch or missing answer stops the suite. No repeated run or identical unknown retry. Native confirmed429 single provider switch only.');criteria['limits']['physical_model_total']=80;criteria['success']+=['On UNKNOWN zero later physical requests; this conditional check may pass while answer E2E fails','If first case passes, cm-009 real embedding/Oracle candidates/source/final saved answer with exact originals; no claim of vector causal improvement'];put(D/'criteria.json',criteria)
auth={'kind':'USER_AUTHORIZED_MAIN125_GOLD_LIVE','instruction':'일단 수정하고 진행해봐 (이전 실험해봐 요청의 수정 후 재검증)' ,'session_id':'01a18ae0-36ec-7663-aa8b-0aa6fb93ec6d','cases_sha256':sha(D/'cases.json'),'scope':'Exact two frozen questions; Gold article369 scope one then approved CM009 scope21 only after first full gate. Original sources/terms/approved ontology; no reference answer.','cm_export_authorization':'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','endpoint':'https://openrouter.ai/api/v1','providers':['parasail/fp8','near-ai/fp8'],'model':'qwen/qwen3.8-27b','dispatches':'40 physical max/case,80 total, native one confirmed429 switch only; UNKNOWN stops, no rerun'};put(D/'authorization.json',auth)
binding=read(P/'binding.json');active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');put(D/'before.json',{'active_release':active,'binding':binding,'active_mapping':read(P/'ACTIVE_MAPPING.json'),'ontology_settings':read(P/'ontology_settings.json')})
m=read(A/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Real native API source/ontology/vector to persisted answer; UNKNOWN stops subsequent physical requests',success_criteria=criteria['success'],failure_criteria=['Any required full-answer gate false; conditional second case not run after failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design']['arms'][0].update(changes='Completed ADR1240 selected MAIN125 scope port component evidence only',controls='Historical, no new baseline calls');m['design']['arms'][1].update(changes='Fresh real inference using selected immutable MAIN125, current Gold ON/DB and R18 mapping; no runtime product patch',controls='Exact cases and byte-pinned selected engine/profile/connector/transport');m['runs'][0].update(arm_ids=['live'],selection_rule=criteria['sample'],artifact_path=str((O/'result.json').relative_to(R)));m['dataset'].update(name='Known Gold369 and approved CM009 functional tests',version='20261030-main125',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'));m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}];reason='No retrieval ranking/filter policy change; conditional real existing vector path is observed and exact source/candidate/delivery accounting retained.';m['retrieval_accounting'].update(changed=False,corpus_total=21,not_applicable_reason=reason);m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
oldentry=R/read(old/'artifacts/design/candidate.json')['entry'];source=oldentry.read_text().replace('adr_1235','adr_1241').replace('ADR-1235-gold-ontology-transport-live','ADR-1241-main125-gold-live-revalidation').replace('MAIN120','MAIN125').replace('gold-ontology-transport-1235','main125-gold-live-1241')
source=source.replace('gold.HERE=P;gold.ROOT=R','gold.ROOT=R;gold.ACTIVE_POINTER=R/\'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json\'')
start=source.index('GOLD_CONTEXT=');end=source.index('GOLD_OPEN=',start)
source=source[:start]+"CASE_ID=sys.argv[1];assert len(sys.argv)==2 and CASE_ID in ('gold-369','cm-009')\nDESIGN=R/'04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation/artifacts/design'\nCASE=next(x for x in gold.read(DESIGN/'cases.json') if x['id']==CASE_ID)\nGOLD_CONTEXT=gold.open_store(documents=CASE['request']['json']['document_ids'])\n"+source[end:]
start=source.index('def gz(');end=source.index('def preserve_provider_failure',start)
source=source[:start]+'''sys.path.insert(0,str(R/'06_TOOLS/maintenance'))
from experiment_json import write_summary,write_raw_json,SUMMARY_LIMIT
checkpoint_put=put
def put(path,value):
 path=Path(path)
 if path.name in ('calls.json','generations.json'):
  assert len(json.dumps(value,ensure_ascii=False).encode())<SUMMARY_LIMIT
  checkpoint_put(path,value)
 else:write_summary(path,value)
def gz(path,value):
 receipt=write_raw_json(path,value)
 write_summary(Path(str(path)+'.ref.json'),receipt)
'''+source[end:]
start=source.index(' case_id=sys.argv[1]');end=source.index(' out.mkdir(',start)
source=source[:start]+" case_id=CASE_ID;case=CASE;out=O/'live'/case_id\n assert read(D/'preflight.json')['passed'] and read(O/'checks.json')['failed']==0\n if case_id=='cm-009':assert all(read(O/'ontology-e2e.json')['gates'].values())\n"+source[end:]
source=source.replace('calls=[];replayed_http=[];generations=[]','calls=[];generations=[]')
start=source.index('  if replay_saved:',source.index(' def post('));end=source.index('  guard();payload',start);source=source[:start]+source[end:]
# Do not hide product stop violations with a second test-only guard; observe any calls after UNKNOWN.
start=source.index('   if replay:',source.index(' def generate('));end=source.index('   result=old_generate',start);source=source[:start]+source[end:]
source=source.replace(';restore=install_vector_port()','')
source=source.replace(",'replay_entry_only':replay and not replay_saved,'replay_saved_responses':replay_saved",'')
source=source.replace('restore();GOLD_CONTEXT','GOLD_CONTEXT').replace('replayed_http_responses=len(replayed_http),','').replace("B['release']['files']","B['engine_files']")
source=source.replace("put(out/'sql-statements.json'","gz(out/'sql-statements.json.gz'").replace("put(out/'sql-errors.json'","gz(out/'sql-errors.json.gz'").replace("put(out/'resources.json'","gz(out/'resources.json.gz'")
# Preserve the normal local transport's absolute-deadline classification through ExperimentClient.
source=source.replace("except ExperimentTransportError as exc:raise TransportError(str(exc),retryable=exc.retryable,unknown=exc.unknown) from exc",'''except ExperimentTransportError as exc:
   from lawrag.core.request_deadline import AbsoluteDeadlineExceeded
   deadline_error=isinstance(exc.__cause__,AbsoluteDeadlineExceeded)
   raise TransportError(str(exc),code=504 if deadline_error else 502,retryable=exc.retryable,unknown=exc.unknown) from exc''')
ast.parse(source)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
base='08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';targets=[base+'/'+x for x in ('connect.py','engine_common.py','physical_mapping.py','binding.json','ontology_settings.json','ACTIVE_MAPPING.json','mapping_local_vctr_current.json')];S=ac.snapshot(A,'live',targets,experiment_id=m['experiment_id'],arm_id='live',run_ids=['run-001']);entry='06_TOOLS/EXPERIMENTS/adr_1241/live.py';SP=S/'snapshot';(SP/entry).parent.mkdir(parents=True);(SP/entry).write_text(source);ac.register_file(S,entry,upstream_state='absent');ac.freeze(S);assert not ac.validate(S);rev=read(S/'candidate.json')['revisions'][-1];RF=S/'revisions'/rev['revision_id']/'snapshot';put(D/'candidate.json',{'root':str(S.relative_to(R)),'snapshot':str(RF.relative_to(R)),'entry':str((RF/entry).relative_to(R)),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
for name in ('checks.py','audit.py','ontology_audit.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1235'/name).read_text().replace('ADR-1235-gold-ontology-transport-live','ADR-1241-main125-gold-live-revalidation').replace('adr_1235','adr_1241')
 if name=='audit.py':
  s=s.replace("parent=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';base=read(parent/'artifacts/design/baseline.json');data=R/base['release']['data_path']","data=R/binding['data_path']")
  s=s.replace("P/'resources.json'","P/'resources.json.gz'")
 if name=='ontology_audit.py':
  s=s.replace("def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\\n')","sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary,write_raw_json\nput=write_summary")
  s=s.replace("with gzip.open(O/'ontology-lineage.json.gz','wt') as f:json.dump({'views':views,'events':events,'assessments':assessments,'wire_paths':wire_paths,'result':result},f,ensure_ascii=False)","receipt=write_raw_json(O/'ontology-lineage.json.gz',{'views':views,'events':events,'assessments':assessments,'wire_paths':wire_paths,'result':result});put(O/'ontology-lineage-reference.json',receipt)")
 (R/'06_TOOLS/EXPERIMENTS/adr_1241'/name).write_text(s)
print('Prepared immutable',rev['revision_id'],'MAIN125',len(binding['engine_files']),'files; no models')
