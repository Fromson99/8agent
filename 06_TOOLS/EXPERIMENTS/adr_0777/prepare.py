from pathlib import Path
import hashlib,json,subprocess,shutil
from matrix import cases,STATE_CASES
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0777-schema-recovery-main';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0777/recovery';P=R/'02_BACKEND/lawrag/research/candidates/adr_0776/recovery'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria={'scope':'Typed output errors, exact normalization, one correction owner, durable request/build budgets and unchanged evidence/ACL/state/publication guards.',
 'matrix':{'syntax_completion_cases':400,'state_cases':STATE_CASES,'expected_total':410},
 'evaluation':'Exhaustive synthetic contract audit fixed before execution; no claim of unseen legal-answer or actual model effectiveness.',
 'required':['Every candidate matrix case passes acceptance, typed classification, input/value preservation or durable state contract',
 'All 817 mandatory known regressions pass; one uncollected historical module remains excluded from passed count',
 'No additional physical call for a valid proposal; one correction maximum; unknown outcome and streamed failure never replay',
 'All original evidence, source scope, access, hash, revision and publication guards preserved',
 'Exact source-file integration and qualified local MAIN selected-service binding verified; GENOS separate'],
 'failure':'Any candidate contract failure or new mandatory regression blocks promotion. No quality waiver.',
 'model_calls':0,'normalization':'Only original allowed mappings, exact duplicate rows and complete outer build JSON fence; hash/audit and full validation',
 'rollback':'MAIN61 content via standard rollback; field installer backup undo and previous serving revision',
 'known_working_drift':'Preexisting input metrics/request reporting/pins kept; not attributed to this implementation',
 'conditional_deferred':['Keyed decision-object and sparse patch wire protocols require separate provider experiments; not activated.']}
put(D/'criteria.json',criteria);put(D/'cases.json',cases())
pointer=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(pointer);assert active['generation']==61
base=read(R/active['manifest_path']);put(D/'baseline.json',{'pointer':active,'pointer_sha256':sha(pointer),'manifest':base})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],
 primary_metric='All declared synthetic output and persistent recovery contract cases pass',
 success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['dataset'].update(name='Exhaustive synthetic JSON/completion and persisted correction states',version='output-recovery-contract-v1',
 frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[];m['runs'][0].update(selection_rule='All 410 prospectively enumerated contract cases plus known mandatory regression selection',
 artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Synthetic fault/state audit; no retrieval or legal quality comparison.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No measured corpus recall/ranking change.')
for arm in m['design']['arms']:arm.update(changes='Selected MAIN61 unchanged' if arm['id']=='baseline' else criteria['scope'],
 controls='Same source generation/model policy, original evidence and publication guards; no real model call')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
parent=read(P/'candidate.json');rev=parent['revisions'][-1];assert rev['revision_id']=='rev-010'
source=P/'revisions'/rev['revision_id']/'snapshot'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),
 '--candidate-id','recovery','--experiment-id',m['experiment_id'],'--arm-id','recovery','--run-id','run-001']
for row in parent['files']:
    name=row['target_path'];live=R/name
    if row['upstream_state']=='present':
        assert live.exists() and sha(live)==row['upstream_sha256'],name
        cmd+=['--source',name]
    else:assert not live.exists(),name
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
for row in parent['files']:
    name=row['target_path'];dest=C/'snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,dest)
    if row['upstream_state']=='absent':
        subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),
            '--target',name,'--upstream-state','absent'],cwd=R,check=True,stdout=subprocess.DEVNULL)
put(D/'source-parent.json',{'manifest':str((P/'candidate.json').relative_to(R)),'sha256':sha(P/'candidate.json'),
    'revision':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
selection=read(R/'04_EXPERIMENTS/ADR/ADR-0776-schema-recovery-runtime/artifacts/development/regression-r10-selection.json')
put(D/'regression-selection.json',{'tests':selection['tests'],'expected_passed':817,'expected_skipped':1})
print('criteria and candidate prepared; no evaluation or promotion')
