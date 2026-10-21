from pathlib import Path
import hashlib,json,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0926-connected-source-release-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0925-source-lead-exact-observation';Q=R/'04_EXPERIMENTS/ADR/ADR-0924-source-lead-parent-handoff';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
b=read(P/'artifacts/design/observed-binding.json');base=read(P/'artifacts/design/baseline.json');C=R/b['code_root']
assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
put(D/'binding.json',b);put(D/'baseline.json',base)
c={'hypothesis':'Unchanged completed source-lead candidate preserves current source/side/committed-state boundaries, bounded projections and exact actual release closure.',
 'required':['Eight independently defined finite source/side/stale-state/capacity cases pass','154 parent technical passes retain exact product binding; inherited failures remain disclosed','Actual packager inventory equals full declared serving closure','Candidate and selectively integrated working service ingress and source read pass','No product change after live observation; current MAIN88 remains rollback base'],
 'legal_holdout':False,'model_calls':0,'failure':'Any new source/ACL/hash/state/consumer regression or undeclared serving dependency prevents activation.',
 'promotion_scope':'Finite software qualification only. Known legal question remains in-sample and has semantic errors; not a legal accuracy certification.'}
put(D/'criteria.json',c)
cm=read(R/b['candidate']['manifest_path']);names={r['target_path'] for r in cm['files']}
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':b['candidate'],'staged_files':b['serving_files'],'excluded_candidate_paths':{n:'Build/test/research file; immutable candidate retains it outside serving closure.' for n in sorted(names-set(b['serving_files']))},'evaluation':'Exact completed ADR0925 product, ADR0924 technical checks and independent finite boundary/packager/service verification. Known legal errors retained.'};put(D/'release-rebase.json',rebase)
rb={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')}
before=base['manifest']['files']
changes=[{'path':n,'before':before.get(n),'after':b['serving_files'].get(n),'reason':'Exact tested development rebase plus connected source selection, document terms and separate child-to-parent leads; explicit engine/profile pins.'} for n in sorted(set(before)|set(b['serving_files'])) if before.get(n)!=b['serving_files'].get(n)]
put(D/'integration.json',{'schema_version':'local-release-integration-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'changes':changes,'candidate':b['candidate'],'rebase_receipt':rb})
old=read(Q/'artifacts/design/working-before.json');delta=[{'path':n,'before':old.get(n),'after':h} for n,h in b['serving_files'].items() if old.get(n)!=h]
put(D/'working-deltas.json',delta)
drift={n:{'before':old.get(n),'current':sha(R/n),'candidate':h} for n,h in b['serving_files'].items() if n in old and sha(R/n)!=old[n]}
assert not ({r['path'] for r in delta}&set(drift)),drift
put(D/'concurrent-working-only.json',{'preserved':drift,'policy':'Do not overwrite concurrent files. Qualified release is exact frozen candidate; working-only differences are explicitly separate.'})
tests={'new_finite_cases':8,'retained_passes':154,'tests':[str((T/'test_boundaries.py').relative_to(R))],'parent_test_disposition':{'path':str((Q/'artifacts/checks/test-disposition.json').relative_to(R)),'sha256':sha(Q/'artifacts/checks/test-disposition.json')}};put(D/'qualification-tests.json',tests)
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=c['hypothesis']
m['design'].update(hypothesis=c['hypothesis'],primary_metric='Finite source/side/state/capacity boundaries and exact release closure',success_criteria=c['required'],failure_criteria=[c['failure']],criteria_frozen_before_run=True,release_rebase=rb)
m['design']['arms']=[{'id':'qualified','role':'candidate','derived_from':['ADR-0925-experiment-v1/observed'],'changes':'No product change; independent finite software qualification','controls':'Exact completed bridged rev005 and MAIN88 data; known legal observation is not holdout.'}]
m['design']['code_isolation'].update(mode='not_applicable',reason='Reuse immutable completed candidate; no product modifications.',candidates=[])
m['runs'][0].update(arm_ids=['qualified'],selection_rule='Eight finite software boundaries, retained parent checks, actual packager and service binding. No legal holdout.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='connected-source-finite-boundaries',version='20261019-r1',frozen_source=str((D/'qualification-tests.json').relative_to(R)),sha256=sha(D/'qualification-tests.json'));m['llm_policy']['llm_calls']=[]
why='Finite software qualification; no new model/retrieval comparison. Known parent retrieval ledger unchanged.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
put(D/'preview-authorization.json',{'purpose':'integration_preview'});put(D/'preview-validation.json',{'structural_checks_passed':True,'source':str((P/'artifacts/run-001/result.json').relative_to(R))})
files={str((C/n).relative_to(R)):sha(C/n) for n in names}
extra=[*D.glob('*.json'),*T.glob('*.py'),P/'실험/manifest.json',P/'artifacts/run-001/result.json',Q/'artifacts/checks/test-disposition.json',R/'06_TOOLS/EXPERIMENTS/adr_0924/test_leads.py',R/'06_TOOLS/EXPERIMENTS/adr_0922/test_connected_exploration.py',R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py',R/'06_TOOLS/EXPERIMENTS/resource_guard.py']
for p in extra:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'code_root':b['code_root'],'candidate':b['candidate'],'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'legal_holdout':False})
print(json.dumps({'serving_files':len(b['serving_files']),'working_deltas':len(delta),'preserved_concurrent_files':list(drift)},ensure_ascii=False))
