from common import *
import ast,shutil,sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
base=read(ART/'baseline.json');release=base['release'];B=ROOT/release['code_root'];C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1105/ontology-r1';S=C/'snapshot'
old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1079-ontology-departure-single-cell/artifacts/design-freeze.json')
cases=read(ROOT/old['product_cases_path'])['cases'];put(ART/'cases.json',[{'id':c['case_id'],'question':c['question']} for c in cases])
for key in ('snapshot','evaluator_cases','evaluation_contract','source_integrity'):
 p=ROOT/old[key+'_path'];assert sha(p)==old[key+('_file_sha256' if key=='snapshot' else '_sha256')]
assert release['data_path']==old['data_path'] and release['data_manifest_sha256']==old['data_manifest_sha256']
# Pin modified modules and explicitly add the new ontology consumers to the same engine.
p=S/'00_SYSTEM/PIPELINE.json';pipeline=read(p)
added=read(ART/'composition.json')['added_product']
for ref in pipeline['engines'].values():
 ep=S/ref['manifest'];engine=read(ep)
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' not in engine['files']:continue
 for n in added:engine['files'][n]=sha(S/n)
 for n in engine['files']:
  if (S/n).is_file():engine['files'][n]=sha(S/n)
 put(ep,engine);ref['sha256']=sha(ep)
put(p,pipeline)
for p in S.rglob('*.py'):ast.parse(p.read_text())

if not read(C/'candidate.json').get('revisions'):ac.freeze(C)
assert not ac.validate(C),ac.validate(C)
def bind(c,arm):
 cm=read(c/'candidate.json');rev=cm['revisions'][-1];code=c/'revisions'/rev['revision_id']/'snapshot'
 return {'code_root':str(code.relative_to(ROOT)),'files':{str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in rev['files']},
 'binding':{'candidate_id':c.name,'experiment_id':'ADR-1105-experiment-v1','arm_id':arm,'run_ids':['run-001'],'manifest_path':str((c/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1105/live.py','runner_sha256':sha(Path(__file__).with_name('live.py'))}}
ontology=bind(C,'ontology')
support=read(ART/'support-inventory.json')['test_only_files'];names=sorted(set(release['files'])|set(support))
BS=ART/'baseline-code';BS.mkdir(exist_ok=True)
for n in names:
 src=B/n if n in release['files'] else S/n;dest=BS/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
baseline={'code_root':str(BS.relative_to(ROOT)),'files':{n:sha(BS/n) for n in names},'binding':{'kind':'selected-release-exact-readonly-copy','release_id':release['release_id'],'release_manifest_sha256':base['release_manifest_sha256'],'test_support_only':True}}
assert all(baseline['files'][n]==h for n,h in release['files'].items())
inputs=[ART/n for n in ('criteria.json','baseline.json','composition.json','cases.json')]
inputs += [ROOT/old[k+'_path'] for k in ('snapshot','source_integrity','evaluator_cases','evaluation_contract')]
inputs += [ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
m=read(ADR/'실험/manifest.json');criteria=read(ART/'criteria.json')
m['integration'].update(result_arm='ontology',rationale=criteria['hypothesis'],common_invariants=criteria['invariants'],no_conflict_reason=None,conflicts=[{'area':'MAIN106 lacks ontology modules and has different output schema','resolution':'Use MAIN106 all serving files and schema; transplant acquisition/projector only, adapt enable guard to completion_contract; no old menus or execution_review schema','risk':'Direct ASSESS still subject to current MAIN final judgment/schema behavior'}])
for p in m['integration']['parent_contributions']:
 p.update(adopted='Complete selected MAIN106 serving code/profile/data/SQL' if '1092' in p['parent_ref'] else 'Only ontology source acquisition, source-bound ASSESS projection and immediate handoff',excluded='None of selected MAIN106' if '1092' in p['parent_ref'] else 'Old candidate navigation, task-local choice contracts, schema/partial judgment repair, input/output aliases, buffering and old profile')
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary'],success_criteria='All integrity contracts pass, ontology/originals reach first ASSESS with no intervening navigation choice; report final answer and gaps separately',failure_criteria='Any integrity failure, missing binding, unwanted authority expansion or absent ontology wire rejects contract; semantic outcome is observed, not certified',criteria_frozen_before_run=True)
for a in m['design']['arms']:
 a.update(derived_from=['ADR-1092-experiment-v1/serving'] if a['id']=='baseline' else ['ADR-1092-experiment-v1/serving','ADR-1098-experiment-v1/direct'],changes='Exact selected MAIN106' if a['id']=='baseline' else 'Only ontology acquisition/direct ASSESS integration',controls='Same MAIN106 corpus, question, schema, model, budget; same runner; sequential fresh process')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[ontology['binding']])
stages=[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'assess_presented','kind':'present','parent_stage_ids':['original_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['assess_presented']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','ontology')}
m['dataset'].update(name='Known authorized CM023; evaluator references separated',version=old['source_generation_id'],frozen_source=str((ART/'cases.json').relative_to(ROOT)),sha256=sha(ART/'cases.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['runs'][0].update(selection_rule='Exactly CM023, baseline then A1 once each after frozen synthetic contracts. No cell retry; no holdout/quality certification.',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=True,corpus_total=old['corpus_total_article_roots'],not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
f={'arms':{'baseline':baseline,'ontology':ontology},'pointer_sha256':base['pointer_sha256'],'snapshot_path':old['snapshot_path'],'snapshot_digest':old['snapshot_digest'],
 'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'manifest_sha256_at_freeze':sha(ADR/'실험/manifest.json'),'new_model_calls':0}
put(ART/'freeze.json',f)
print('FROZEN',len(baseline['files']),len(ontology['files']))
