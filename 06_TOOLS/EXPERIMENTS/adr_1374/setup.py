from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1373-charter-knowledge-accumulation-reuse/artifacts'
DES.mkdir(exist_ok=False)
f=read(P/'design/candidate.json')
files=list(f['selected_files'])
before={n:sha(ROOT/n) for n in files}
put(DES/'working-before.json',before)
put(DES/'candidate-parent.json',f)
for n in ('baseline','source-scope','originals','originals-origin','records','provider-policy'):
    put(DES/(n+'.json'),read(P/'design'/(n+'.json')))
shutil.copytree(P/'transport',ART/'transport')
products=['02_BACKEND/semantic_runtime/ontology_work/'+n for n in ('recorded_fields.py','domain_workflow.py')]
assert all(before[n]==f['selected_files'][n] for n in products)
criteria={'hypothesis':'Offer exact verified glossary term locations, preserving general free-span fallback. Compare an actual misleading opinion with originals. On the prior verified RAG consumer, measure adoption of the isolated revision2 when its path is explicitly requested.',
 'success':['The original five rejected responses remain rejected. Only offered unique or repeated exact locations restore; preserve valid unrestricted quotations.',
 'The real contradictory judgment reaches source comparison and a new conflict draft without changing the rule or active revision2.',
 'Record the verified usage on a final claim for the exact published revision2; a quotation or ontology delivery alone does not qualify.'],
 'failure':['Report partial answers, skips or failures explicitly. No real approval or promotion; no automatic retries after uncertain transmission.'],
 'limits':{'authoring_physical':11,'rag_physical':40,'maximum_per_authoring_job':5,'provider':'Qwen3.8 FP8, Parasail policy, reasoning none'}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Reopenable, source-grounded charter bundle accepted by compiler',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed1371/repaired exact stored charter DRAFT and verified source associations',controls='Reference only')
m['design']['arms'][1].update(changes='Version-bound follow-up observation comparison using canonical validation and immutable prior graph',controls='Same public originals, archived judgment, all selected statements, model and provider policy')
m['dataset'].update(name='Actual archived charter judgment and legal source snapshot',version='1354-frozen',frozen_source=str((DES/'records.json').relative_to(ROOT)),sha256=sha(DES/'records.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Fresh build once. Validation may request up to four additional proposals per stage. Stop on unknown.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=m['llm_policy']['llm_calls'][:1]
m['runs'][0]['selection_rule']='Corroborate → review & activate isolated revision → same-question ON/OFF → conflicting opinion. Unknown stops all later external calls. On known non-corroboration use reviewed original or mark target explicitly.'
cases=[{'id':'charter-explicit','arms':['ontology-on'],'document_ids':read(DES/'source-scope.json')['public'],'article':434,'steps':[{'number':1,'mode':'외규','question':'상법 제434조의 정관변경 특별결의 정족수를 알려주세요. 검토된 온톨로지의 ‘정관 변경 결의의 비율 기준’ 경로를 사용해 설명해 주세요.'}]}]
put(DES/'live-cases.json',cases)
put(DES/'followups.json',read(P/'design/followups.json'))
put(DES/'authorization.json',{'scope':'Explicit test-only use of approved staged copy and public archived opinion; no production changes.','public_ids':cases[0]['document_ids']})
consumer=read(next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1369*/artifacts/design/candidate-repaired.json')));put(DES/'consumer.json',consumer)
m['dataset'].update(name='Same actual conflicting judgment and one explicit path question',version='1374-r1',frozen_source=str((DES/'followups.json').relative_to(ROOT)),sha256=sha(DES/'followups.json'))
m['runs'][0]['selection_rule']='First explicit ON with immutable1369 answer consumer, then comparison with modified authoring worker on copy of 1373 revision2. Stop all later sends on unknown.'
m['design']['arms'][0].update(changes='Completed1373 five known normalization failures and natural ON with no accepted usage')
m['design']['arms'][1].update(changes='Bounded exact raw glossary mentions; distinct explicit request on recorded completed1369 consumer',controls='Same public originals, actual conflicting opinion and approved revision2. This is not a speed comparison to 1373.')
m['design']['retrieval_stage_plan']=read(P.parent/'실험/manifest.json')['design']['retrieval_stage_plan']
for x in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):x['not_applicable_reason']='Fixed original authoring input; no answer/retrieval search experiment.'
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',files,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in files:
    if sha(can/'snapshot'/n)!=f['selected_files'][n]:
        shutil.copyfile(ROOT/f['code_root']/n,can/'snapshot'/n)
assert all(sha(can/'snapshot'/n)==f['selected_files'][n] for n in files)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':products})
print(can/'snapshot')
