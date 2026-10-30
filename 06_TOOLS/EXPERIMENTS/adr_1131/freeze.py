from common import *
import sys,ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=CAND/'snapshot';pipeline=read(S/'00_SYSTEM/PIPELINE.json');comp=read(ART/'composition.json')
for p in list(Path(__file__).parent.glob('*.py'))+list((S/'02_BACKEND/semantic_runtime/legal_agent').glob('ontology_scenar*.py')):ast.parse(p.read_text())
for ref in pipeline['engines'].values():
 ep=S/ref['manifest'];engine=read(ep)
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' not in engine['files']:continue
 for n in comp['added_product']:engine['files'][n]=sha(S/n)
 for n in engine['files']:
  if (S/n).is_file():engine['files'][n]=sha(S/n)
 put(ep,engine);ref['sha256']=sha(ep)
put(S/'00_SYSTEM/PIPELINE.json',pipeline);ac.freeze(CAND);assert not ac.validate(CAND),ac.validate(CAND)
cm=read(CAND/'candidate.json');rev=cm['revisions'][-1];code=CAND/'revisions'/rev['revision_id']/'snapshot';files={str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in rev['files']}
binding={'candidate_id':CAND.name,'experiment_id':'ADR-1131-experiment-v1','arm_id':'scenario','run_ids':['run-001'],'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1131/live.py','runner_sha256':sha(Path(__file__).with_name('live.py'))}
m=read(ADR/'실험/manifest.json');parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1124-ontology-explicit-exception-contract/실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding]);m['dataset']=parent['dataset'];m['dataset'].update(name='Known authorizedCM023 +3 authored public business-selection probes, same saved source28',frozen_source=str((ART/'cases.json').relative_to(ROOT)),sha256=sha(ART/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'scenario-selector','class':'product','model':'qwen/qwen3.8-27b','repetitions':4,'temperature':0,'notes':'4sequential cases, at most1same-schema repair each, no compiler/compose/evaluator calls'}]
m['retrieval_accounting']=parent['retrieval_accounting'];m['retrieval_accounting'].update(changed=True,not_applicable_reason=None,before_filter={'scenario':0},after_filter={'scenario':0},presented_total={'scenario':0},presented_mean={'scenario':0},presented_p50={'scenario':0},presented_p95={'scenario':0},golden_recall={'scenario':0},selectivity={'scenario':0})
m['retrieval_accounting']['stage_ledger'].update(mode='measured',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',summary_run_id='run-001',not_applicable_reason=None)
stages=[{'stage_id':'saved_originals','kind':'source','parent_stage_ids':[]},{'stage_id':'selector_presented','kind':'present','parent_stage_ids':['saved_originals']},{'stage_id':'selected_cited','kind':'present','parent_stage_ids':['selector_presented']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stages,'scenario':stages};put(ADR/'실험/manifest.json',m)
source_view='04_EXPERIMENTS/ADR/ADR-1124-ontology-explicit-exception-contract/artifacts/run-001/semantic/cm-023/canonical/004.json.gz'
inputs=[ART/n for n in ('criteria.json','baseline.json','composition.json','cases.json','build-input.json','recipe.json','rubric.json','parent.json')]+[ROOT/source_view,ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json']
f={'code_root':str(code.relative_to(ROOT)),'files':files,'binding':binding,'pointer_sha256':read(ART/'parent.json')['pointer_sha256'],'source_view':source_view,'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'manifest_sha256_at_freeze':sha(ADR/'실험/manifest.json'),'new_model_calls':0};put(ART/'freeze.json',f);print('FROZEN',len(files))
