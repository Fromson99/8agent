from pathlib import Path
import json,sys,shutil
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1053-ontology-mvp-step-state';ART=ADR/'artifacts'
read=lambda p:json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1049-ontology-mvp-provider-failover';old=read(prior/'실험/manifest.json');m=read(ADR/'실험/manifest.json')
m['design']=old['design'];d=m['design'];d['code_isolation']['candidates']=[];d['criteria_frozen_before_run']=False
m['lineage']['hypothesis_delta']='Completed1052 law overview/progressive clauses plus deterministic per-decision server state across native and workflow gateways. Common change in all three arms; no causal token reduction claim against incomplete1049.'
d['hypothesis']='Every logical model decision receives authoritative current revisions, last tool outcome, evidence availability, stage task, input references and remaining budget without a new summarization call. Compare unchanged ontology A0/A1/A2 on37 approved cases.'
d['operational_success_criteria']='Every model request has server step-state; no source text or model judgment rewriting; no extra calls; accepted replay identity stable; errors/unknowns/ACL/hash/revisions/budgets preserved. API and contract checks must pass before live execution.'
d['arms'][0]['derived_from']=['ADR-1052-experiment-v1/overview']
for a in d['arms']:a['controls']='Same1053 code,37cases,current corpus, approved provider chain, output unlimited,40calls1024tools1800seconds; A0/A1/A2 ontology mode only.'
d['provider_policy']=old['design']['provider_policy'];d['live_execution_gate']='User2026-10-25 approved implementation, MVP documentation and new experiment; isolated candidate tests then freeze; no MAIN promotion.'
m['runs'][0].update(arm_ids=['A0','A1','A2'],selection_rule='All37 approved cases × A0/A1/A2; inherited counterbalanced order; sequential; never replay started cell',artifact_path=str((ART/'matrix-summary.json').relative_to(ROOT)),sha256='PENDING')
m['dataset']=old['dataset'];m['dataset']['frozen_source']=str((ART/'dataset-freeze-r1.json').relative_to(ROOT));m['llm_policy']=old['llm_policy'];m['retrieval_accounting']=old['retrieval_accounting'];m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING');m['questions']=old['questions']
for q in m['questions']:
 for k,v in q.items():
  if isinstance(v,str):q[k]=v.replace(prior.name,ADR.name)
for p in (prior/'실험').glob('질문-*.md'):(ADR/'실험'/p.name).write_text('Execution pending; frozen reporter will populate.\n')
save(ADR/'실험/manifest.json',m)
save(ART/'implementation-plan.json',{'before_implementation':True,'scope':'native and workflow shared model gateway; all logical stages including repair and resumed new decisions','mechanism':'wire-only server fact projection; canonical view and decision replay key unchanged; no LLM summary','failure_owner':'existing gateway/workflow owners unchanged','retries':'no new retries; existing budget and known429 failover only','on_invalid_state':'existing contract/stale failure; no model correction bypass','checks':['stage coverage','unknown and failed tool preservation','no duplicate source or opinion text','budget/resume/replay','ACL/hash/state regressions','real API fixture'],'live':'37x3 after exact frozen code validation; no MAIN'})
for n in ['cases-product.json','cases-evaluator-r1.json','corpus-selection-r1.json','execution-authorization-20261024-r1.json','evaluation-contract.json','dataset-freeze-r1.json','approved-bundles-20261024-r1.json','corpus-article-root-count-r1.json','provider-authorization.json','provider-endpoints.json']:
 shutil.copyfile(prior/'artifacts'/n,ART/n)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
parent=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1052/law-overview-r1';manifest=read(parent/'candidate.json');frozen=parent/'revisions/rev-002/snapshot'
target=c.snapshot(ADR,'step-state-r1',[r['target_path'] for r in manifest['files'] if (ROOT/r['target_path']).is_file()],experiment_id=m['experiment_id'],arm_id='A2',run_ids=['run-001'])
for r in manifest['files']:
 n=r['target_path'];dest=target/'snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(frozen/n,dest)
 if not (ROOT/n).is_file():c.register_file(target,n,upstream_state='absent')
c.refresh(target)
print(target)
