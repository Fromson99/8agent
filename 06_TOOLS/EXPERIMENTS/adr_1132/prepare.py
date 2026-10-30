from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1132-scenario-source-binding';ART=ADR/'artifacts';D=Path(__file__).parent;OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1131-scenario-choice-contract-repair'
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(OLD/'artifacts/freeze.json');source=ROOT/f['code_root'];oldm=read(OLD/'실험/manifest.json')
for name in ['criteria.json','baseline.json','composition.json','build-input.json','recipe.json','cases.json','rubric.json','parent.json']:shutil.copyfile(OLD/'artifacts'/name,ART/name)
criteria=read(ART/'criteria.json');criteria['source_binding_followup']='1131 134pass4fail preserved; canonical source document_id/evidence_refs retained until ordinary wire projection.';put(ART/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update({k:oldm['design'][k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria','criteria_frozen_before_run')})
for a in m['design']['arms']:a.update(changes='historical parent, not executed' if a['id']=='baseline' else 'Retain source identity and offered span refs before ordinary wire projection',controls='Same recipe/path/selection contract as1131')
m['runs'][0].update(arms=['scenario'],selection_rule=criteria['run'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)));put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'scenario-r1',present,experiment_id=m['experiment_id'],arm_id='scenario',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(source/n)==h,n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for name in ['common.py','build.py','live.py','freeze.py','check.py','test_direct.py','test_projection.py','test_semantics.py','test_scenarios.py','test_scenario_native.py']:
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1131'/name).read_text().replace('ADR-1131-scenario-choice-contract-repair','ADR-1132-scenario-source-binding').replace('adr_1131','adr_1132').replace('ADR-1131-experiment-v1','ADR-1132-experiment-v1').replace('ADR1131','ADR1132');(D/name).write_text(s)
p=S/'02_BACKEND/semantic_runtime/legal_agent/ontology_scenarios.py';s=p.read_text();old="'sources':[{k:v for k,v in row.items() if k in ('source_id','document_name','heading')} for row in sources]";new="'sources':[{**{k:deepcopy(v) for k,v in row.items() if k not in ('text','adopted_spans')}, 'evidence_refs':[o['id'] for o in (options or []) if o['source_id']==row['source_id']]} for row in sources]";assert old in s;s=s.replace(old,new);p.write_text(s)
p=D/'test_scenarios.py';p.write_text(p.read_text()+'''

def test_canonical_source_identity_and_offered_refs_survive_until_wire():
    p,c=compiled();source={'source_id':'SRC1','document_id':'d','document_name':'합성규정','text':'원문','adopted_spans':[]}
    view=sc.selection_input(c,'질문',issues(),options=options(),sources=[source])
    assert view['sources'][0]['document_id']=='d'
    assert view['sources'][0]['evidence_refs']==['S1']
    assert 'text' not in view['sources'][0] and view['evidence_options']==options()
''')
print(S)
