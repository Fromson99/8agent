from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1133-scenario-selection-receipt';ART=ADR/'artifacts';D=Path(__file__).parent;OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1132-scenario-source-binding'
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(OLD/'artifacts/freeze.json');source=ROOT/f['code_root'];oldm=read(OLD/'실험/manifest.json')
for name in ['criteria.json','baseline.json','composition.json','build-input.json','recipe.json','cases.json','rubric.json','parent.json']:shutil.copyfile(OLD/'artifacts'/name,ART/name)
criteria=read(ART/'criteria.json');criteria['receipt_followup']='1132 135pass4fail preserved; existing assessment_basis stores scenario choice, no new top-level answer schema.';put(ART/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update({k:oldm['design'][k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria','criteria_frozen_before_run')})
for a in m['design']['arms']:a.update(changes='historical parent, not executed' if a['id']=='baseline' else 'Keep scenario choice in existing assessment_basis schema',controls='Same recipe/path/selection semantics as1132')
m['runs'][0].update(arms=['scenario'],selection_rule=criteria['run'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)));put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'scenario-r1',present,experiment_id=m['experiment_id'],arm_id='scenario',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(source/n)==h,n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for name in ['common.py','build.py','live.py','freeze.py','check.py','test_direct.py','test_projection.py','test_semantics.py','test_scenarios.py','test_scenario_native.py']:
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1132'/name).read_text().replace('ADR-1132-scenario-source-binding','ADR-1133-scenario-selection-receipt').replace('adr_1132','adr_1133').replace('ADR-1132-experiment-v1','ADR-1133-experiment-v1').replace('ADR1132','ADR1133');(D/name).write_text(s)
P=S/'02_BACKEND/semantic_runtime/legal_agent'
p=P/'ontology_scenarios.py';s=p.read_text().replace("out.update(scenario_selection={","out.update(assessment_basis={'scenario_choice':{").replace("'case_applicability_certified':False},semantic_quality_certified=False)","'case_applicability_certified':False}},semantic_quality_certified=False)").replace("receipt=assessment['scenario_selection']","receipt=assessment['assessment_basis']['scenario_choice']");p.write_text(s)
p=P/'ontology_scenario_runtime.py';s=p.read_text().replace("result.update(answer_coverage=ic.coverage(result),assessment_basis=basis)\n    result['assessment_basis']['scenario_choice']=deepcopy(result['scenario_selection'])","receipt=deepcopy(result['assessment_basis']['scenario_choice'])\n    result.update(answer_coverage=ic.coverage(result),assessment_basis={**basis,'scenario_choice':receipt})").replace("result['scenario_selection']['selected_paths']","receipt['selected_paths']");p.write_text(s)
p=P/'completion_execution.py';s=p.read_text().replace("assessment.get('scenario_selection')","assessment.get('assessment_basis',{}).get('scenario_choice')");p.write_text(s)
p=D/'live.py';s=p.read_text().replace("assessment['scenario_selection']","assessment['assessment_basis']['scenario_choice']");p.write_text(s)
p=D/'test_scenarios.py';p.write_text(p.read_text()+'''

def test_selection_receipt_uses_existing_internal_contract_field():
    p,c=compiled();value=sc.materialize_choice(choice(),c,issues(),options())
    assert 'scenario_selection' not in value
    assert value['assessment_basis']['scenario_choice']['selected_paths'][0]['id']=='PATH1'
''')
print(S)
