from pathlib import Path
import sys,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1267-legacy-selection-contract-repair';D=A/'artifacts';D.mkdir(exist_ok=True)
m=json.loads((A/'실험/manifest.json').read_text());hyp='Executable source-ref choices must compile into the selected canonical v6/v7/v8 provenance schema while preserving actual source identity.'
criteria={'hypothesis':hyp,'success':['DIRECT and DEPENDENCY selections pass v6/v7/v8 canonical schema','Legacy DEPENDENCY uses exact selected currently delivered original text, not generated paraphrase','Duplicate target/issue, unknown original, malformed selection continue to reject and repair','Native v6/v7/v8 API recovery and previous current-loop fault suite pass'],'failure':['Source/ACL validation relaxed','Current v8 output changed','Any new regression'],'live_model_calls':0,'scope':'One generic projection fix and explicit test fixture maintenance; no MAIN/deploy changes.'}
(D/'criteria.json').write_text(json.dumps(criteria,ensure_ascii=False,indent=2)+'\n')
m['lineage']['hypothesis_delta']=hyp;m['design'].update(hypothesis=hyp,primary_metric='Native API and source provenance contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(R)),'sha256':hashlib.sha256((D/'criteria.json').read_bytes()).hexdigest()})
m['design']['arms'][0].update(changes='Historical ADR1266 root offline failure',controls='No fresh live model');m['design']['arms'][1].update(changes='Version-aware provenance projection only',controls='Same validation/ACL/source reads; tests synthetic')
m['runs'][0].update(arm_ids=['repaired'],artifact_path=str((D/'result.json').relative_to(R)),selection_rule='Existing failing v6/v7 API and explicit DIRECT/DEPENDENCY v6/v7/v8 contracts')
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
sources=list(json.loads((R/'04_EXPERIMENTS/ADR/ADR-1266-agent-loop-recovery-qwen-live/artifacts/design/working-before.json').read_text()))
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=ac.snapshot(A,'repaired',sources,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])/'snapshot'
p=S/'02_BACKEND/semantic_runtime/legal_agent/decision_projection.py';s=p.read_text()
old="                decision['exploration']=[{**r,'request_quote':issue_map[r['issue_id']].get('request_quote',request),'source_quote':''} for r in selected]"
new="""                fields=branch['properties']['exploration']['items']['properties']
                decision['exploration']=[]
                for row in selected:
                    provenance={**row,'request_quote':issue_map[row['issue_id']].get('request_quote',request),'source_quote':''}
                    if 'source_ref' not in fields:
                        # v6/v7 require an exact quote instead of the v8 handle.
                        # The handle was selected by the model and validated above.
                        reference=provenance.pop('source_ref')
                        if row['relation']=='DEPENDENCY':provenance['source_quote']=current[reference]['text']
                    decision['exploration'].append(provenance)"""
assert old in s;s=s.replace(old,new);p.write_text(s)
mapping={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text());before=hashlib.sha256(p.read_bytes()).hexdigest();changed=False
 for n,h in v.get('files',{}).items():
  actual=hashlib.sha256((S/n).read_bytes()).hexdigest()
  if actual!=h:v['files'][n]=actual;changed=True
 if changed:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');mapping[before]=hashlib.sha256(p.read_bytes()).hexdigest()
p=S/'00_SYSTEM/PIPELINE.json';s=p.read_text()
for old,new in mapping.items():s=s.replace(old,new)
p.write_text(s)
(D/'candidate.json').write_text(json.dumps({'snapshot':str(S.relative_to(R))},indent=2)+'\n');print(S)
