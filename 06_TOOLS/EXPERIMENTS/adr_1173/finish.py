"""Close the experiment with its failed content gate; no live calls or promotion."""
from common import *
import sys,sqlite3,gzip,statistics
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
f=read(DES/'freeze.json');C=ROOT/f['code_root'];m=read(ADR/'실험/manifest.json');baseline=read(DES/'baseline.json');cases=read(DES/'cases.json');refs={x['id']:x for x in read(ART/'evaluation-only/cases.json')};P=ART/'live/cm-001';a=read(P/'audit.json');r=read(P/'result.json');storage=read(P/'storage-audit.json');calls=read(P/'calls.json');check=read(ART/'check-rev-012.json')
assert check['passed']==130 and check['failed']==0
assert all(sha(C/n)==h for n,h in f['files'].items());assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
reg=[read(ART/('regression-'+x+'-rev-011.json')) for x in ('main112','candidate')]
assert [(x['test'],x['status']) for x in reg[0]['rows']]==[(x['test'],x['status']) for x in reg[1]['rows']]
cv=read(ROOT/f['candidate_revision']['manifest_path']);old=next(x for x in cv['revisions'] if x['revision_id']=='rev-011');oldfiles={x['frozen_path'].split('/snapshot/',1)[1]:x['snapshot_sha256'] for x in old['files']};assert oldfiles==f['files']
changed=[]
for name,h in f['files'].items():
 before=baseline['release']['files'].get(name)
 if h!=before:changed.append({'path':name,'main112_sha256':before,'candidate_sha256':h,'working_sha256':sha(ROOT/name) if (ROOT/name).is_file() else None,'copied_to_working':False})
put(ART/'candidate-diff.json',{'candidate':f['candidate_revision'],'files':len(f['files']),'main112_changes':changed,'production_integration':'NOT_PERFORMED_CONTENT_GATE_FAILED','active_main':'MAIN112'})
base_replays=[]
for cid,ver in [('cm-001','v4'),('cm-007','v5')]:
 for repeat in (1,2):
  p=ART/('baseline-replay-'+ver)/(cid+'-r'+str(repeat));v=read(p/'result.json');assert v['target_reached']
  base_replays.append({'case_id':cid,'repeat':repeat,'artifact':str(p.relative_to(ROOT)),'new_model_calls':0,'outcome':'RESOLVED_NO_BASIS_REJECTED_BEFORE_FINISH' if cid=='cm-001' else 'EXACT_GOAL_LOOKUP_THEN_SELECTOR_MODEL_BOUNDARY'})
replays=[]
for cid in ('cm-001','cm-007'):
 p=ART/'candidate-replay-rev-011'/(cid+'-r1');v=read(p/'before-next-model.json');goals=[g for st in v['state']['investigation_supervisor'].values() for g in st.get('source_goals',[])];assert goals and all(g['status']=='ACQUIRED' for g in goals)
 replays.append({'case_id':cid,'goals':goals,'extra_selector_calls_for_goal':0,'resume':read(p/'grant-resume.json'),'http_boundary':'Intentional no-next-response TransportError after original acquired; NOT a completed answer'})
put(ART/'replay-summary.json',{'baseline':base_replays,'candidate':replays,'reconstruction':'Same native HTTP pipeline and stored canonical outputs rebound only to current opaque IDs after source/material equality. No original prose or legal meaning changed. No validator bypass. Fresh reconstructed state, not a historical process snapshot.','candidate_code_identical_to_live':True})
body=read(P/'response.json')['body'];assess=a['assessments'][-1]['payload'];gate={'case_id':'cm-001','passed':False,'technical_request_completed':True,'source_integrity_passed':not(a['source_mismatches'] or a['acl_violations']),'stored_response_verified':storage,'actual_goal_status':'제26조 ACQUIRED; 시행세칙 제23조는 이번 새 실행에서 목표로 선언되지 않음','reason':'Accepted outcome LIMITED_ANSWER/PARTIAL; assessment acknowledges unknown calculation unit, yet final narrative categorically says no aggregation and individual calculation. Cannot certify the investigation/content gate.','legal_accuracy':'not_scored; frozen reference quotes regulation and does not resolve calculation-unit ambiguity','followup_cases':{'cm-007':'NOT_STARTED_GATE_FAILED','cm-009':'NOT_STARTED_GATE_FAILED'},'same_case_retry':False,'main_promotion':False,'stronger_model_comparison':False}
put(P/'gate.json',gate)
# Observed candidates/acquired/cited stages; unknown SQL pools are not invented.
data=ROOT/baseline['release']['data_path'];nav=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True);scope=set(read(DES/'corpus.json')['document_ids']);source={};corpus=set()
for sid,raw in nav.execute('select id,json from source'):
 x=json.loads(raw);c=x.get('article_coordinate') or {};did=c.get('doc_id',x.get('document_id'));node=c.get('node',x.get('unit_id'))
 if did in scope and str(node).isdigit():source[sid]=(did,int(node));corpus.add(source[sid])
