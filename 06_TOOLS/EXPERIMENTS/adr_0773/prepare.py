from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0773-successful-shortcut-publication'; D=A/'artifacts/design'
D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text()); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'scope':'Successful final publication admits native shortcut lists and wiki compilation/reuse. Preserve complete failure logs and manually curated source catalogue. Include previously implemented AD page fix and shipped request logging/transport fixes in the verified integration.',
 'required':['Failed, interrupted, blank, clarification-only, unpublished and hash-corrupt runs never enter shortcut list or native wiki reuse','Successful final export with nonempty supported answer, current route, source and ownership checks is admitted; recovered intermediate errors do not disqualify success','Success receipt and core entry commit atomically; failures preserve raw investigations and may retry safely','Corrections, stale routes, excluded records, wrong principals and revoked sources continue to fail closed','Native compiler rejects cases without completed publication before any model call and records the exact successful input binding; rejected executions never become accepted judgment traces','Legacy success is restored only by explicit verification of durable publication journals; missing evidence stays unconfirmed, never deleted','Curated operator source routes keep separate provenance and existing ACL; never acquire fabricated answer success','AD paging boundary and prior logging/transport contract fixes preserved','Same validated code integrated, selected by standard MAIN promotion, and actual local service binding checked; GENOS package exact installer/gate/rollback tested'],
 'matrix':{'terminal':['success','recovered_success','failed','interrupted','pending_export','empty','clarification','tampered_receipt','stale_revision','retired_route','foreign_team','rejected'], 'surfaces':['ad_shortcut','native_wiki','compiler']},
 'model_calls':0,'evaluation':'Prospectively frozen exhaustive synthetic publication-state contracts, independent source/ACL/transport regressions. No semantic accuracy or GENOS latency claim.',
 'failure':'Any new publication, ACL, state preservation or actual serving binding failure blocks promotion. Development test failures retained; final frozen audit runs once.',
 'rollback':'Prior MAIN58 and hash guarded working/GENOS file backups; additive receipt table ignored by old code, no raw data deletion.'}
assert not (D/'criteria.json').exists();put(D/'criteria.json',criteria)
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';a=read(p);assert a['generation']==58
release=read(R/a['manifest_path']);put(D/'baseline.json',{'pointer':a,'pointer_sha256':sha(p),'manifest':release})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Publication eligibility matches every frozen terminal-state/surface case; zero failed-run admission and no loss of raw logs',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['dataset'].update(name='Synthetic terminal publication state matrix',version='successful-shortcut-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[];m['runs'][0].update(selection_rule='All fixed lifecycle/surface combinations and specified regression suites after code/runner freeze; no model calls',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='State admission contract audit; no corpus retrieval, ranking, law/gold evaluation or model calls. Runtime memory eligibility changes are explicitly in scope.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='Synthetic publication states, not a law retrieval experiment; exact surface admissions recorded per case.')
for arm in m['design']['arms']:arm.update(changes='Selected MAIN58' if arm['id']=='baseline' else criteria['scope'],controls='Same data/model/prompts and source-selection policy; only terminal success admission and reviewed existing fixes')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
names=set(release['files']);config=read(R/'00_SYSTEM/PIPELINE.json')
for e in config['engines'].values():names.update(read(R/e['manifest'])['files'])
names.update(['05_TESTS/CONTRACTS/test_ad_pagination.py'])
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','successful-publication','--experiment-id',m['experiment_id'],'--arm-id','successful-publication','--run-id','run-001']
for n in sorted(names):cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
put(D/'working-source.json',{n:sha(R/n) for n in sorted(names)})
put(D/'selected-working-delta.json',[{'path':n,'selected':release['files'].get(n),'working':sha(R/n)} for n in sorted(names) if release['files'].get(n)!=sha(R/n)])
print('Criteria and working integration snapshot frozen',len(names))
