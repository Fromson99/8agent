from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0693-main46-display-judgment-integration'
D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/b['manifest_path']);assert b['generation']==46
put(D/'baseline.json',{'pointer':b,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release})
criteria={'scope':'P1 explicit public display allowlist; P2 v4 accepted judgment, typed per-gap receipts and source-bound condition groups. Probe only; no external model calls or promotion in this ADR.', 'required':['no diagnostic payload in public JSON/SSE/cards/cached display','full scrubbed causes remain in operational log','normal answers/citations and HTTP failure status retained','material gap never COVERED','same-issue adopted provenance for resolved gaps','late/stale proposals cannot replace accepted revision','v1/v2/v3 historical render preserved','condition group provenance/cycle/depth/fact-source validation','same confirmed claims used by COMPOSE and judgment view'], 'controls':{'baseline':'MAIN46 release + exact selected source generation','integration':'Current working edits preserved in isolated integration package and mapped per-file; no candidate overwrites working tree','model_calls':0,'data_rebuild':False},'independent_qualification':'Separate follow-up ADR freezes new public-only paired dataset before any model call; probe is in-sample and not decision eligible'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['design'].update(hypothesis=criteria['scope'],primary_metric='Public-boundary, judgment and provenance contract failures',success_criteria=criteria['required'],failure_criteria='Any required invariant fails',criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['scope'];m['llm_policy']['llm_calls']=[]
for arm in m['design']['arms']:
 arm.update(changes={'baseline':'Selected MAIN46 and inherited display fixtures','safe-display':'Public-only display policy over maintained current consumers','consistent-judgment':'safe-display plus v4 judgment integration'}[arm['id']],controls='Same source generation; no real model calls; exhaustive synthetic contracts, not quality certification')
m['dataset'].update(name='Synthetic display and completion counterexamples',version='main46-contracts-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(selection_rule='All declared public-boundary and completion contracts; no model effect measurements',artifact_path=str((A/'artifacts/contracts/result.json').relative_to(R)))
m['retrieval_accounting']['not_applicable_reason']='No real retrieval comparison; deterministic synthetic contract checks only'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
put(A/'실험/manifest.json',m)
# Snapshot all maintained serving inputs. Record every inherited pending change for review.
files=set(release['files'])
files.update(['service.py','main_workflow.py','main_router.py','main_integrated.py','08_DEPLOYMENT/GENOS/stream_app.py','02_BACKEND/lawrag/research/experiment_client.py'])
files.update(str(p.relative_to(R)) for p in (R/'02_BACKEND/semantic_runtime').rglob('*.py'))
files.update(str(p.relative_to(R)) for p in (R/'05_TESTS/CONTRACTS').glob('*.py'))
files=sorted(p for p in files if (R/p).is_file())
put(D/'integration-map.json',{p:{'working_sha256':sha(R/p),'main46_sha256':release['files'].get(p),'working_differs':sha(R/p)!=release['files'].get(p)} for p in files})
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','safe-display','--experiment-id',m['experiment_id'],'--arm-id','safe-display','--run-id','run-001']
for p in files:cmd+=['--source',p]
subprocess.run(cmd,cwd=R,check=True)
print('Frozen initial design and snapshot:',len(files),'files')
