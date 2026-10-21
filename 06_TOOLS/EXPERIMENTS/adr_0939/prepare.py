from pathlib import Path
import hashlib,json,shutil,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0939-research-continuity-qualified';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0938-research-continuity-ingress/artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
for name in ('criteria.json','baseline.json','changes.json','connected-binding.json','serving-files.json'):shutil.copyfile(P/name,D/name)
c=read(D/'criteria.json');c['scope']='Read-only finite contract audit of unchanged completed ADR0938 code; no new implementation or real legal quality evaluation.'
c['qualification']='All 2 sides x 3 fields x 5 terminal states x 2 evidence transitions; all 6 interval orders; both actual ingress binding states; prior API, interruption, partial originals and duplicate/state/source checks. No new failures; known baseline eight failures remain disclosed.'
put(D/'criteria.json',c)
runner=(R/'06_TOOLS/EXPERIMENTS/adr_0938/run_tests.py').read_text().replace('ADR-0938-research-continuity-ingress','ADR-0939-research-continuity-qualified')
(T/'run_tests.py').write_text(runner)
tests=['06_TOOLS/EXPERIMENTS/adr_0936/'+n for n in ('test_generalized.py','test_lossless_wire.py','test_durable.py','test_host_links.py','test_patch_contract.py')]
tests+=['06_TOOLS/EXPERIMENTS/adr_0938/test_continuity.py','06_TOOLS/EXPERIMENTS/adr_0938/test_research_resume.py',str((T/'test_qualification.py').relative_to(R)),
 '05_TESTS/CONTRACTS/test_main50_request_repair.py','06_TOOLS/EXPERIMENTS/adr_0890/test_focus.py','06_TOOLS/EXPERIMENTS/adr_0922/test_connected_exploration.py']
put(D/'execution-plan.json',{'tests':tests,'expected_existing_failures':c['known_baseline_failures'],'resource_limits':c['limits'],'post_integration':'Repeat exact affected checks with working code; verify every serving file equals immutable candidate. Do not change active MAIN90.'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=c['qualification']
m['design'].update(hypothesis=c['hypothesis'],primary_metric='Finite state and consumer continuity invariants',success_criteria=c['success'],failure_criteria=c['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'qualified','role':'candidate','derived_from':['ADR-0938-experiment-v1/connected'],'changes':'No product changes; immutable completed snapshot audit','controls':c['qualification']}]
m['design']['code_isolation'].update(mode='not_applicable',reason='Read-only structural and finite contract audit; no new implementation candidate. Reuse completed ADR0938 immutable snapshot and verify every serving hash.',candidates=[])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=c['qualification'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='research-continuity-finite-state-contracts',version='20261020-r3',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['llm_policy']['llm_calls']=[]
why='Technical state and structural contract audit only; no model/search effect comparison.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=why);m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=why)
put(A/'실험/manifest.json',m)
files={n:h for n,h in read(P/'freeze.json')['files'].items() if not n.startswith(str(P.relative_to(R))+'/')}
for folder in (T,D):
 for p in folder.glob('*'):
  if p.is_file():files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
print('Unchanged product code, 68 finite combinations plus existing regression/API suites frozen.')
