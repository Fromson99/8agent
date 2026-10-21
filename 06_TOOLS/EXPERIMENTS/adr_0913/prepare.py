from pathlib import Path
import json,hashlib,shutil,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0913-answer-first-financial-scope';P=R/'04_EXPERIMENTS/ADR/ADR-0912-answer-first-user-followup';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();f=read(P/'artifacts/design/freeze.json')
for n in ('baseline.json','baseline-binding.json','answer-first-binding.json','working-before.json','changes.json','cases.json','execution-plan.json'):shutil.copy2(P/'artifacts/design'/n,D/n)
c=read(P/'artifacts/design/criteria.json');c.update(team_id='financial_team',scope_correction='CM001 original metadata belongs to financial_team; use team/public whitelist intersection for both arms. Previous invalid risk_team model runs are not reused as performance baseline.',product_change=False,parent_contracts='115 passed, seven legacy failures reproduced on baseline. Exact frozen product code, no new algorithm/prompt changes.');put(D/'criteria.json',c)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0912/live.py').read_text().replace('ADR-0912-answer-first-user-followup','ADR-0913-answer-first-financial-scope').replace('adr0912-','adr0913-').replace("TEAM_ID='risk_team'","TEAM_ID='financial_team'").replace("store,'risk_team'","store,'financial_team'").replace('    assert request_scope','    assert request_scope\n    assert \'3521c3aaa5a735fd\' in request_scope, \'CM corpus scope missing KOSDAQ rule\'');(T/'live.py').write_text(s)
for n in ('observe.py','report.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0912'/n).read_text().replace('ADR-0912-answer-first-user-followup','ADR-0913-answer-first-financial-scope').replace("risk_team public scope (28 documents)","financial_team public scope").replace("115 scoped checks pass.","115 unchanged-parent scoped checks pass.")
 (T/n).write_text(s)
shutil.copy2(P/'artifacts/contract-disposition.json',A/'artifacts/contract-disposition.json')
m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
m.update(in_sample=True,decision_eligible=False);m['design']={**old['design'],'hypothesis':c['hypothesis'],'criteria_frozen_before_run':True}
m['design']['code_isolation']={'mode':'not_applicable','reason':'No new product implementation. Reuse both immutable ADR0912 rev-002 snapshots and verify every hash; only runner team selection is corrected before first calls.','candidates':[]}
m['design']['arms']=[{'id':arm,'role':'candidate','derived_from':['ADR-0912-experiment-v1/answer-first'],'changes':'Exact ADR0912 '+arm+' frozen snapshot, financial_team shared runner scope. Baseline removes the same answer-first delta as the parent paired design.','controls':'Same team, source generation, model, instrumentation; product code unchanged.'} for arm in ('baseline','answer-first')]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'selected','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'cited','kind':'present','parent_stage_ids':['selected']}];m['design']['retrieval_stage_plan']['stages_by_arm']={a:plans for a in ('baseline','answer-first')}
m['runs'][0].update(arm_ids=['baseline','answer-first'],selection_rule=c['evaluation']+' Financial team/public whitelist intersection.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='cm-financial-answer-first-followup',version='20261019-r1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=old['llm_policy']['llm_calls']
m['retrieval_accounting']['not_applicable_reason']='Acquired, selected, cited source accounting. No legal gold or search recall measurement.';m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
files={n:h for n,h in f['files'].items() if '/revisions/' in n or not n.startswith(('06_TOOLS/EXPERIMENTS/adr_0912/',str((P/'artifacts/design').relative_to(R))+'/'))}
for p in [*T.glob('*.py'),*D.glob('*.json')]:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'reused_candidates':f['candidates'],'no_product_change':True})
print('Both immutable snapshots reused; financial_team model experiment frozen')
