from common import *
import shutil,os,ast
T=Path(__file__).parent
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1191-main115-parasail-cm007'
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1192-final-answer-scope-prompt'
f=read(parent/'artifacts/design/freeze-rev-001.json');C=ROOT/f['code_root']
a=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert a['generation']==115
r=read(ROOT/a['manifest_path']);assert all(sha(C/n)==h for n,h in f['files'].items())
assert read(parent/'artifacts/run-001/result.json')['unique_contracts_passed']==75
put(DES/'baseline.json',{'pointer':a,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':r,
 'prompt_candidate':f,'parent_contract_result_sha256':sha(parent/'artifacts/run-001/result.json')})
for n in ('cases.json','corpus.json','authorization.json'):put(DES/n,read(P/'artifacts/design'/n))
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
for p in (P/'artifacts/evaluation-only').glob('*.json'):put(ART/'evaluation-only'/p.name,read(p))
criteria=read(P/'artifacts/design/criteria.json')
criteria.update(hypothesis='ADR1192 final scope prompts preserve material conditions in the CM007 final answer; full existing integrity/content/storage gates still decide conditional CM009.',
 scope='Exact frozen ADR1192 scoped rev-001 code through isolated native API and serving transport; active MAIN115 unchanged. No product changes, no automatic repeated case, no stronger model comparison.',
 request='실험한번해봐',
 content_review='Offline agent after product finishes: review quantity basis including territorial/time scope, caps and holding period, actor/types, exceptions/delegated detail. Separate model claim content from server limitation footer; full pass still requires both, as ADR1191. No gold in product/correction input.',
 prompt_success_observation='Both markets relevant quantity, cap, duration and scope in actual claims; distinguish previous domestic/post-application denominator omission from missing originals. No keyword-only semantic pass.',
 comparison_limit='Known single case with new retrieval trajectory and provider conditions; not a controlled A/B or quality certification.')
criteria['success_criteria'][1]='All spans and ACL exact; physical requests equal budget; no output cap; frozen466 files exactly match ADR1192 and active MAIN115 pointer remains unchanged'
put(DES/'criteria.json',criteria)
put(DES/'user-authorization.json',{'request':'실험한번해봐','scope':'Test the modified final prompts: CM007 once, CM009 only after all CM007 gates pass',
 'session':os.environ.get('CODEX_THREAD_ID'),'active_main_changed':False})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='CM007 scoped final content with integrity and completion; conditional CM009',
 success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,execution=criteria,
 arms=[{'id':'scoped','role':'candidate','derived_from':['ADR-1192-experiment-v1/scoped'],
 'changes':'None from completed ADR1192 scoped rev-001; two prompt constants compared with active MAIN115',
 'controls':'Same questions/data/65-document ACL/model/routing/budgets/resource guard; no runtime logic change'}])
m['runs'][0].update(arm_ids=['scoped'],selection_rule='CM007 once; CM009 only on full first-case pass; no same-case repeat',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='CM007 and conditional CM009',version='same stored CM source as ADR1191',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='No retrieval implementation change; actual read and final citation sets measured',stage_ledger={
 'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001',
 'artifact_path':str((RUN/'retrieval-ledger.json').relative_to(ROOT)),'sha256':'PENDING','not_applicable_reason':None})
m['design']['retrieval_stage_plan']['stages_by_arm']={'scoped':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
cases={c['id']:c for c in read(DES/'cases.json')}
m['questions']=[]
for i,cid in enumerate(('cm-007','cm-009'),1):
 name=f'질문-{i:03}-{cid}.md';p=ADR/'실험'/name
 texts=['run-001/scoped; 실행 전',cases[cid]['request']['json']['question'],'평가 전용 artifacts/evaluation-only/cases.json. 제품 입력 금지.',
 '[동결](../artifacts/design/criteria.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n관측후보→확보→인용을 실행 후 전용 원장에 저장한다.',
 '실행 시 raw/call-*에 실제 요청·응답 저장. 아직 호출 없음.','실행 시 canonical/에 단계 입력·출력 저장. 아직 호출 없음.','모델 채점0. 종료 후 오프라인 검토.','실행 전. 사전 기준 그대로 판단.']
 p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {j}. {h}\n\n{v}' for j,(h,v) in enumerate(zip(heads,texts),1))+'\n')
 m['questions'].append({'number':i,'case_id':cid,'file':name,'sha256':sha(p)})
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
snapshot=ac.snapshot(ADR,'scoped',list(f['files']),experiment_id=m['experiment_id'],arm_id='scoped',run_ids=['run-001'])
for n,h in f['files'].items():shutil.copyfile(C/n,snapshot/'snapshot'/n)
ac.freeze(snapshot);assert not ac.validate(snapshot),ac.validate(snapshot)
c=read(snapshot/'candidate.json');v=c['revisions'][-1];code=snapshot/'revisions'/v['revision_id']/'snapshot'
assert all(sha(code/n)==h for n,h in f['files'].items())
b={'manifest_path':str((snapshot/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(snapshot/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(b,candidate_id='scoped',experiment_id=m['experiment_id'],arm_id='scoped',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))])
m['design']['execution_note']='Explicit frozen candidate import and native API injection; no active release switch. Same466 hashes as ADR1192 tested code; existing75 contract checks inherited.'
put(ADR/'실험/manifest.json',m)
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':f['files'],'candidate_revision':b,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json')},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')}})
for p in T.glob('*.py'):ast.parse(p.read_text())
print('Frozen exact ADR1192/466; CM007 once then conditional009; MAIN115 unchanged')
