from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0784-length-adapter-parity';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria={'scope':'Prospective finite length recovery wire/owner/budget contract audit, plus previous four failures resolved with current contracts.',
 'matrix':{'ceiling':[0,1536,6400,12800],'initial':[1536,6400],
 'first':['stop','length','content_filter','refusal'],'second':['stop','length','content_filter'],
 'usage':[False,True],'expected_total':192},
 'namespace_matrix':{'checkouts':8,'dependencies':4,'maturities':2,'expected_total':64},
 'resolved_symlinks':{'checkouts':2,'targets':2,'maturities':2,'expected_total':8},
 'adapter_matrix':{'finishes':4,'providers':2,'models':2,'thinking':2,'expected_total':32},
 'required':['All 296 frozen length/cap/finish/usage cases pass under candidate','Every frozen regression passes, no known-failure exemption','Existing normal request bytes/call budget unchanged; length correction only within explicit ceiling','No partial JSON applied; one existing owner; original failure/output/deadline retained','Working, evaluated candidate and selected serving files identical'],
 'failure':'Any finite contract failure, new regression, skip, missing test or code drift blocks promotion.',
 'limitations':['Synthetic host contract verification, not field model efficacy or legal accuracy','Original screenshot usage/context/provider output cap not available','No output compression or partial JSON repair'],
 'external_model_calls':0}
put(D/'criteria.json',criteria)
pointer=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=read(pointer);assert active['generation']==65
base=read(R/active['manifest_path']);put(D/'baseline.json',{'pointer':active,'pointer_sha256':sha(pointer),'manifest':base})
files=set(base['files'])|{'00_SYSTEM/SCHEMAS/pipeline-v1.schema.json','00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json'}
changed=[{'path':n,'selected_before':base['files'].get(n),'working_after':sha(R/n)} for n in sorted(files) if base['files'].get(n)!=sha(R/n)]
put(D/'working-delta.json',{'changes':changed,'reason':'Length correction opt-in and pipeline schema; normal caps/data/search/model unchanged.'})
put(D/'regression-selection.json',{'tests':read(R/'90_RUNTIME/length_recovery_20261014/checks.json'),'known_failure_exemptions':[]})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='296 finite host length contracts pass',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['dataset'].update(name='Finite synthetic output length recovery contracts',version='navigation-length-recovery-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[];m['runs'][0].update(selection_rule='All frozen length/cap/finish/usage states; previous regressions separately reported',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Host recovery protocol, no corpus or semantic quality comparison.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No retrieval recall measurement.')
for arm in m['design']['arms']:arm.update(changes='Selected MAIN64 same-cap correction' if arm['id']=='baseline' else criteria['scope'],controls='Same data/model/search; only explicit length correction allowance added')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','recovery','--experiment-id',m['experiment_id'],'--arm-id','recovery','--run-id','run-001']
for n in sorted(files):cmd+=['--source',n]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
print('Prepared',len(files),'files;',len(changed),'changes; prospective296cases')
