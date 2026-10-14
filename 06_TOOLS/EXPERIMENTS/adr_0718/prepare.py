from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0718-main50-request-repair-integration'; D=A/'artifacts/design'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());base=json.loads((R/pointer['manifest_path']).read_text())
assert pointer['generation']==50
for p,h in base['files'].items():assert sha(R/p)==sha(R/base['code_root']/p)==h,p
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':base})
criteria={'scope':'Request-scoped decision epochs; code-owned target gap identity and target receipts; same-request progress; exact decision deduplication; request/context provenance; delivery-span reuse; versioned nested completion structure and content preservation; approved final outcome and prompt projection; existing seven stages and data retained.',
 'implementation_plan':{'path':'07_DOCS/REFERENCE/REPORTS/MAIN50_CM51_REPAIR_IMPLEMENTATION_PLAN_20261009/PLAN.md','sha256':sha(R/'07_DOCS/REFERENCE/REPORTS/MAIN50_CM51_REPAIR_IMPLEMENTATION_PLAN_20261009/PLAN.md')},
 'required':['same-decision repair resumes reuse immutable presentation','new epoch retires prior retry without resetting request budget','alias and optional material do not reopen same resolved target','different document version scope issue or unlocated target not falsely merged','wrong-target and incomplete search cannot prove absence','resolved gaps cite target-bound adopted delivered spans including reused originals','same evidence cannot reopen a closed gap by changing wording','read reuse preserves delivery adoption and excluded/deferred status','exact duplicated decisions normalized before corrective call; conflicts rejected','explicit request quotes preserve question and do not promote background-only issues','nested conditions compile without orphan refs and preserve ALL ANY UNKNOWN','approved details and condition/exception roles survive composition and all consumers','v1-v4 completed payloads retain renderer and verifier','physical budget and severe quote access state binding checks retained','final accounting reads accepted assessment and response rather than raw model proposal'],
 'execution':{'type':'synthetic contract implementation validation','model_calls':0,'real_private_questions':False,'main_wiring':'unchanged until separate eligible public qualification','production_mutation_before_decision':False},
 'success':'All new meaningful synthetic boundary and native integration tests pass; targeted existing behavior regressions resolved or accurately isolated; product files unchanged; complete frozen candidate retained.',
 'failure':'Any unresolved severe quote, access, binding, state, coverage, composition or native wiring error; probe never qualifies MAIN by itself.',
 'preserved':['source and index generation','public export boundary','request deadlines and total attempts','model identity','DIRECT/CASE and existing-case methods','no personal wiki autoprompt','no extra permanent judge','progress and actual model call metrics'],
 'future_holdout':'Separate ADR after implementation completes; new public original roots and independent source review; repeated requests planned before first call; known CM traces used only for diagnosis and synthetic fixtures.'}
put(D/'criteria.json',criteria)
put(D/'dataset.json',{'name':'Synthetic request lifecycle and completion contract fixtures','version':'v1','cases':[], 'real_question_export':False,'description':criteria['required']})
m=json.loads((A/'실험/manifest.json').read_text());m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Native contract invariants on synthetic fixtures; no quality or performance estimate',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:arm.update(changes='Unchanged selected MAIN50' if arm['id']=='baseline' else criteria['scope'],controls='No real model calls, unchanged originals and external boundary, frozen synthetic fixtures; not a legal accuracy comparison')
m['runs'][0].update(selection_rule='Synthetic boundary and native API contracts fixed in criteria before candidate implementation; no quality comparison or external calls',arm_ids=['repaired'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Synthetic request/completion contracts',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['retrieval_accounting'].update(changed=False,not_applicable_reason='No corpus retrieval effect measurement; synthetic contract implementation checks only')
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','repaired','--experiment-id',m['experiment_id'],'--arm-id','repaired','--run-id','run-001']
sources=set(base['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}
# Current tests are recorded as part of the immutable synthetic validation inputs.
sources|={str(p.relative_to(R)) for p in (R/'05_TESTS/CONTRACTS').glob('test_*.py') if p.name in {'test_judgment_loop_recovery.py','test_completion_v4.py','test_exception_wire.py','test_law_grouped_navigation.py','test_structure_reading.py','test_unified_legal_agent.py','test_compact_metrics.py','test_public_display_boundary.py','test_genos_answer_stream.py','test_main_workflow_display.py','test_wire_repair.py','test_followup_structure_lookup.py','test_investigation_completion_adr0678.py','test_completion_boundary_adr0679.py','test_law_navigation_state_contract_adr0661.py','test_document_focus.py','test_named_menu.py'}}
for p in sorted(sources):cmd+=['--source',p]
subprocess.run(cmd,cwd=R,check=True)
print('ADR0718 criteria and baseline fixed; isolated implementation snapshot created.')
