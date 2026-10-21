"""Freeze eight unseen cases and exact current/pre-feature code before model calls."""
from common import *
import sys,copy,gzip,shutil
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation']==97
base=read(ROOT/pointer['manifest_path'])
prior=ROOT/'09_ARTIFACTS/AUDITS/20261021-law-name-recovery'
assert all(sha(ROOT/p)==h for p,h in read(prior/'binding-check.json')['changed_files'].items())
paths=set(base['files'])|{'02_BACKEND/semantic_runtime/legal_agent/law_name_recovery.py'}
changed=sorted(p for p in paths if base['files'].get(p)!=sha(ROOT/p))
for arm in ('baseline','candidate'):
    dest=ART/('code-'+arm);dest.mkdir(exist_ok=False)
    for p in sorted(paths):
        target=dest/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,target)
    if arm=='baseline':
        for p,h in read(prior/'before.json').items():
            if p in paths:(dest/p).write_bytes(gzip.decompress((prior/(h+'.gz')).read_bytes()))
roots={arm:str((ART/('code-'+arm)).relative_to(ROOT)) for arm in ('baseline','candidate')}
files={arm:{p:sha(ROOT/roots[arm]/p) for p in sorted(paths)} for arm in roots}
save(ART/'stage.json',{'base_pointer':pointer,'roots':roots,'files':files,'working_baseline':files['candidate']})
save(ART/'integration-delta.json',{'against_main97':changed,'paired_difference':[p for p in sorted(paths) if files['baseline'][p]!=files['candidate'][p]],'preexisting_changes':'Text length constraints removed in working code before this feature. Preserved identically in both arms, separately covered by text-length and consumer contracts. No source overwrite or model/profile/data change.'})
titles=['전자기록 보존규정','전자기록 폐기규정','방문자 출입관리규정','임시직원 출입관리규정','연구장비 대여규정','연구시설 대관규정','문서전송 점검규정','개인장비 반출규정']
special={('D01',2):'전자기록 보존기간은 작성일부터 삼 년이다.',('D02',2):'전자기록 폐기에는 기록관리자의 사전 승인이 필요하다.',('D03',3):'방문자는 퇴실할 때 방문증을 안내 창구에 반납한다.',('D04',3):'임시직원은 계약 종료 시 출입증을 인사 담당자에게 반납한다.',('D05',4):'연구장비 대여 신청서는 사용 전날 장비 담당자에게 제출한다.',('D06',4):'연구시설 대관 신청서는 사용 일주일 전 시설 담당자에게 제출한다.',('D07',2):'문서전송 담당자는 발송 전에 수신 주소와 첨부파일을 확인한다.',('D08',2):'개인장비는 반출대장에 일련번호를 기록한 뒤 반출한다.'}
docs=[]
for i,title in enumerate(titles,1):
    did=f'D{i:02d}'
    docs.append({'id':did,'title':title,'texts':[f'제{n}조 '+special.get((did,n),title+'의 담당자는 업무 처리 기록을 남긴다.') for n in range(1,5)]})
scope=[d['id'] for d in docs]
specs=[('전자기록 보관규정 제2조','D01','제2조'),('방문자 출입관리지침 제3조','D03','제3조'),('연구장비 대출규정 제4조','D05','제4조'),('문서 전송 점검요령 제2조','D07','제2조'),('전자기록 보존규정 제2조','D01','제2조'),('연구장비 대여규정 제4조','D05','제4조'),('연구장비 대여규칙 제99조',None,None),('방문자 출입관리지침 제3조',None,None)]
cases=[];gold=[]
for i,(lookup,did,node) in enumerate(specs,1):
    ident=f'name-{i:02d}';allowed=['D01'] if i==8 else scope
    cases.append({'id':ident,'lookup':lookup,'question':lookup+'의 원문을 찾아 그대로 보여 주세요.','scope':allowed})
    gold.append({'case_id':ident,'expected':[] if did is None else [{'doc_id':did,'node':node}],
        'kind':'name_recovery' if i<=4 else 'exact_control' if i<=6 else 'missing_coordinate' if i==7 else 'scope_boundary'})
