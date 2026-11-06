from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
def evidence(number):return next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{number}-*/artifacts'))
DES.mkdir(exist_ok=False)
prior=evidence(1374);seed=evidence(1373)/'sandbox-repository';paired=evidence(1383)
for n in ('baseline','source-scope','provider-policy','authorization'):
    put(DES/(n+'.json'),read(paired/'design'/(n+'.json')))
for n in ('followups','parent-knowledge'):put(DES/(n+'.json'),read(prior/'design'/(n+'.json')))
b=read(DES/'baseline.json');r=b['release'];assert b['pointer']==read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
published=read(evidence(1373)/'publication-verified.json')
put(DES/'seed.json',{'root':str(seed.relative_to(ROOT)),'files':{str(p.relative_to(seed)):sha(p) for p in seed.rglob('*') if p.is_file()},'approved':{k:published[k] for k in ('publication_id','revision','bundle_id','active','work_hash')}})
for dest in ('sandbox-repository','preflight-repository'):shutil.copytree(seed,ART/dest)
shutil.copytree(prior/'transport',ART/'transport')
criteria={'hypothesis':'A fresh MAIN145 Qwen examination of a contradictory legal judgment may preserve the independent reference and flag the erroneous application while retaining the active package.',
'success':['Append a draft to existing revision 2, preserve its graph, source records and active publication','Source-backed contradiction for the incorrect application and no unsupported new rule. Separate whether the optional independent NEW branch really occurred.'],
'failure':['Never approve the new judgment. Preserve physical unknowns, four bounded supplements maximum per authoring stage, no further sends on UNKNOWN in either experiment.'],
'limits':{'max_physical':11,'stages':['NORMALIZE','COMPARE_JUDGMENT'],'scope':'public Commercial Act only / isolated repository'}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Conflict review and source-bound history on selected code with preserved active revision',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for arm in m['design']['arms']:arm.update(changes='Completed integrated release' if arm['id']=='baseline' else 'New Qwen proposals on the exact same selected code and archived original judgment',controls='Same archive, source, quoted spans, DB seed and unchanged validation')
m['dataset'].update(name='One archived misleading interpretation of the charter quorum',version='live-selected145',frozen_source=str((DES/'followups.json').relative_to(ROOT)),sha256=sha(DES/'followups.json'))
m['runs'][0].update(arm_ids=['selected'],selection_rule='One fresh conflict comparison after six usage cells. Stop on either unknown physical outcome.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for x in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):x['not_applicable_reason']='Fixed original judgments and exact statutory evidence; no RAG selection.'
can=ac.snapshot(ADR,'selected',list(r['files']),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
for n,h in r['files'].items():
    assert sha(selected()/n)==h
    shutil.copyfile(selected()/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can)
rev=read(can/'candidate.json')['revisions'][-1]
assert all(sha(can/'revisions'/rev['revision_id']/'snapshot'/n)==h for n,h in r['files'].items())
pin={'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'candidate.json',dict(code_root=r['code_root'],selected_files=r['files'],pin=pin))
runner=Path(__file__).with_name('compare.py')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))])
put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*DES.glob('*.json'),*(p for p in (ART/'transport').rglob('*') if p.is_file()),*(p for p in seed.rglob('*') if p.is_file())]
put(DES/'freeze.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths}})
print('Bound the revision2 seed, original archived judgments and MAIN145; no physical calls.')