nav.close()
def coords(xs):return [{'doc_id':d,'node':n} for d,n in sorted(xs)]
reads={source[s] for s in a['read_source_ids'] if s in source};cites={source[s] for s in a['published_source_ids'] if s in source};seen=set(reads);delivered=set();views=[]
for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=json.load(gzip.open(p,'rt'))['view'];visible=set()
 for x in v.get('read_candidates',[]):
  for n in reversed(x.get('path',[])):
   if n.get('level')=='조' and str(n.get('unit_id','')).isdigit() and x.get('document_id'):visible.add((x['document_id'],int(n['unit_id'])));break
 def walk(x):
  if isinstance(x,dict):
   if x.get('source_id') in source and x.get('text'):
    visible.add(source[x['source_id']]);delivered.add(source[x['source_id']])
   for y in x.values():walk(y)
  elif isinstance(x,list):
   for y in x:walk(y)
 walk(v);seen|=visible;views.append({'call':int(p.name[:3]),'stage':v.get('source_stage',v.get('phase')),'observed_roots':coords(visible)})
graded=[]
for case in cases:
 cid=case['id'];rec=StageLedgerRecorder(cid,'executed',identity_canonicalizer)
 for sid,kind,parents,values,discard in [('delivered_or_read','source',[],seen,[]),('original_read','select',['delivered_or_read'],reads,seen-reads),('final_cited','present',['original_read'],cites,reads-cites)]:
  if cid=='cm-001':rec.record_stage(sid,kind,coords(values),parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Observed candidate not acquired' if kind=='select' else 'Acquired source not cited in final claims'} for x in coords(discard)])
  else:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='CM001 content gate failed; this case not called or scored')
 gold=[{'doc_id':x['doc_id'],'node':int(x['node'])} for x in refs[cid]['targets']];graded.append(grade_capture(rec.capture(),gold))