save(ART/'documents.json',docs);save(ART/'cases.json',cases);save(ART/'grading-only.json',gold)
m=read(ADR/'실험/manifest.json');m['decision_eligible']=True
m['lineage']['hypothesis_delta']='Add model-selected title-only recovery after a failed name/article lookup, preserving the original coordinate and read-before-adopt boundary.'
m['design'].update(hypothesis='The explicit candidate-selection tool restores at least three of four novel name variants while preserving exact lookup and authority boundaries.',
 primary_metric='Correct original-coordinate source delivery and actual RETRY_LAW_STRUCTURE use; engineering qualification, not legal-answer accuracy.',
 success_criteria='Candidate correct source delivery or correct abstention >=6/8 and >=baseline; >=3/4 name variants use RETRY_LAW_STRUCTURE and deliver the expected article; both exact controls pass; both no-source controls deliver no sources; no source/hash/ACL/state violation; all applicable frozen contracts pass, only seven pre-recorded failures may remain. Same staged/working/selected hashes and native service check required.',
 failure_criteria='Wrong-scope/source/hash/state acceptance, changed original coordinate, new contract failures, model budget exceeded, candidate below the frozen thresholds or selected-code mismatch prevents promotion. Uncertainty and individual semantic misses stay visible.',
 criteria_frozen_before_run=True,
 budget={'physical_calls_per_trial':8,'total_physical_calls':128,'trial_seconds':300,'experiment_seconds':2400,'address_space_bytes':6*1024**3,'minimum_available_ram_bytes':4*1024**3,'parallel_heavy_processes':1},
 sampling='Eight new synthetic cases authored after implementation without viewing candidate results; no reuse of previous unit-test questions. Fixed suffix/semantic-name variations, exact controls, missing article and scope-negative cases. One run; no adaptive retry.',
 exposure='Developer authored tests are independent from development fixtures, not statistically independent user traffic. No legal quality certification.',
 call_order='Odd cases baseline then candidate; even cases candidate then baseline. Same corpus/profile/deadline/call budget.',
 preexisting_work='Paired baseline is current pre-feature working code, not byte-identical MAIN97. Text-length removal is fixed in both arms. Parent MAIN97 is separately preserved as rollback and actual data/model binding.')
m['design']['arms'][0].update(changes='MAIN97 lineage plus pre-existing text-length removal; prior audit restores exact bytes from before the law-name feature.',controls='Same synthetic data, profile, model, bounded runtime, original-coordinate task; no title-recovery tool.')
m['design']['arms'][1].update(changes='Previously implemented law-name recovery and registered RETRY_LAW_STRUCTURE, otherwise exact paired baseline.',controls='No further product edits after dataset freeze; candidate selected only by explicit research runner.')
stages=[{'stage_id':'corpus','kind':'source','parent_stage_ids':[]},{'stage_id':'initial','kind':'filter','parent_stage_ids':['corpus']},{'stage_id':'investigated','kind':'expand','parent_stage_ids':['initial']},{'stage_id':'read','kind':'select','parent_stage_ids':['investigated']},{'stage_id':'present','kind':'present','parent_stage_ids':['read']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={arm:copy.deepcopy(stages) for arm in roots}
m['llm_policy']['llm_calls']=[{'role':'source-navigation','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['dataset']={'name':'Eight unseen synthetic name/article lookup tasks','version':'name-recovery-holdout-v1','frozen_source':str((ART/'cases.json').relative_to(ROOT)),'sha256':sha(ART/'cases.json'),'legal_version_checked':True,'reference_version_checked':True,'version_scope':'Synthetic frozen document corpus; no real-law version or legal interpretation claim','documents':{'path':str((ART/'documents.json').relative_to(ROOT)),'sha256':sha(ART/'documents.json')},'grading_only':{'path':str((ART/'grading-only.json').relative_to(ROOT)),'sha256':sha(ART/'grading-only.json')}}
m['runs'][0].update(selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=True,corpus_total=32,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
runner=ROOT/'06_TOOLS/EXPERIMENTS/adr_0965/run_case.py'
isolation=m['design']['code_isolation'];isolation.update(mode='candidate_snapshot',reason=None,candidates=[])
save(ADR/'실험/manifest.json',m)
for arm in ('candidate',):
    croot=ac.snapshot(ADR,arm,changed,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
    for p in changed:shutil.copyfile(ROOT/roots[arm]/p,croot/'snapshot'/p)
    ac.freeze(croot)
    assert not ac.validate(croot)
    candidate=read(croot/'candidate.json');rev=candidate['revisions'][-1]
    isolation['candidates'].append({'candidate_id':arm,'arm_id':arm,'experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((croot/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(croot/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)})
m['design']['script_bindings']={str(p.relative_to(ROOT)):sha(p) for p in runner.parent.glob('*.py')}
tests=['test_law_name_recovery','test_followup_structure_lookup','test_law_grouped_navigation','test_tool_availability','test_navigation_input_compaction','test_multiturn_structured_scope','test_scoped_multiturn_api','test_main50_request_repair','test_text_length_unlimited','test_unattempted_gap_finish','test_assessment_source_reply','test_investigation_completion_contract','test_public_display_boundary']
m['design']['test_bindings']={f'05_TESTS/CONTRACTS/{name}.py':sha(ROOT/f'05_TESTS/CONTRACTS/{name}.py') for name in tests if (ROOT/f'05_TESTS/CONTRACTS/{name}.py').is_file()}
m['design']['allowed_existing_failures']=read(prior/'test-summary.json')['unchanged_failure_names']
save(ADR/'실험/manifest.json',m)
save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'dataset':m['dataset'],'stage_sha256':sha(ART/'stage.json'),'prior_feature_audit':str(prior.relative_to(ROOT))})
print('Frozen',len(paths),'serving files,',len(changed),'changed from MAIN97; eight cases; no calls yet')
