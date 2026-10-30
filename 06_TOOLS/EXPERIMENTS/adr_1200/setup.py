from common import *
import shutil,os
T=Path(__file__).parent;P=ROOT/'04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline'
a=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert a['generation']==117
r=read(ROOT/a['manifest_path']);parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1199-supervisor-independent-route-recovery/artifacts/design/freeze-rev-001.json');C=ROOT/parent['code_root'];assert all(sha(C/n)==h for n,h in parent['files'].items())
put(DES/'baseline.json',{'pointer':a,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':r,'tested_parent':parent['candidate_revision']})
for n in ('cases.json','corpus.json','authorization.json'):put(DES/n,read(P/'artifacts/design'/n))
put(DES/'provider-policy.json',read(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
for p in (P/'artifacts/evaluation-only').glob('*.json'):put(ART/'evaluation-only'/p.name,read(p))
criteria={'hypothesis':'Exact ADR1199 recovery candidate can independently recover a valid nonterminal route while retaining supervisor rejection, acquire required originals and complete CM007; CM009 runs only after all CM007 integrity, completion, requirement-review and content gates pass.',
 'success_criteria':['HTTP200 READY; ANSWER/COVERED; supported claims; no material gaps; actual required originals both acquired and cited','All spans and ACL exact; physical requests equal reserved budget; no output cap; active MAIN117 pointer and all466 candidate code hashes unchanged','Final ASSESS contains a bound requirement_review; current question parts and issues covered; no unresolved required items','Saved COMPLETE response equals returned text and assessment; offline content review against frozen reference and actual originals passes'],
 'failure_criteria':'Any source/ACL/code/budget discrepancy, missing required original, incomplete/incorrect final answer, resource stop or unknown model result stops conditional CM009; no automatic same-case rerun.',
 'per_case_budget':{'physical':40,'tools':1024,'seconds':1800,'output_cap':None},'order':['cm-007 once','cm-009 once only on all cm-007 gates'],
 'resource_policy':{'unchanged_from':'ADR1184','minimum_start_available_gib':5,'minimum_running_available_gib':3,'worker_rss_limit_gib':4,'address_space_limit_gib':6,'swap_growth_stop_mib':128,'minimum_workspace_free_gib':20},
 'scope':'Isolated ADR1199 candidate through native API with MAIN117 data/transport; no product/guard changes, no promotion/GENOS, no stronger-model comparison; known cases in-sample, no legal quality certification',
 'content_review':'Offline agent review only after product finishes; must cover both markets quantity, caps and holding duration, and exceptions when applicable, using stored source version. No gold in product or correction input.',
 'outside_deadline_guard_seconds':1860,'allow_external':True,'request':'실험도해'}
criteria['content_review']='Offline review after completed product run: both markets quantity denominator, domestic/post-application scope, caps, holding duration, types and exceptions/delegated detail. Check actual claims against frozen originals/reference. No generic unread footer; genuine gaps remain. No gold in product input.'
criteria['success_criteria'].append('Actual final calls contain frozen candidate final prompts; no unsupported generic limitation footer; no UNKNOWN or resource stop')
criteria['comparison_limit']='Known cases in_sample; no controlled prompt A/B, provider performance or legal quality certification'
criteria['content_review']='Offline review of actual final text and accepted claims against frozen source version/reference: both markets quantities and denominators, domestic/post-application scope, domestic-located foreign holding-company classification, caps, durations, disposal start/denominator, exceptions and delegated terms. CM009 must distinguish exemption/discretion and exclusions for both markets and required31 details. No gold in product input.'
criteria['success_criteria'].append('COMPOSE uses accepted-content-v1 with no memory-compose model call; all accepted claim text survives final server rendering and verifies against stored ASSESS.')
criteria['code_scope']='No edits to working product, selectedMAIN117 or profile; only experiment observation and exact granted CM context.'
criteria['recovery_review']='Observe actual rejection and independent recovery events, action application and original reads. Recovery is only attributed if the trigger occurs; candidate visibility alone is not original acquisition. KOSDAQ15 acquisition/detailed terms and acquisition obligation vs condition are explicitly checked offline. No domain schema/runtime semantic fix is claimed.'
put(DES/'criteria.json',criteria)
put(DES/'user-authorization.json',{'request':'실험도해','scope':'User requested exact1199 recovery candidate actual test: CM007 once then CM009 only if all gates pass','session':os.environ.get('CODEX_THREAD_ID')})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='CM007 final-answer completion with original integrity and requirement coverage; conditional CM009',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'recovered','role':'candidate','derived_from':['ADR-1199-experiment-v1/recovered'],'changes':'Exact1199 product bytes; isolated native API live retest','controls':'Same question/data/65-document ACL/model/budgets/resource guard; current primary Parasail'}])
m['runs'][0].update(arm_ids=['recovered'],selection_rule='User selected CM007; CM009 conditional on first pass; once each',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='CM007 and conditional CM009',version='same stored CM source as ADR1184',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='No retrieval code change; measured observed stages only',stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((RUN/'retrieval-ledger.json').relative_to(ROOT)),'sha256':'PENDING','not_applicable_reason':None})
m['design']['retrieval_stage_plan']['stages_by_arm']={'recovered':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
cases={c['id']:c for c in read(DES/'cases.json')};m['questions']=[]
for i,cid in enumerate(('cm-007','cm-009'),1):
 name=f'질문-{i:03}-{cid}.md';p=ADR/'실험'/name
 texts=['run-001/recovered; 실행 전',cases[cid]['request']['json']['question'],'평가 전용 artifacts/evaluation-only/cases.json. 제품 입력 금지.',
 '[동결](../artifacts/design/criteria.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n관측후보→확보→인용을 실행 후 전용 원장에 저장한다.',
 '실행 시 raw/call-*에 실제 요청·응답 저장. 아직 호출 없음.','실행 시 canonical/에 단계 입력·출력 저장. 아직 호출 없음.','평가 모델0. 종료 후 오프라인 검토.','실행 전. 사전 기준 그대로 판단.']
 p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {j}. {h}\n\n{v}' for j,(h,v) in enumerate(zip(heads,texts),1))+'\n')
 m['questions'].append({'number':i,'case_id':cid,'file':name,'sha256':sha(p)})
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
snapshot=ac.snapshot(ADR,'recovered',list(parent['files']),experiment_id=m['experiment_id'],arm_id='recovered',run_ids=['run-001'])
for n,h in parent['files'].items():
 p=snapshot/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
ac.freeze(snapshot);assert not ac.validate(snapshot),ac.validate(snapshot)
c=read(snapshot/'candidate.json');v=c['revisions'][-1]
b={'manifest_path':str((snapshot/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(snapshot/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(b,candidate_id='recovered',experiment_id=m['experiment_id'],arm_id='recovered',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))])
m['design']['execution_note']='New snapshot is byte-identical to frozen ADR1199 recovery candidate. Native API imports only this snapshot with all466 hashes asserted; active MAIN117 remains unchanged.'
put(ADR/'실험/manifest.json',m)
put(DES/'freeze-preflight-002.json',{'code_root':str((snapshot/'revisions'/v['revision_id']/'snapshot').relative_to(ROOT)),'files':parent['files'],'candidate_revision':b,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json')},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')}})
print('Frozen exact ADR1199/466; CM007 then conditional009; MAIN117 unchanged')