put(RUN/'retrieval-ledger.json',build_experiment_artifact('ADR-1173',m['experiment_id'],[build_run_artifact('run-001',graded,{'executed':['delivered_or_read','original_read','final_cited']})]))
gold={(x['doc_id'],int(x['node'])) for x in refs['cm-001']['targets']};focus={'case_id':'cm-001','observed':coords(seen),'acquired':coords(reads),'delivered':coords(delivered),'cited':coords(cites),'reference_coordinates':coords(gold),'gold_cited':len(gold&cites),'gold_total':len(gold),'views':views,'quality_gate':False,'interpretation':'A cited expected article is not evidence of legal correctness; reference itself does not specify calculation-unit semantics.'};put(P/'focus-audit.json',focus)
usage={'input_tokens':sum(x.get('usage',{}).get('prompt_tokens',0) for x in calls),'output_tokens':sum(x.get('usage',{}).get('completion_tokens',0) for x in calls),'cost_usd':sum(x.get('usage',{}).get('cost',0) for x in calls),'model_seconds':sum(x['seconds'] for x in calls)}
result={'status':'complete','implementation':'isolated candidate rev012','candidate_revision':f['candidate_revision'],'candidate_files':len(f['files']),'main112_changed_paths':len(changed),'technical_passed':130,'regression':{'main112_passed':54,'candidate_passed':54,'same_existing_failures':17,'new_failures':0},'stored_replays':{'baseline':4,'candidate':2,'new_model_calls':0,'goals_acquired_before_selector':2,'resume_verified':2},'live':{'attempted':1,'cases_total':3,'physical_calls':8,'http_status':200,'status':'READY','claims':1,'run_status':'COMPLETED','request_storage_status':'COMPLETE','outcome':'LIMITED_ANSWER/PARTIAL','seconds':r['seconds'],'source_span_checks':34,'delivered_span_checks':60,'source_mismatches':0,'acl_violations':0,'physical_budget_matches':True,'output_cap_fields':0,'gate_passed':False,'skipped':['cm-007','cm-009']},'provider':{'actual':'Chutes FP8 8/8','live_switches':0,'near_ai_live_tested':False,'gateway_fault_and_resume_tested':True,'research_client_loop_not_nested':True},'usage':usage,'active_main_unchanged':True,'active_main':'MAIN112','production_integration':False,'main_service_promotion_check':False,'genos_deployed':False,'quality_certified':False,'legal_accuracy':None,'stronger_model_comparison':False,'decision':gate['reason']}
put(RUN/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'executed':{'status':'complete','technical_success':True,'content_gate_success':False,'quality_certified':False,'attempted_cases':1,'skipped_cases':2}},comparisons=[],judge_disagreements=[],usage={'physical_requests':8,'offline_evaluator_requests':0,**usage},latency={'observed_case_seconds':r['seconds'],'improvement_certified':False},error_taxonomy=['Historical CM001 resolution without basis rejected by actual server; replay boundary is not a final-answer success','Initial candidate exact article blocked by direct scope; repaired only through a verified reference to the same source with explicit-exclusion checks','Technical intermediate implementation/fixture failures preserved in revision logs','CM001 fresh run declared only26, no23; PARTIAL assessment followed by categorical narrative; followups stopped','Audit initially compared pre-adapter schema to actual wire; corrected read-only audit uses existing provider_request transformation'])
m['llm_policy']['provider_override'].update(path=str((DES/'provider-policy.json').relative_to(ROOT)),sha256=sha(DES/'provider-policy.json'))
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=len(seen),after_filter=len(cites),presented_total=len(cites),presented_mean=float(len(cites)),presented_p50=float(len(cites)),presented_p95=float(len(cites)),golden_recall=len(gold&cites)/len(gold),selectivity=len(cites)/len(corpus));m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 cid=q['case_id'];ran=cid=='cm-001';link='../artifacts/live/'+cid
 texts=[f'run-001 / executed / {cid}; '+('rev012 실제 서빙 어댑터·격리 HTTP, 실제 모델8회.' if ran else 'CM001 내용 게이트 실패로 미실행. 저장007 재생은 별도이며 새 실험이 아니다.'),refs[cid]['question'],refs[cid]['reference_answer']+'\n\n평가 전용. 제품에 전달하지 않았고 법률 정답률을 확정하지 않았다.','[동결 요청](../artifacts/design/cases.json), [코드](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/run-001/retrieval-ledger.json). 관측 후보→확보→최종 claim 인용만 센다. 미실행은 executed=false.',f'[실제 요청·응답]({link}/calls.json), raw/call-*/request.json,response.json 및 canonical/*.json.gz.' if ran else '실제 제품 호출0.', '요청 해석1·조사3·감시2·ASSESS1·COMPOSE1. 보완 모델0.' if ran else '새 중간 모델0.', '평가 모델0, 같은 질문 재시도0. 알려진 사례이며 법률 정확도 미채점.', 'HTTP200/READY·claim1·저장 COMPLETE. 내부 LIMITED_ANSWER/PARTIAL과 단정적 최종 문장의 불일치로 내용 게이트 실패. [감사]('+link+'/audit.json), [저장]('+link+'/storage-audit.json), [답변]('+link+'/answer.txt).' if ran else 'NOT_STARTED_GATE_FAILED. 미실행을 오답으로 세지 않는다.']
 p=ADR/'실험'/q['file'];p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
