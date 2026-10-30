from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1131-scenario-choice-contract-repair';ART=ADR/'artifacts';D=Path(__file__).parent;OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1130-ontology-precompiled-scenario-selection'
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(OLD/'artifacts/freeze.json');source=ROOT/f['code_root'];oldm=read(OLD/'실험/manifest.json')
for name in ['criteria.json','baseline.json','composition.json','build-input.json','recipe.json','cases.json','rubric.json','parent.json']:shutil.copyfile(OLD/'artifacts'/name,ART/name)
criteria=read(ART/'criteria.json');criteria['contract_followup']='1130 131pass7fail preserved; fix canonical NO_MATCH transition and two synthetic fixture errors, source-authored recipe unchanged.';put(ART/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update({k:oldm['design'][k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria','criteria_frozen_before_run')})
for a in m['design']['arms']:a.update(changes='historical parent, not executed' if a['id']=='baseline' else 'NO_MATCH canonical transition; same5 precompiled scenarios and closed selection',controls='Same recipe/originals as1130; new output fixture correctness only')
m['runs'][0].update(arms=['scenario'],selection_rule=criteria['run'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)));put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'scenario-r1',present,experiment_id=m['experiment_id'],arm_id='scenario',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(source/n)==h,n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for name in ['common.py','build.py','live.py','freeze.py','check.py','test_direct.py','test_projection.py','test_semantics.py','test_scenarios.py','test_scenario_native.py']:
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1130'/name).read_text().replace('ADR-1130-ontology-precompiled-scenario-selection','ADR-1131-scenario-choice-contract-repair').replace('adr_1130','adr_1131').replace('ADR-1130-experiment-v1','ADR-1131-experiment-v1').replace('ADR1130','ADR1131')
 (D/name).write_text(s)
p=S/'02_BACKEND/semantic_runtime/legal_agent/ontology_scenarios.py';s=p.read_text().replace("'disposition':'ANSWER' if not gaps else 'LIMITED_ANSWER'","'disposition':'NEEDS_INVESTIGATION' if not claims else 'ANSWER' if not gaps else 'LIMITED_ANSWER'");p.write_text(s)
p=p.with_name('ontology_scenario_runtime.py');s=p.read_text().replace("result['stop_reason']='NO_SCENARIO_MATCH'","result['stop_reason']='NO_SCENARIO_MATCH'\n        result['disposition']='LIMITED_ANSWER'");p.write_text(s)
p=D/'test_scenarios.py';s=p.read_text().replace("'path_ids':paths","'path_ids':deepcopy(paths)").replace("'missing_facts':facts","'missing_facts':deepcopy(facts)");p.write_text(s)
p=D/'test_scenario_native.py';p.write_text(p.read_text().replace("answer_presentation='narrative'","answer_presentation='grounded-narrative-v1'"))
p=D/'freeze.py';s=p.read_text().replace("before_filter=None,after_filter=None,presented_total=None,presented_mean=None,presented_p50=None,presented_p95=None,golden_recall=None,selectivity=None","before_filter={'scenario':0},after_filter={'scenario':0},presented_total={'scenario':0},presented_mean={'scenario':0},presented_p50={'scenario':0},presented_p95={'scenario':0},golden_recall={'scenario':0},selectivity={'scenario':0}").replace("{'scenario':stages}","{'baseline':stages,'scenario':stages}")
p.write_text(s)
p=D/'check.py';s=p.read_text().replace("'-q','-s','--tb=short'","'-q','--tb=short'");p.write_text(s)
print(S)
