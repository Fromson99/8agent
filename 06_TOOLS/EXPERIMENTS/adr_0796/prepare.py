from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);base=read(R/pointer['manifest_path'])
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(p),'manifest':base})
criteria={'scope':'Finite technical selection/admission/consumer audit; no legal answer quality assertion','controls':['MAIN72 source/navigation/fulltext bytes','all unrelated MAIN72 serving functions','all original RAW and sealed handoffs'],'success':['all frozen user rules, whitespace split, same-date attachments and singleton cases','one common rule engine for RAW and indexed metadata','retained internal documents carry is_latest plus honest reason; excluded IDs inaccessible in search/list/folder/read/definition/reference','strict generation/source/config fingerprint verification; plan mutation, stale run, missing sidecar, rollback and cache invalidation','candidate and actual service use identical selected bytes; all unrelated baseline code preserved'],'limits':{'model_calls':0,'automatic_retries':0,'meaning_inference':False},'failures':{'owner':'search_selection plan/apply; RAW inventory before structure','invalid_configuration':'fail before write; explicit corrected config and fresh plan','missing_target':'report REVIEW and preserve; do not silently choose another date','stale_or_hash_mismatch':'stop and preserve previous selection','apply_verification_failure':'restore previous sidecar with failure receipt','resume':'idempotent identical plan only'},'evaluation':'all listed finite technical contracts plus current corpus metadata; supplied names are known cases, not out-of-sample semantic evaluation'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']='Common filename selection and explicit latest marks at pipeline and serving boundaries'
m['design'].update(hypothesis='Approved retained document set is identical at pipeline admission and every RAG consumer',primary_metric='finite technical contract pass and source preservation',success_criteria=criteria['success'],failure_criteria='Any unauthorized exclusion, stale selection acceptance, original mutation or consumer bypass',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason='Product selection candidate isolated from MAIN72; no model calls')
for a in m['design']['arms']:a.update(changes='MAIN72 unchanged' if a['id']=='baseline' else 'Latest marks and R3 approved exceptions with whitespace-specific indexbook identity',controls=criteria['controls'])
m['runs'][0].update(selection_rule='Frozen finite technical contracts and complete selected generation metadata inventory',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='latest-document-technical-contracts',version='20261015-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
for arm in ('baseline','selected'):m['design']['retrieval_stage_plan']['stages_by_arm'][arm]=[{'stage_id':s,'kind':k,'parent_stage_ids':[] if i==0 else [['source','filter','present'][i-1]]} for i,(s,k) in enumerate([('source','source'),('filter','filter'),('present','present')])]
put(A/'실험/manifest.json',m)
extras=['02_BACKEND/semantic_runtime/search_selection.py','02_BACKEND/lawrag/pipeline/search_selection.py','02_BACKEND/lawrag/pipeline/document_representations.py','02_BACKEND/lawrag/pipeline/genos_build.py','02_BACKEND/lawrag/pipeline/genos_corpus.py','02_BACKEND/lawrag/pipeline/team_raw.py','02_BACKEND/lawrag/pipeline/document_release.py','06_TOOLS/pipeline.py','06_TOOLS/COMMANDS/composed_build.py','06_TOOLS/COMMANDS/genos_data_stages.py','00_SYSTEM/SCHEMAS/pipeline-v1.schema.json','05_TESTS/CONTRACTS/test_search_selection.py']
sources=sorted(set(base['files'])|set(extras))
cmd=['.venv/bin/python','06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','selected','--experiment-id',m['experiment_id'],'--arm-id','selected','--run-id','run-001']
for s in sources:cmd+=['--source',s]
subprocess.run(cmd,check=True)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0796/selected/snapshot'
# Explicit preservation of latest selected code; search visibility is the only adopted preexisting delta.
search={'02_BACKEND/semantic_runtime/'+x for x in ('storage.py','term_index.py','app.py','team_scope.py','legal_agent/shortcut_ingress.py','workflow_bridge.py')}
for s in base['files']:
 if s not in search:shutil.copyfile(R/base['code_root']/s,C/s)
put(D/'working-before.json',{s:sha(R/s) for s in sources})
put(D/'data-binding.json',{'path':base['data_path'],'manifest_sha256':base['data_manifest_sha256']})
print('Prepared isolated baseline and candidate',len(sources))
