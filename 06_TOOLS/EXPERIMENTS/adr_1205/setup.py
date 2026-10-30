"""Freeze the already tested need-continuity implementation; no product edits."""
from common import *
import shutil
T=Path(__file__).parent
tested=ROOT/'09_ARTIFACTS/AUDITS/20261029-need-continuity-implementation'
parent=read(tested/'fixed-code-v3-binding.json');C=tested/'fixed-code-v3'
assert all(sha(C/n)==h for n,h in parent['files'].items())
checks=read(tested/'fixed-contract-results.json')
assert checks['exit_code']==0 and checks['passed']==169 and not checks['import_leaks']
own=read(tested/'final-binding.json')['products']
assert all(sha(ROOT/n)==h==parent['files'][n] for n,h in own.items())
pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';a=read(pointer);assert a['generation']==117;r=read(ROOT/a['manifest_path'])
put(DES/'baseline.json',{'pointer':a,'pointer_sha256':sha(pointer),'release':r,
 'tested_code':str(C.relative_to(ROOT)), 'parent_checks':{'path':str((tested/'fixed-contract-results.json').relative_to(ROOT)),'sha256':sha(tested/'fixed-contract-results.json'),'passed':169},
 'working_files':{n:sha(ROOT/n) for n in parent['files']},'own_product_files':own,
 'working_vs_tested_differences':[n for n,h in parent['files'].items() if sha(ROOT/n)!=h]})
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1203-reference-purpose-live-cm009'
for n in ('cases.json','corpus.json','authorization.json'):put(DES/n,read(prior/'artifacts/design'/n))
put(ART/'evaluation-only/cases.json',read(prior/'artifacts/evaluation-only/cases.json'))
old=read(prior/'artifacts/design/criteria.json')
criteria={**old,'hypothesis':'A cumulative ID ledger preserves every declared need across investigation termination and final assessment, rejects unsupported resolution and requires the same conditional change_review in generation and validation, without server-chosen sibling references.',
 'success_criteria':['Actual CM009 once on exact tested471-file need-continuity candidate, unchanged65-document permission/model/physical40/tools1024/wall1800/percall180/no output cap',
 'Every accepted material_need persists by ID in final input and has one explicit evidence/claim-bound resolution, grounded exclusion, or material same-issue unresolved gap; no silent closure at FINISH or supervisor limit',
 'Conditional change_review is physically delivered as required in generation schema; normal ROLE_ONLY exclusions work; one existing repair only, and repeated errors remain rejected',
 'LLM chooses needed reference clauses/ranges; no automatic sibling reference goal is added; actual selected subranges require full acquired/delivered original spans',
 'Source bytes/ACL/physical budget/input and code integrity hold, no unknown transport or resource stop, MAIN117 unchanged',
 'Final stored and delivered answer preserves accepted content and correctly covers the frozen exemption question including necessary article31 ma/ba qualifications; root presence is insufficient'],
 'failure_criteria':'Any declared need lost, ungrounded closure, repeated output rejection, missing final answer, wrong/omitted material conditions, required subclause omission, integrity/ACL/budget breach, UNKNOWN/deadline/resource stop fails full case. Contract detection and limited answer are separately assessed; a controlled rejection is not a legal-answer pass.',
 'scope':'Exact previously unit/API-tested need-continuity snapshot; preserve concurrent ontology changes outside candidate; no new product edits, MAIN/GENOS promotion, advisory reviewer or stronger model comparison',
 'request':'실험해봐','allow_external':True,'order':['cm-009 once'],
 'comparability':'Known-case in-sample single run. Historical1203 is contextual baseline only; changed stochastic paths prevent causal speed/quality estimates.',
 'content_review':'Offline after product finishes against stored originals and evaluation-only reference. No gold or required reference targets injected into product input. Separate declared-need contract, missing undeclared references and legal meaning.'}
put(DES/'criteria.json',criteria)
put(DES/'user-authorization.json',{'request':'실험해봐','scope':'Actual CM009 once on latest tested need-continuity implementation, same authorized CM question and65-document source scope','session_id':'need-continuity-live-20261029'})
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Declared need identity continuity, final accounting, conditional review submission and actual CM009 answer correctness',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,execution=criteria,
 arms=[{'id':'bound','role':'candidate','derived_from':['ADR-1203-experiment-v1/bound'],'changes':'Seven need-continuity product files and pins from tested implementation; preserved existing storage reader dependencies; explicit model reference selection','controls':'Same data, ACL, model, nativeAPI, budgets and provider routing. Parallel ontology work excluded by tested immutable snapshot.'}])
m['runs'][0].update(arm_ids=['bound'],selection_rule='Latest user request to experiment on just-implemented need continuity; CM009 exactly once, no automatic retry',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='CM009 known-case need-continuity live probe',version='same authorized CM question as1203',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None,stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((RUN/'retrieval-ledger.json').relative_to(ROOT)),'sha256':'PENDING','not_applicable_reason':None})
m['design']['retrieval_stage_plan']['stages_by_arm']={'bound':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
c=read(DES/'cases.json')[0];q=m['questions'][0];p=ADR/'실험'/q['file']
texts=['run-001/bound/cm-009; 실행 전',c['request']['json']['question'],'평가 전용 artifacts/evaluation-only/cases.json. 제품 입력 금지.','[사전기준](../artifacts/design/criteria.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n관측후보→확보→최종 인용. 별도로 실제 필요 ID·참조 하위 원문을 대조한다.','실행 시 raw/call-*에 전체 요청·응답 저장. 아직 호출 없음.','실행 시 canonical/에 단계 입력·출력 저장. 아직 호출 없음.','평가 모델0. 종료 후 저장 원문으로만 검토.','실행 전; 기준 변경 없이 실패 보존.']
p.write_text('# cm-009\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p);put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=ac.snapshot(ADR,'bound',list(parent['files']),experiment_id=m['experiment_id'],arm_id='bound',run_ids=['run-001'])
for n in parent['files']:shutil.copyfile(C/n,S/'snapshot'/n)
ac.freeze(S);assert not ac.validate(S),ac.validate(S)
v=read(S/'candidate.json')['revisions'][-1]
binding={'manifest_path':str((S/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(S/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='bound',experiment_id=m['experiment_id'],arm_id='bound',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))]);put(ADR/'실험/manifest.json',m)
put(DES/'freeze-live.json',{'code_root':str((S/'revisions'/v['revision_id']/'snapshot').relative_to(ROOT)),'files':parent['files'],'candidate_revision':binding,'pointer_sha256':sha(pointer),'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json')},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')}})
print('Frozen tested need-continuity candidate',len(parent['files']),'files; CM009 once; MAIN117 unchanged')