'확정 원문 선집행·판단 보완 분리·목표 종료 계약·문서/목표 선택·실제 서빙429 전환을 격리 후보에 구현했다. 기술130검사 통과, 동일71회귀54통과/17기존실패·새회귀0. 저장 CM001/007에서 필요한 원문을 선택 모델 호출 없이 확보했다. 새 CM001은8호출·HTTP200/READY·저장완료지만 LIMITED_ANSWER/PARTIAL과 단정적 최종 문장의 불일치로 내용 게이트 실패. CM007/009·작업 코드 통합·MAIN 승격은 중단했고 MAIN112를 유지한다.',
'저장1172 CM001의 FINISH는 실제 서버에서 RESOLVED의 원문 근거 누락으로 거절됐다. 목표 실행 전 판단 보완 단계로 들어가는 것이 확인됐고, 잘못된 종료가 그대로 성공했다고 확대하지 않는다. CM007은 정확한 목표 조회 뒤 다시 선택 모델을 기다렸다. 별도 direct search scope가 검증된 참조의 세칙23⑤만 허용하여 세칙23 전체 읽기를 막는 문제도 발견했다.',
'[사전 기준](artifacts/design/criteria.json), [사용자 계획](../../../07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/CM_REQUIRED_SOURCE_EXECUTION_PLAN_20261028.txt). 원문 집행은 법률 판단을 대신하지 않는다. 실제001한번 뒤 내용까지 통과할 때만007/009. 같은 사례 자동 재실행·더 좋은 모델/GENOS 대리 모델 비교 없음.',
'기존 supervisor/request 상태를 재사용한다. 현재 세대/권한에 결속된 EXACT ASSESS 부족과 명시 source_targets를 보존하고 모델 선택·no-progress 인계보다 먼저 기존 READ/조회 실행기로 보낸다. 조회번호를 생성하지 않고 현재 허용 도구에 문서/좌표/goal_id를 결속한다. READ 영수증의 정확 목표·전체 span·원문 검증을 충족해야 ACQUIRED다. 같은 canonical source의 검증된 reference endpoint에서 필요한 상위 목표로만 한정 읽기를 허용하며 ACL·사용자 명시 제외·검색 범위를 유지한다. 재개 때 다시 검증한다. 종료의 RESOLVED/NOT_NEEDED는 현재 원문 근거가 필요하고 미해결 목표는 제한 응답에 남는다.',
'MAIN112 데이터·65개 공개 원문 ACL·현재 Qwen3.8·40/1024/1800·출력 상한 없음 유지. CM 질문은 별도 사용자 반출 승인으로 처리하며 공개 질문으로 바꾸지 않는다. 서빙은 pure provider_routing 모듈을 공유하고 gateway만 물리 전환을 소유한다. 확정429만 요청당1회 Chutes→Near AI; 예산·기한·전환 이력은 같은 요청의 새 run에도 보존. research 클라이언트를 서빙 전송기 안에 중첩하지 않는다. rev011과 실실행rev012의463파일 모두 동일.',
json.dumps(result,ensure_ascii=False,indent=2),
'저장재생001은 세칙23 전체 READ→ACQUIRED,007은 상장규정13 LOOKUP→READ→ACQUIRED이며 추가 선택 모델0회. 두 재개 권한 검사 통과. 다음 모델 응답을 의도적으로 공급하지 않아 반환502이며 완성 답변으로 세지 않는다. 새001은26조만 목표로 선언하고 해당 원문을 확보했다. 세칙23 목표 자체가 새로 선언되지 않아 이번 새 실행에서23 선확보가 발동했다고 말할 수 없다. ASSESS는 산정 단위 미확인/PARTIAL을 남겼지만 COMPOSE는 개별 계산을 단정했다. 기준답변도 조문 인용이어서 법률 오답률을 확정하지 않고 내용 게이트 실패로 기록했다. 모든 중간 실패와 감사 실행기 보완은 artifacts 로그에 보존.',
f'실제8요청, 입력{usage["input_tokens"]}·출력{usage["output_tokens"]}토큰, 제공자 보고비용${usage["cost_usd"]:.9f}. 관측 요청161.844초·모델 전송합{usage["model_seconds"]:.3f}초. 원문34구간·모델전달60구간 불일치0,권한위반0,출력상한필드0,8물리호출=8차감. 실제429없음·Near AI실통신미검증. 골드좌표 인용1/1은 법률 정확도가 아니다.',
'이미 확정된 목표를 서버가 실행하는 기계적 경로는 저장상태 재생과 실제26조 집행으로 확인했다. 어떤 추가 원문이 필요한지 판단하는 문제와 확보 원문의 해석·최종 문장 강도는 남아 있다. 목표를 선언하지 않은 새 실행에 과거 목표를 몰래 주입하지 않았다.',
'알려진 인샘플·새001한번. 저장재생은 원문/재결속으로 재구성한 상태이며 과거 프로세스 자체 복원이 아니다. 기존71회귀만 동일비교했으며 시스템 전체 품질·전체성능 검증이 아니다. 내용 게이트 실패로 조건부 통합/승격/선택서비스 재조회와007/009는 미실행. 기술 결과를 법률 품질·현장 배포로 확대하지 않는다.',
'작업 제품 파일과 선택 MAIN112를 변경하지 않았다. 후보는 연구 경로에만 있고 실행 기본값으로 등록하지 않았다. 롤백할 활성 포인터 변경이 없다. 과거1171/1172와 실패이력 보존, GENOS현장/메일/Git 미수행. 후속은 목표 필요 판단·불확실성과 최종 문장 일치의 별도 설계/실험이며 이번에 더 좋은 모델 비교를 수행하지 않았다.',
'check.py는현재동결130검사; regression.py main112/candidate는동일71검사. audit_result.py cm-001, audit_storage.py cm-001은 읽기 전용. live.py cm-001은 dispatch.json 때문에 재호출을 거부한다. 상세 경로와 해시는 artifacts/manifest.json. 이미 종료된 기록을 덮어쓰는 재실행은 하지 않는다.'
]
p=ADR/'README.md';meta=p.read_text().split('---',2)[1];p.write_text('---'+meta+'---\n\n# 확정 원문 선집행 구현과 CM001 내용 게이트\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 결과\n\nCM001 1회는 반환·저장 완료, 내용 게이트 실패. CM007·009는 미실행.\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
A=ROOT/'09_ARTIFACTS/AUDITS/20261028-required-source-execution';A.mkdir(exist_ok=True)
(A/'구현과_검증결과.txt').write_text('확정 원문 선집행 구현 결과 — 2026-10-28\n\n1. 구현\n격리 후보 ADR1173 rev012에 구현했다. 이미 검증된 미확보 목표는 모델 선택 전에 기존 조회·읽기로 집행한다. 잘못된 판단 채택과 독립 원문 확보를 분리했고, 이유 한 문장으로 목표를 지우지 못하게 했다. 모델은 문서/좌표 또는 목표번호를 지정하고 서버가 현재 도구에 결속한다. 실제 서빙 gateway에 확정429일 때 요청당 한 번 Chutes→Near AI 전환과 물리 호출별 예산 차감을 연결했다. 선택 MAIN112에는 아직 반영하지 않았다.\n\n2. 저장 로그와 오류 주입\n저장001/007 응답4개를 실제 서버 경로로 재생했다. 001의 잘못된 종료는 근거 없는 RESOLVED로 거절되는 것이 확인됐다. 수정본 재생에서001 시행세칙23 전체,007 상장규정13 원문을 선택 모델 추가0회로 확보했고 재개 권한도 확인했다. 의도적으로 다음 모델 응답을 공급하지 않은 재생이므로 완성 답변 성공으로 세지 않는다. 기술130검사 통과. 동일71회귀는 MAIN112/수정본 모두54통과·17기존실패로 새회귀0.\n\n3. 실제 CM001 1회\nChutes Qwen3.8으로8호출·161.844초, HTTP200/READY·주장1개·요청저장 COMPLETE·실행저장 COMPLETED. 원문34구간과 모델전달60구간에서 불일치/권한위반0. 8물리요청=8예산차감. 판단7단계의 저장 hash와 반환 화면 hash·저장 답변을 대조했다. 실제429는 없었고 Near AI 실통신은 미검증이다.\n\n4. 통과하지 못한 부분\n이번 새 실행은26조만 필수 목표로 지정했고 시행세칙23을 목표로 지정하지 않았다. 내부판단은 산정 단위가 미확인인 LIMITED_ANSWER/PARTIAL인데 최종 문장은 합산이 아니라 개별 기준이라고 단정했다. 저장 기준답변도 조문 인용이라 법률 오답을 확정하지 않지만, 조사·내용 게이트는 통과로 인정하지 않았다. 서버가 확정된 목표를 집행하는 기능과 모델이 추가 조사 필요성을 알아내는 능력은 구분해야 한다.\n\n5. 중단·현재 상태\n사전 기준에 따라 CM007·009 추가 모델 호출, 같은 질문 재시도, 작업 코드 통합, MAIN 승격·새 선택서비스 검증을 진행하지 않았다. MAIN112 유지. 더 좋은 모델 비교·GENOS대리모델 호출·현장배포·메일·Git 미수행. 구현 후보·원시 응답·실패·검증·롤백 경계는 아래 ADR에 보존했다.\n\n상세: '+str(ADR/'README.md')+'\n실제 답변: '+str(P/'answer.txt')+'\n후보 코드: '+str(C)+'\n')
put(ART/'report.json',{'path':str((A/'구현과_검증결과.txt').relative_to(ROOT)),'sha256':sha(A/'구현과_검증결과.txt')})
print('closed result',result['live'],'changes',len(changed))
