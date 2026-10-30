from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=CAND/'snapshot';pipeline=read(S/'00_SYSTEM/PIPELINE.json');comp=read(ART/'composition.json')
for ref in pipeline['engines'].values():
 ep=S/ref['manifest'];engine=read(ep)
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' not in engine['files']:continue
 for n in comp['added_product']:engine['files'][n]=sha(S/n)
 for n in engine['files']:
  if (S/n).is_file():engine['files'][n]=sha(S/n)
 put(ep,engine);ref['sha256']=sha(ep)
put(S/'00_SYSTEM/PIPELINE.json',pipeline);ac.freeze(CAND);assert not ac.validate(CAND),ac.validate(CAND)
cm=read(CAND/'candidate.json');rev=cm['revisions'][-1];code=CAND/'revisions'/rev['revision_id']/'snapshot';files={str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in rev['files']}
binding={'candidate_id':CAND.name,'experiment_id':'ADR-1124-experiment-v1','arm_id':'semantic','run_ids':['run-001'],'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1124/live.py','runner_sha256':sha(Path(__file__).with_name('live.py'))}
old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1121-ontology-semantic-compilation/artifacts/freeze.json');m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding]);parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1121-ontology-semantic-compilation/실험/manifest.json')
m['dataset']=parent['dataset'];m['dataset'].update(frozen_source=str((ART/'cases.json').relative_to(ROOT)),sha256=sha(ART/'cases.json'));m['llm_policy']['llm_calls']=parent['llm_policy']['llm_calls'];m['retrieval_accounting']=parent['retrieval_accounting']
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',summary_run_id='run-001',not_applicable_reason=None)
stages=[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'assess_presented','kind':'present','parent_stage_ids':['original_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['assess_presented']}];m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','semantic')};put(ADR/'실험/manifest.json',m)
inputs=[ART/n for n in ('criteria.json','baseline.json','composition.json','cases.json','build-input.json','prefix.json','previous-proposal.json')]+[ROOT/old['snapshot_path'],ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json']
f={'code_root':str(code.relative_to(ROOT)),'files':files,'binding':binding,'pointer_sha256':read(ART/'baseline.json')['pointer_sha256'],'snapshot_path':old['snapshot_path'],'snapshot_digest':old['snapshot_digest'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'manifest_sha256_at_freeze':sha(ADR/'실험/manifest.json'),'new_model_calls':0};put(ART/'freeze.json',f);print('FROZEN',len(files))
