from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/active['manifest_path'])
assert active['generation']==118
prior=read(ROOT/'09_ARTIFACTS/AUDITS/20261029-rejected-need-preservation/fixed-binding.json')
files=set(prior['files'])|{'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json','00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'}
assert all((ROOT/n).is_file() for n in files)
core=['05_TESTS/CONTRACTS/'+n for n in ['test_need_observation.py','test_need_continuity.py','test_read_judgment.py','test_need_continuity_api.py']]+['06_TOOLS/EXPERIMENTS/adr_1199/test_supervisor.py','06_TOOLS/EXPERIMENTS/adr_1199/test_source_goals.py','06_TOOLS/EXPERIMENTS/adr_1188/test_requirements.py']
features=['05_TESTS/CONTRACTS/'+n for n in ['test_genos_journal_storage.py','test_domain_profile_workflow.py','test_domain_profile_native.py','test_domain_profile_ui.py','test_genos_source_accordion.py','test_workflow_answer_delivery.py','test_main_source_cards.py','test_output_contract_recovery.py','test_assessment_source_reply.py']]
regression=['05_TESTS/CONTRACTS/'+n for n in ['test_navigation_scope_memory.py','test_initial_interpreted_scope.py','test_investigation_completion_adr0678.py','test_unattempted_gap_finish.py','test_completion_v4.py','test_source_span_norm.py','test_narrative_answer.py','test_token_answer_stream.py','test_navigation_input_compaction.py','test_nested_minimal_output.py','test_single_rule_content.py','test_genos_native_chat_sse.py','test_genos_main_chat.py']]
criteria={'scope':'User-authorized technical qualification of completed working changes, plus read-only diagnosis of recorded wire size; no new model calls or legal scoring',
'success':['Complete frozen serving inventory matches official prepare and working integration','All feature contracts pass on the frozen candidate','Shared regression has no newly failing tests against exact MAIN118','Candidate and selected native service HEALTH plus synthetic HTTP and module/pin/data binding pass','Need continuity, denied action isolation, exact sources/ACL/state/accepted answer, storage corruption/quota/legacy reads and domain approval boundaries preserved','Existing source accordion preserved','No legal gold or saved CM cases used to claim quality eligibility'],
'failure':'New product regression, altered source/ACL, unknown-byte mismatch, import leak, stale MAIN or incomplete official inventory blocks activation',
'suites':{'core':core,'features':features,'regression':regression},'fixture_hashes':{p:sha(ROOT/p) for p in set(core+features+regression)},
'exclusions':{'actual007':'Previously excluded live-fixture test; saved failure is a diagnostic only','ADR1201 advisory reviewer':'Rejected effect, not adopted in working product','ADR1207 portable_transport':'Unexecuted research transport, not completed working implementation'},
'packaging_changes':['Include both inactive domain/business profile templates by explicit engine pins; no activation/approval implied'],
'rollback':'Before any new compressed records official pointer rollback to MAIN118; after compact writes keep compatible readers and disable new compact writes with GENOS_JOURNAL_STORAGE=plain. Never strip new readers from compact journals.',
'external_model_calls':0,'quality_certified':False,'resource_limit_GiB':6,'heavy_processes':1}
put(DES/'criteria.json',criteria);put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(ROOT/n) for n in sorted(files)}})
m=read(ADR/'실험/manifest.json');refs=m['integration']['parent_refs']
m['integration'].update(result_arm='integrated',rationale='Explicit user request to activate all completed working features together; evaluate technical boundaries without adopting failed legal outcomes.',common_invariants='Current data/model/40/1024/1800 limits/ontology default OFF and original evidence/ACL/state/accepted-content contracts unchanged.',parent_contributions=[{'parent_ref':ref,'adopted':text,'excluded':excluded} for ref,text,excluded in zip(refs,['MAIN118 full baseline and source accordion','Independent supervisor route recovery within existing budget','Purpose change review and exact gap linkage'],['No exclusions from selected MAIN118','No prior CM007 quality claims','Automatic sibling reference expansion removed by later user-directed LLM selection contract'])],conflicts=[{'id':'reference-autofill','parents':[refs[2]],'resolution':'Later explicit user requirement and tested working need-continuity code retain LLM choice; server sibling expansion call is absent.','evidence':'09_ARTIFACTS/AUDITS/20261029-need-continuity-implementation/구현과_검증결과.txt'}],no_conflict_reason=None)
h='Completed working storage, supervisor, declared-need and domain-profile contracts can share one pinned MAIN release without new regression; recorded prompt growth is measured without changing input semantics.'
m['lineage']['hypothesis_delta']=h
m['design'].update(hypothesis=h,primary_metric='Technical release/consumer contract integrity; no legal quality or runtime speed metric',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':refs,'changes':'Exact selected MAIN118 used as operational comparison; lineage merge references describe integrated contributions','controls':'Current data/model unchanged'}, {'id':'integrated','role':'candidate','derived_from':['baseline'],'changes':'All completed working serving changes plus inactive template packaging','controls':'Same data/model/budgets and ontology default OFF'}])
m['dataset'].update(name='Prospectively fixed technical release and shared regression suite',version='v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[];m['runs'][0].update(arm_ids=['baseline','integrated'],selection_rule='Complete predeclared technical suite; prior known actual model cases excluded from quality/eligibility',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting']['not_applicable_reason']='No new legal retrieval evaluation; synthetic contracts and historical read-only input size audit.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No changed retrieval experiment or golden recall claim.'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'integrated',sorted(files),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
# Only packaging differs from the already implemented working code.
templates=['00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json','00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json']
changes={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p)
 if '00_SYSTEM/SCHEMAS/ontology-domain-profile-v1.schema.json' not in d.get('files',{}):continue
 old=sha(p)
 for n in templates:d['files'][n]=sha(S/n)
 put(p,d);changes[old]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';text=p.read_text()
for old,new in changes.items():text=text.replace(old,new)
p.write_text(text)
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');rev=c['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
fs={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in rev['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':fs,'candidate_revision':binding,'working_changes':[n for n,h in fs.items() if sha(ROOT/n)!=h]})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print({'frozen_files':len(fs),'MAIN_changes':sum(base['files'].get(n)!=h for n,h in fs.items()),'packaging_only_pin_files':len(changes)+1})
