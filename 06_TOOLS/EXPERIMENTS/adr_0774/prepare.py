from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main'; D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text()); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'scope':'Integrate previously implemented deterministic source-gap action correction into MAIN59, with no new product edits. All other MAIN59 behavior retained.', 'required':['Only non-MISSING_FACT REQUEST_FACT becomes RESEARCH; preserve all gap content and ordering','Input immutable; idempotent normalization; exact correction audit','v5-v8 original schema/evidence/fact/meaning validation retained','Bounded API research reentry, repeated gap limited answer, no-claims failure, duplicate request no extra model calls','MAIN59 successful publication, ACL, state and shortcut regressions retained','Exact candidate bytes/pins equal working and selected service code; no original data or profile changes'], 'matrix':{'single_kinds':['MISSING_SOURCE','MISSING_FACT','UNRESOLVED_REFERENCE','CONFLICTING_SOURCE','INSUFFICIENT_SCOPE','MISSING_DEFINITION','MISSING_PROCEDURE'], 'kind_source':'actual GAP_KINDS enum captured in matrix runner; all entries required','actions':['REQUEST_FACT','RESEARCH'],'material':[False,True],'target':['absent','empty','named'],'material_id':[None,'M1'],'pair':'Cartesian product of all kinds/actions/material values for two ordered gaps, with distinct targets/issue IDs'}, 'evaluation':'Prospectively fixed exhaustive synthetic field contract audit; prior known tests are supplemental regression, not fresh holdout. No law answer accuracy, recall or field latency claim.', 'model_calls':0, 'failure':'Any invariant violation, new regression, unsupported answer or code/ACL/state mismatch blocks activation. Four previously documented recovery fixture failures stay open and are not suppressed or counted passed.', 'rollback':'Standard release rollback to MAIN59 content, immutable parent and source bytes preserved.'}
assert not (D/'criteria.json').exists();put(D/'criteria.json',criteria)
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';a=read(p);assert a['generation']==59
release=read(R/a['manifest_path']);put(D/'baseline.json',{'pointer':a,'pointer_sha256':sha(p),'manifest':release})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Every exhaustive field transformation equals declared contract with no mutation or unsafe admission',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['dataset'].update(name='Exhaustive synthetic gap-field transformation matrix',version='gap-action-main-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[];m['runs'][0].update(selection_rule='Exhaustive enum/action/material/target/reference combinations and fixed ordered gap pairs; existing regressions supplemental',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Deterministic schema/action compatibility audit. No real corpus retrieval or ranking compared. Research reentry is simulated under existing bounds.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='Synthetic field transformation and API doubles only; no retrieval metric or legal answer evaluation.')
for arm in m['design']['arms']:arm.update(changes='Selected MAIN59 unchanged' if arm['id']=='baseline' else criteria['scope'],controls='Same source data, model, prompts, profile, retrieval, success publication policy')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
names=set(release['files'])
# Include existing contract fixtures without runtime discovery; hash-pinned below.
names.update(str(p.relative_to(R)) for p in (R/'05_TESTS/CONTRACTS').glob('*.py'))
names.add('05_TESTS/conftest.py')
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','source-gap-action','--experiment-id',m['experiment_id'],'--arm-id','source-gap-action','--run-id','run-001']
for n in sorted(names):cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
put(D/'working-source.json',{n:sha(R/n) for n in sorted(names)})
changes=[n for n in release['files'] if sha(R/n)!=release['files'][n]]
source=[n for n in changes if not n.endswith('.json')]
assert source==['02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py','02_BACKEND/semantic_runtime/legal_agent/completion_v5.py','02_BACKEND/semantic_runtime/legal_agent/completion_v6.py'],source
put(D/'selected-working-delta.json',[{'path':n,'selected':release['files'][n],'working':sha(R/n)} for n in changes])
print('Prepared snapshot',len(names),'delta',len(changes),'product source',len(source))
