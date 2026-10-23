"""Freeze current working product bytes and one photograph-derived natural query."""
from common import *
import sys
from datetime import datetime,timezone
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
assert not (ART/'design-freeze.json').exists()
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/p['manifest_path'])
assert sha(ROOT/p['manifest_path'])==p['release_manifest_sha256']
assert all(sha(ROOT/r['code_root']/n)==h for n,h in r['files'].items())
files={n:sha(ROOT/n) for n in r['files']}
# Same previously used public document grant, with no question-specific coordinate constraints.
request=read(ROOT/'04_EXPERIMENTS/ADR/ADR-0994-expansion-recheck-normal-budget/artifacts/known-request.json')
request['json']['question']='양도차익을 산정할 때 양도가액에서 공제되는 경비는 무엇인가?'
save(ART/'known-request.json',request)
save(ART/'query-provenance.json',{'source':'User-provided photograph, issue/question text displayed by application. Exact originally typed question is not visible.','transcription':request['json']['question'],'question_specific_document_or_coordinate_injection':False,'grant':'Same65 public document_ids previously used for local native runs; not restricted to Income Tax Act.','entry':'service.service -> RAG_ASK -> /v1/rag/ask; ordinary local RAG, no workflow task_context','scope':'Observe local recent working version; not a bit-identical GENOS workflow replay.'})
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='Article92 paragraph2 item1 search evidence can be widened by the offered read scope, cumulative delivered originals, or article-only incoming edges. Actual model selection and supplied scope must be distinguished.',primary_metric='Exact model proposals, executable target scopes, source spans and connection cards at each actual decision; locate first scope widening and whether it is system offer construction or model explicit selection.',success_criteria='One natural-question native run preserves exact provider payloads, selected tools, search previews, read offers, delivered spans and reference cards; provide evidence-backed attribution if92 pathway occurs, otherwise report non-reproduction and actual pathway. No forced92/97/163 input.',failure_criteria='Missing trace, code/data/ACL mismatch or provider failure prevents causal attribution. One case is not an effectiveness comparison or legal-answer certification. No adaptive query/retry to induce92.',criteria_frozen_before_run=True,sampling='One photo-derived natural question once; recent working product snapshot, selected MAIN101 data and65public-document grant. Baseline is byte comparison only with no model call.',execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'max_calls_total':40,'max_model_attempts':40,'wall_seconds':1800,'max_transport_retries':0,'concurrency':1,'rss_ceiling_gib':6,'minimum_available_gib':3,'failure_owner':'Existing native bounded decision owners, ExperimentClient sticky provider stop; no whole-run retry'},retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{'candidate':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Selected MAIN101 immutable byte reference only, no new baseline execution',controls='Same selected corpus and original public grant')
m['design']['arms'][1].update(changes='Current working files including previously implemented connection-first guidance/menu ordering/missing_target contract; no new product edits for this probe',controls='All current working419productfiles snapshotted; same data, profile, permissions; local standard external model, read-only observation wrappers')
save(ADR/'실험/manifest.json',m)
D=ac.snapshot(ADR,'candidate',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
ac.freeze(D);assert not ac.validate(D)
C=D/'snapshot';assert all(sha(C/n)==h for n,h in files.items())
cm=read(D/'candidate.json');rev=cm['revisions'][-1]
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0997/guard.py','runner_sha256':sha(Path(__file__).with_name('guard.py'))}])
m['dataset'].update(name='Photo-derived capital-gains expenses question',version='20261022-photo-transcription-v1',frozen_source=str((ART/'known-request.json').relative_to(ROOT)),sha256=sha(ART/'known-request.json'),legal_version_checked=True,reference_version_checked=False,version_scope='Selected corpus Income Tax Act and Enforcement Decree20260701 metadata; no legal answer gold')
m['llm_policy']['llm_calls']=[{'role':'native-service','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='No new retrieval edits or paired effectiveness claim; exact source-read/citation ledger and detailed scope trace recorded.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
save(ADR/'실험/manifest.json',m)
save(ART/'stage.json',{'base_release':r,'roots':{'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_vs_selected_changed':[n for n,h in files.items() if r['files'][n]!=h]})
save(ART/'design-freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'request_sha256':sha(ART/'known-request.json'),'files':{'candidate':files},'working_files':files,'runner_hashes':{str(x.relative_to(ROOT)):sha(x) for x in Path(__file__).parent.glob('*.py')},'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')})
print('Frozen',len(files),'files; working/selected differences',len([n for n,h in files.items() if r['files'][n]!=h]),'; one natural question; zero calls yet')
