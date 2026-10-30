from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/active['manifest_path'])
assert active['generation']==117 and active['release_id']=='accepted-answer-20261029-r1'
old=read(ROOT/'09_ARTIFACTS/AUDITS/20261029-genos-source-accordion/validation.json')
assert sha(ROOT/PRODUCT)==old['after_sha256'] and base['files'][PRODUCT]==old['before_sha256']
suites={'source':['05_TESTS/CONTRACTS/test_genos_source_accordion.py','05_TESTS/CONTRACTS/test_workflow_answer_delivery.py','05_TESTS/CONTRACTS/test_main_source_cards.py','05_TESTS/CONTRACTS/test_source_tiers_v4.py::test_T08_renderer_keeps_untrusted_markdown_literal'],
'regression':['05_TESTS/CONTRACTS/test_genos_native_chat_sse.py','05_TESTS/CONTRACTS/test_genos_main_chat.py']}
criteria={'scope':'Technical qualification of existing requested UI on exact MAIN117, no legal/model/performance experiment',
'success':['Only the source renderer changes among the complete serving inventory','Frozen candidate and working source suite pass','Unchanged shared regressions have identical outcomes in MAIN117 and candidate, no newly failing test','Response originals, blank lines, versions, read scopes, failures and request reuse remain bound','Official preview/rebase equals tested inventory','Native selected service HEALTH plus exact bound renderer and JSON/SSE publication checked','GENOS delivery bytes match selected MAIN and can be verified/applied/rolled back locally'],
'failure':'Any new source/permission/state failure, inventory drift, import leak or rebase mismatch prevents activation',
'suites':suites,'fixture_hashes':{p.split('::')[0]:sha(ROOT/p.split('::')[0]) for suite in suites.values() for p in suite},
'external_model_calls':0,'quality_certified':False,'prior_UI_unit_checks':bind(ROOT/'09_ARTIFACTS/AUDITS/20261029-genos-source-accordion/validation.json'),
'prior_UI_evidence_scope':'Known earlier unit/browser checks are diagnostic; release qualification uses the complete frozen code and fixed technical suite, not legal out-of-sample quality.',
'resources':{'parallel_heavy_processes':1,'min_available_GiB':5,'address_space_GiB':6}}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(ROOT/n) for n in base['files']}})
m=read(ADR/'실험/manifest.json');hyp='A two-level source disclosure reaches selected MAIN and GENOS transport without modifying the accepted answer, source selection or model behavior.'
m['lineage']['hypothesis_delta']=hyp
m['design'].update(hypothesis=hyp,primary_metric='Complete release/source publication contract integrity; no law-quality metric',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,
arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1197-experiment-v1/verified'],'changes':'None; exact selected MAIN117','controls':'Same data, model, budgets and answer/source generation'}, {'id':'integrated','role':'candidate','derived_from':['baseline'],'changes':'Existing source accordion renderer only','controls':'All other MAIN117 serving files byte-identical'}])
m['dataset'].update(name='Fixed technical source renderer and shared native transport suite',version='v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['runs'][0].update(arm_ids=['baseline','integrated'],selection_rule='Complete prospectively fixed source/native compatibility suite on exact frozen inventory; no sample selection or legal scoring',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting']['not_applicable_reason']='Display-only release qualification; retrieval unchanged'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No retrieval experiment or legal answer benchmark'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'integrated',list(base['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n,h in base['files'].items():
 assert sha(ROOT/base['code_root']/n)==h,n
 shutil.copyfile(ROOT/base['code_root']/n,S/n)
shutil.copyfile(ROOT/PRODUCT,S/PRODUCT)
changed=[n for n,h in base['files'].items() if sha(S/n)!=h];assert changed==[PRODUCT]
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');rev=c['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
files={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in rev['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':files,'candidate_revision':binding})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print(json.dumps({'frozen_files':len(files),'changed':changed,'code_root':str(code.relative_to(ROOT))}))
