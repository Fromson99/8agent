from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0937-research-continuity';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
D.mkdir(exist_ok=True)
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path'])
names=list(release['files']);before={n:sha(R/n) for n in names}
put(D/'baseline.json',{'pointer':pointer,'manifest':release,'working_files':before,
    'working_drift':[n for n in names if before[n]!=release['files'][n]]})
criteria={
 'hypothesis':'Connect parent issue/field/side research needs to immutable child acquisition attempts and their evidence outcomes. Separate discovery from original-source progress; preserve retries and budget across continuation. Do not infer legal equivalence or suppress uncertainty.',
 'success':[
 'New candidates/definitions/locations and wording changes alone do not reset original-source stagnation; verified new intervals do, duplicate/subset intervals do not.',
 'Parent tasks retain stable issue/field/side need identity, purpose, exact operation and returned evidence/failed receipts across JSON restart.',
 'A changed missing explanation cannot automatically schedule the same exhausted fallback route on unchanged cited evidence; explicit alternate routes and genuinely new evidence remain usable.',
 'Exact acquisitions reuse physical document/unit/source identity across display/lead/evidence labels, while side/binding/ref/operation and search text differences remain distinct.',
 'Scoped continuity reaches actual child model input and returns its progress; opposite-side/stale binding/malformed payload is rejected.',
 'No reset of parent/child budgets or deadlines, no extra retry layer; failures never prove absence; uncertainty preserves read originals and final partial response.',
 'Existing API/store/duplicate request/source scope/hash behavior and prior latest fixes remain connected with matching code pins.'
 ],
 'failure':['Any source/ACL/hash/state/budget regression','Unexplained loss of acquired originals','Resource guard stop'],
 'failure_owner':'Existing native loop owns stagnation recovery (one durable decision); parent owns additional research (existing max_recoveries=2). New state assembly is deterministic and introduces no model call, repair owner or legal acceptance gate.',
 'scope':'Technical contracts and scripted API only; no real legal answer, recall or speed comparison. Known defects are probe, no MAIN activation.',
 'limits':{'workers':1,'rss_gib':4,'min_available_gib':4,'min_disk_gib':10,'new_model_calls':0},
 'cases':['discovery-only','source-growth','subset-overlap','paraphrase-no-reset','new-target','new-cited-basis','exact-reuse','different-side','changed-binding','failure','budget','resume','api-child-context','partial-publication','duplicate-request']}
put(D/'criteria.json',criteria);put(D/'serving-files.json',names)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Durable research and source-progress invariants',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'connected','role':'candidate','derived_from':['ADR-0936-experiment-v1/fixed'],'changes':criteria['hypothesis'],'controls':'MAIN90 working sources, existing original-data/model policies; scripted technical verification only.'}]
m['runs'][0].update(arm_ids=['connected'],selection_rule='All predeclared technical boundaries plus existing affected contract suites, one process sequentially',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='research-continuity-technical-contracts',version='20261020-r1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=False,reference_version_checked=False)
why='Technical state and consumer verification with synthetic originals; no measured legal retrieval comparison.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=why);m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=why)
put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in names:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
print('Criteria fixed, MAIN90 baseline recorded; 387 serving sources isolated without copying data.')
