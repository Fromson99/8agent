from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0771-source-cards-main-wiring';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'scope':'Connect the already implemented source-list UI to the real MAIN56 progress producer. Preserve all model input, search, source authorization, accepted answers, data, AD and token streaming. No model calls.',
'required':['Each admitted source path arrives at the renderer as its own Markdown list item','Consecutive read notifications form one card without truncation across 0,1,9,37 rows','Visible phase, candidate and answer boundaries preserve chronology and streamed answer bytes','Private model I/O and rejected decisions remain absent from public progress','Request isolation, source scope and failed/no-socket completion retain their contracts','All non-display semantic runtime files, profiles, prompts, source generation and active service settings unchanged','Same qualified code in working tree, selected release and actual service.service entry'],
'matrix':{'counts':[0,1,9,37],'boundaries':['candidate','decision','answer'],'modes':['socketio','final-cards']},
'failure':'Any new display/integrity failure blocks promotion. No semantic quality claim or quality waiver.',
'evaluation':'Prospectively fixed complete synthetic progress-producer-to-renderer matrix; 24 combinations, no real LLM latency or legal-quality benchmark',
'prior_work':'R1 UI implementation and 72 known contract results predate this ADR. This new qualification covers the previously unconnected MAIN producer plus the complete fresh boundary matrix; prior tests are regression only.',
'model_calls':0,'rollback':'Previous MAIN56 release and reviewed file backups'}
assert not (D/'criteria.json').exists();put(D/'criteria.json',criteria)
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';a=read(p);assert a['generation']==56;release=read(R/a['manifest_path']);put(D/'baseline.json',{'pointer':a,'pointer_sha256':sha(p),'manifest':release})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Every source path retained with grouped reads and byte-identical streamed answer',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['dataset'].update(name='Prospective exhaustive synthetic progress producer and UI boundaries',version='source-cards-main-boundaries-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[];m['runs'][0].update(selection_rule='All frozen source counts, visible boundaries and display modes, once after code and runner freeze',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Progress display only; retrieval and accepted original-source answer unchanged');m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No retrieval execution, selection or legal evaluation; display boundary audit')
for arm in m['design']['arms']:arm.update(changes='MAIN56 compact progress projection' if arm['id']=='baseline' else criteria['scope'],controls='Same model input/schema/prompts and canonical completed text; no external model calls')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','source-cards','--experiment-id',m['experiment_id'],'--arm-id','source-cards','--run-id','run-001']
for n in sorted(release['files']):cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
print('Criteria frozen; MAIN56 isolated into source-cards candidate')
