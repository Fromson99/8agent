from common import *
import sys,ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=CAND/'snapshot';pipeline=read(S/'00_SYSTEM/PIPELINE.json')
for p in list(Path(__file__).parent.glob('*.py'))+[S/'02_BACKEND/semantic_runtime/legal_agent'/n for n in ('completion_execution.py','ontology_scenarios.py','ontology_scenario_runtime.py')]:ast.parse(p.read_text())
for ref in pipeline['engines'].values():
 ep=S/ref['manifest'];engine=read(ep)
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' not in engine['files']:continue
 for n in engine['files']:
  if (S/n).is_file():engine['files'][n]=sha(S/n)
 put(ep,engine);ref['sha256']=sha(ep)
put(S/'00_SYSTEM/PIPELINE.json',pipeline);ac.freeze(CAND);assert not ac.validate(CAND),ac.validate(CAND)
cm=read(CAND/'candidate.json');rev=cm['revisions'][-1];code=CAND/'revisions'/rev['revision_id']/'snapshot';files={str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in rev['files']}
binding={'candidate_id':CAND.name,'experiment_id':'ADR-1134-experiment-v1','arm_id':'scenario','run_ids':['run-001'],'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1134/check.py','runner_sha256':sha(Path(__file__).with_name('check.py'))}
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding]);m['dataset'].update(name='Synthetic source contracts and native HTTP with deterministic transport; no live legal question evaluation',frozen_source=str((ART/'criteria.json').relative_to(ROOT)),sha256=sha(ART/'criteria.json'))
m['llm_policy']['llm_calls']=[];m['design']['retrieval_stage_plan']['stages_by_arm']={}
ra=m['retrieval_accounting'];ra.update(changed=False,not_applicable_reason='Synthetic contract/API fixtures only; no measured real corpus retrieval or quality experiment.')
for key in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):ra[key]=None
ra['stage_ledger'].update(mode='not_applicable',artifact_path=None,sha256=None,summary_run_id=None,not_applicable_reason=ra['not_applicable_reason']);put(ADR/'실험/manifest.json',m)
f={'code_root':str(code.relative_to(ROOT)),'files':files,'binding':binding,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'inputs':{str(p.relative_to(ROOT)):sha(p) for p in [ART/'criteria.json',ART/'parent-binding.json']},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'manifest_sha256_at_freeze':sha(ADR/'실험/manifest.json'),'new_model_calls':0};put(ART/'freeze.json',f);print('FROZEN',len(files))
