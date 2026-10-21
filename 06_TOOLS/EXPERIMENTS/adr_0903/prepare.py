from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0903-read-input-connected-contract';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0902-read-input-contract-qualification'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();f=read(P/'artifacts/design/freeze.json')
for n in ['criteria.json','baseline.json','changes.json','working-before.json','execution-plan.json']:shutil.copyfile(P/'artifacts/design'/n,D/n)
c=read(D/'criteria.json');c['evaluation']='Same 90 finite boundaries and immutable ADR0902 code; API fixture supplies trusted test_team per current team selector and uses navigation rather than the historical direct-source shortcut. No model calls, product changes, legal quality or latency claims.';put(D/'criteria.json',c)
text=(R/'06_TOOLS/EXPERIMENTS/adr_0902/test_input.py').read_text()
needle="    api.test_current_compact_api_publishes_and_reuses_verified_original(tmp_path, tree, monkeypatch)"
replacement="""    import semantic_runtime.app as app_module
    create = app_module.create_app
    def current_fixture(*args, **kwargs):
        kwargs['memory_identity'] = lambda _: {'team_id': 'test_team', 'document_ids': ['d']}
        kwargs['legal_agent_transport'].direct_note = False
        return create(*args, **kwargs)
    monkeypatch.setattr(app_module, 'create_app', current_fixture)
    api.test_current_compact_api_publishes_and_reuses_verified_original(tmp_path, tree, monkeypatch)"""
assert needle in text;text=text.replace(needle,replacement);(T/'test_input.py').write_text(text)
(T/'run_tests.py').write_text((R/'06_TOOLS/EXPERIMENTS/adr_0902/run_tests.py').read_text().replace('ADR-0902-read-input-contract-qualification','ADR-0903-read-input-connected-contract'))
plan=read(D/'execution-plan.json');plan['tests'][0]=str((T/'test_input.py').relative_to(R));put(D/'execution-plan.json',plan)
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=c['evaluation']
m['design'].update(hypothesis=c['hypothesis'],primary_metric='Finite input preservation and actual API original publication',success_criteria=c['success'],failure_criteria=c['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'qualified','role':'candidate','derived_from':['ADR-0902-experiment-v1/qualified'],'changes':'No product change. Correct API fixture team selector and request navigation path.','controls':'Exact immutable ADR0902 candidate; same finite boundaries and no model calls.'}]
m['design']['code_isolation'].update(mode='not_applicable',reason='No implementation change; reuse completed immutable ADR0902 snapshot with every file hash bound, avoiding duplicate storage.',candidates=[])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=c['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='finite-input-preservation-contracts',version='20261019-r3',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
why='Finite synthetic software contracts without model/retrieval comparison.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why
put(A/'실험/manifest.json',m)
files={n:h for n,h in f['files'].items() if n.startswith(f['code_root']+'/')}
for folder in [T,D]:
 for p in folder.glob('*'):
  if p.is_file():files[str(p.relative_to(R))]=sha(p)
for name in [x.split('::')[0] for x in plan['tests']]+['06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py','06_TOOLS/EXPERIMENTS/adr_0892/test_focus.py','06_TOOLS/EXPERIMENTS/adr_0832/test_delivery.py','05_TESTS/conftest.py','06_TOOLS/EXPERIMENTS/resource_guard.py']:
 files[name]=sha(R/name)
put(D/'freeze.json',{**f,'files':files})
print('Frozen90 contracts, unchanged712 code files, current API team selector and navigation fixture.')
