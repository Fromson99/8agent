from common import *
import shutil
DES.mkdir(exist_ok=False)
audit=ROOT/'09_ARTIFACTS/AUDITS/20261104-genos-gold-mapping'
f=read(audit/'candidate-manifest.json');C=ROOT/f['code_root']
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==140
assert all(sha(C/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==f['files'][n] for n in f['product_changes'])
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
put(DES/'baseline.json',{'pointer':active,'release':release,
    'working_files':{n:sha(ROOT/n) for n in f['files']},
    'gold_binding':read(gold/'binding.json'),
    'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.py','.json','.yaml')},
    'prior_validation':{'path':str((audit/'final-validation.json').relative_to(ROOT)),'sha256':sha(audit/'final-validation.json')},
    'product_changes':f['product_changes']})
criteria={'authorization_text':'지금 메인에 반영해봐',
 'scope':'Previously completed MAIN140-based Gold B003 R5 change only; no additional product changes',
 'required':['Prepared528 files exactly match previously validated Gold candidate',
 'Gold contract30, startup6 and actual disposable Oracle API1 pass on prepared release',
 'Native639 plans keep identical executable SQL/list/AST; engine30/500 pass',
 'Official prepare/apply selects MAIN141 and previous MAIN140 is rollback-ready',
 'Fresh actual root service selects the exact release and original source generation with HEALTH200',
 'Maintained Gold connector imports same MAIN141 with unchanged mapping/publication/data',
 'Working code including concurrent multiturn changes remains byte-identical to admission'],
 'failure':'No apply on code/data/ACL/state/binding mismatch. Preserve failure; rollback on selected service failure.',
 'limits':['No model calls','No field GENOS deployment','No new legal quality or speed claim'],
 'resources':{'startup_available_GiB':5,'minimum_available_GiB':3,'max_worker_RSS_GiB':4,'max_swap_growth_MiB':128,'minimum_free_disk_GiB':20}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']='Explicitly select already validated Gold mapping support in local MAIN without importing unrelated working changes'
m['design'].update(hypothesis='The verified Gold candidate remains identical through official release preparation and actual MAIN selection',primary_metric='Exact release/data/consumer binding and scoped technical contract pass',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:
 arm.update(changes='Selected MAIN140 reference; no re-evaluation' if arm['id']=='baseline' else 'Existing Gold B003 R5 delta39 only',controls='Original data/generation/model/provider/source authority, existing SIDDA records and S_1 option unchanged')
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Frozen Gold mapping and MAIN selection technical contracts',version='20261104-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(selection_rule='Predeclared contracts and actual prepared/selected entrypoint checks; baseline inventory only',artifact_path=str((ART/'result.json').relative_to(ROOT)))
reason='Release selection audit of already tested mapping; no retrieval quality evaluation or new retrieval policy'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',list(f['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
for n in f['files']:shutil.copyfile(C/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(C/n)==h for n,h in f['files'].items())
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':f['files'],'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-integrated.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1334/run.py',runner_sha256=sha(Path(__file__).with_name('run.py')))])
put(ADR/'실험/manifest.json',m)
print('Frozen528 files; original Gold candidate exact; working code unchanged')
