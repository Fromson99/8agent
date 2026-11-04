from pathlib import Path
import shutil,sys,json
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent;OLDT=ROOT/'06_TOOLS/EXPERIMENTS/adr_1311'
for n in ['common.py','authorization.py','pinned_imports.py','resource_guard.py','sql_observer.py','check.py']:
 s=(OLDT/n).read_text().replace('ADR-1311-structure-latency-repair','ADR-1312-finish-handoff-live')
 if n=='check.py':s=s.replace("default='optimized'","default='after'")
 (T/n).write_text(s)
sys.path.insert(0,str(T));from common import *
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1309-main136-sqlite-latency';PERF=ROOT/'04_EXPERIMENTS/ADR/ADR-1311-structure-latency-repair';DES.mkdir(exist_ok=False)
for n in ['baseline.json','baseline-after.json','authorization.json','nearai-only.json','sqlite-source.json','scoring-only-originals.json']:
 shutil.copyfile(OLD/'artifacts/design'/n,DES/n)
shutil.copyfile(DES/'baseline-after.json',DES/'baseline-before.json')
shutil.copytree(OLD/'artifacts/transport',ART/'transport')
cases=read(OLD/'artifacts/design/cases.json')
for c in cases:c['arms']=['before','after'] if c['id']=='ontology-369' else ['after']
put(DES/'cases.json',cases)
criteria={'hypothesis':'After source-goal control has resolved mandatory sources, a validated FINISH with all original issues ANSWERABLE and no live read-needs/conflicts/unseen evidence can enter existing final ASSESS without a new supervisor redirect.', 'primary_metric':'Valid final answers, calls after FINISH, total/model/outside-model request seconds; identical original369 offline gate proof and one live369 before/after pair plus fixed365.', 'success':['No new regression; pending/UNKNOWN/hash/ACL/source-goal control and final claim/source validation preserved.','Eligible FINISH is authorized and persisted with zero additional supervisor calls; open need/conflict/mandatory source still blocks bypass.','After answers365/369 contain source-grounded core requirements, no original/ACL/wire mismatch, duplicate requests add0 models.'], 'failure':['UNKNOWN physical result stops global live dispatch; never retry same cell. Known429 is failed cell, excluded from speed ratio.','Source/code drift, resource violation or new contract regression stops dependent live runs.'], 'order':['ontology-369/before','ontology-369/after','ontology-365/after'],'repeats':1,'global_physical_cap':60,'cell_cap':40,'limits':read(PERF/'artifacts/design/criteria.json')['limits'],'fixed':['SQLite corpus, Qwen3.8-27b, NearAI FP8 only/fallback0/reasoningnone, ontologyOFF, finaltablesOFF experimentonly, performance fixes botharms, source validation/budgets'], 'changes':['Only investigation_supervisor eligible FINISH gate; no prompt or schema edits.'],'causality':'Single model run pair is stochastic, no general latency/quality guarantee;1311 replay isolates exact-equivalent CPU repair.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');parent=read(PERF/'실험/manifest.json')
for k in ['design','llm_policy','dataset']:m[k]=parent[k]
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1311-experiment-v1/optimized'],'changes':'Completed equivalent performance repair','controls':'Same SQLite corpus'},*({'id':a,'role':'candidate','derived_from':['baseline'],'changes':'Performance repairs only' if a=='before' else 'Validated FINISH handoff','controls':'Same model/provider/schema/prompt and all performance repairs'} for a in ('before','after'))]
stages=parent['design']['retrieval_stage_plan']['stages_by_arm']['optimized'];m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','before','after')};m['design']['code_isolation']['candidates']=[];m['llm_calls']=[]
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),version='20261104-finish-handoff-v1')
m['retrieval_accounting']=read(OLD/'실험/manifest.json')['retrieval_accounting'];m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((ART/'retrieval-stage-ledger.json').relative_to(ROOT)),sha256='PENDING')
m['runs'][0].update(arm_ids=['before','after'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='Fixed369 before then after and365 after eachonce; UNKNOWN globalstop, no cellretry.');m['lineage']['hypothesis_delta']=criteria['hypothesis'];put(ADR/'실험/manifest.json',m)
orig=read(OLD/'artifacts/design/candidate-after.json');code=ROOT/orig['code_root'];verified=read(PERF/'artifacts/design/candidate-optimized.json');V=ROOT/verified['code_root'];products=read(PERF/'artifacts/working-integration.json')['products']
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
for arm in ['before','after']:
 can=ac.snapshot(ADR,arm,[str((code/n).relative_to(ROOT)) for n in orig['selected_files']],experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
 S=can/'snapshot'/orig['code_root']
 for n in products:shutil.copyfile(V/n,S/n)
 put(DES/(arm+'-path.json'),{'candidate':str(can.relative_to(ROOT)),'code_relative':orig['code_root'],'files':orig['selected_files']})
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1309/live.py').read_text().replace('adr1309','adr1312').replace('ADR1309','ADR1312').replace('total>=160','total>=60').replace('experiment160','experiment60')
s=s.replace('One candidate module disables final read judgment review; selected MAIN135 unchanged.','Both candidates use1311 performance repairs; after also hands off eligible FINISH; final tables remain off only in tests.')
(T/'live.py').write_text(s)
s=(OLDT/'freeze.py').read_text().replace("['before','optimized']","['before','after']").replace("if arm=='optimized':","if arm in ('before','after'):").replace("T/'replay.py'","T/'live.py'")
a=s.index("source=ROOT/read(DES/'source-cell.json')");b=s.index("put(DES/'freeze.json'",a);s=s[:a]+s[b:];s=s.replace("'new_model_calls':0","'physical_cap':60").replace('before/optimized517','before/after517')
(T/'freeze.py').write_text(s)
print('1312 design and isolated snapshots ready')
