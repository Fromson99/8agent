from common import *
import shutil,zipfile
candidate=read(DES/'candidate-selected.json');C=ROOT/candidate['code_root'];active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==151 and release['files']==candidate['selected_files']
assert all(sha(ROOT/release['code_root']/n)==h and sha(ROOT/n)==h for n,h in release['files'].items())
H=ROOT/read(ART/'mail-package.json')['handoff'];sent=read(H/'EMAIL_SENT.json');assert 'SENT' in sent['label_ids'] and sent['header_verified']
sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
from semantic_runtime.legal_agent import guided_answer as g,completion_contracts as cc
fixture=read(DES/'actual-cm003.json.gz');latest_input=read(ART/'actual-final-r6/actual-input.json.gz')
core=g.wire_input(g.input_data(fixture['question'],fixture['parts']['SELECT']['payload']['issues'],cc.evidence_options(fixture['sources']),[]))
assert core==latest_input['data'] and g.PROMPT==latest_input['system'] and g.schema(fixture['parts']['SELECT']['payload']['issues'],cc.evidence_options(fixture['sources']))==latest_input['schema']
trials=[];physical=[]
findings={3:'문서명 노출, 예외 생략, 유형 중 하나라는 단정과 동시 해당 가능성 표현 충돌',4:'문서명은 제거했지만 제3호 단정 및 COVERED, 질문0. 사용자 의도 실패',5:'설명 뒤 불확실성은 있으나 장황한 반복, 예외 생략·과도한 적용 표현. Parasail429 후 기존 정책 NearAI1회',6:'설명 먼저·구체 질문 마지막·문서명 없음·PARTIAL. 원문 문구 직접 반복과 예외 생략, 과도한 조건부 적용 표현 잔존. 법률 품질 미통과'}
for n in (3,4,5,6):
 base=ART/('actual-final-r'+str(n));r=read(base/'result.json');canonical=read(base/'actual-input.json.gz');calls=[]
 for p in sorted((base/'model').glob('call-*')):
  request=read(p/'request.json.gz');response=read(p/'response.json.gz')
  assert request['messages'][0]['content']==canonical['system']
  assert json.loads(request['messages'][1]['content'])==canonical['data']
  for row in canonical['data']['originals']:
   original=next(o for o in cc.evidence_options(fixture['sources']) if o['id']==row['id']);assert original['text']==row['text']
  status=429 if response.get('error',{}).get('code')==429 else 200
  calls.append({'path':str(p.relative_to(ROOT)),'status':status,'wire_originals_match':True})
 physical+=calls
 trials.append({'trial':n,'candidate_revision':'rev-'+str(n-1).zfill(3),'result':r,'finding':findings[n],
  'actual_answer_path':str((base/'사용자답변.txt').relative_to(ROOT)),'calls':calls,'legal_quality_pass':False})
usage={'physical_calls':len(physical),'normal_responses':sum(c['status']==200 for c in physical),'known429':sum(c['status']==429 for c in physical),'unknown':0,'reported_cost_usd':sum(u['cost_usd'] for t in trials for u in t['result']['usage']),'reported_tokens':sum(u['total_tokens'] for t in trials for u in t['result']['usage']),'review_calls':0,'repair_calls':0,'repeat_additional_calls':0,'new_retrieval_calls':0,'model_grader_calls':0}
assert usage['physical_calls']==5 and usage['normal_responses']==4 and usage['known429']==1
checks={name:read(ART/name/'result.json') for name in ('final-service-contracts','working-contracts-r2','prepared-review')}
assert all(v['failed']==0 and v['code_unchanged'] for v in checks.values())
report={'scope':'General final ASSESS/COMPOSE uses one guided reply, no final semantic review, correction or automatic research reentry. Source/ACL/integrity kept; command/investigation and special workflow/scenario review kept.',
 'products':14,'native_metadata':1,'derived_pins':31,'changed_files':46,'serving_files':531,'same_executable_SQL':640,
 'core_tests':{n:{k:r[k] for k in ('passed','failed','exit_code','code_unchanged')} for n,r in checks.items()},
 'test_rechecks_overlap':True,'prior_related_tests':{'passed':19,'failed':2,'same_two_on_MAIN150':True,'path':'related-before/result.json'},
 'model_trials':trials,'usage':usage,'wire_audit':{'physical_inputs_checked':5,'source_mismatches':0,'wire_mismatches':0,'document_grant_mismatches':0,'latest_core_input_prompt_schema_identical_to_final_code':True,'source_checks_per_trial':27,'note':'5 outbound payloads including429, no assertion of provider processing429 payload'},
 'lifecycle':'Synthetic native state and gateway: unresolved cannot confirm; facts update same goal; resolved user-confirmed experience stores conditions/claim/source graph. Actual Qwen continuation and shared domain ontology publication not tested.',
 'main_activation':read(ART/'main/activation.json'),'package':read(ART/'mail-package.json'),'installer':read(ART/'mail-package-tests-r3/result.json'),'email':sent,
 'quality_certified':False,'actual_legal_quality_pass':False,'full_retrieval_rerun':False,'actual_multiturn_qwen':False,'field_deployed':False,'oracle_calls':0,
 'failure_records':'All early runner, contract, native version5 fixture, package dependency and whitespace failures retained. Model outputs from every revision retained; no best-run-only reporting.'}
put(ART/'result.json',report)
lines=['MAIN151 최종 검토 제거·추가 질문 연결 및 삼성메일 발송 결과','',
 '일반 대화의 최종 ASSESS/COMPOSE: 확인한 설명 → 마지막 불명확한 부분과 구체 질문. 최종 의미 검토·보완/자동 재조사0. 대화·조사 검토와 업무/시나리오 경로는 유지.',
 '본문의 원문 미리보기·출처명 반복과 검토 실패 목록을 제거. 원문 카드·권한·정확한 span 결속 유지. 미해결 경험 저장 차단, 사실 추가 후 같은 목적의 판단/답변 갱신, 해결 후 사용자 확인으로 경험 온톨로지 저장.',
 'MAIN150 → MAIN151 guided-answer-20261105-r1. 제품14+native메타1+pin31=46변경, 서빙531 동일, 실행SQL640 동일. 이전150·Gold 원복 바이트 보존.',
 '핵심42 통과, 작업39/준비본39 부분집합 재확인. 실제 root service38/Gold 코드연결9. 기존 관련19통과/2실패는 MAIN150도 동일. 신규 전체 회귀/법률 품질 인증은 아님.','']
for t in trials:
 lines.extend(['실제 CM003 최종단계 trial '+str(t['trial']),t['finding'], '시간/물리호출: '+str(round(t['result']['seconds'],3))+'초 / '+str(t['result']['model_calls']), '실제 답변: '+t['actual_answer_path'],''])
lines.extend(['호출 합계: '+json.dumps(usage,ensure_ascii=False),
 '최신 실제 답변(원문은 앞선 실제 검색 결과를 readonly DB에서 재대조; 이번에는 전체 검색 미실행):',
 (ART/'actual-final-r6/사용자답변.txt').read_text(),
 '예외 설명 누락·일부 직접 문구 반복·과도한 조건부 표현이 남아 법률 답변 품질 통과로 보고하지 않는다. 1문항을 수정하면서 반복한 인샘플 시험이며 일반화/속도 인과 인증0.',
 '멀티턴/온톨로지 연결은 모의 검사다. 실제 Qwen 연속 대화나 운영 지식 게시를 수행하지 않았다.',
 '패키지: MAIN151_FULL_20261105_R1.zip / MAIN151_ONECLICK_R1.txt / MAIN151_WORKFLOW.py / GUIDE.txt / VERIFICATION.json / SHA256SUMS.txt. JS0/중첩압축0. 531서빙 동일(기존JS1 해시검사) + 검증 보조11, 보조1파일 trailing space만 제거(AST동일).',
 '정확한 무인자 bash 명령의 ~/DEV 링크→설치·재실행·상태·stage·commit·코드+generation 전체gate·undo 통과. 최초 검증 도구 누락/다음 trailing whitespace 실패 보존 후 패키지 보완. 메인 서빙 바이트 변경0.',
 '삼성메일 SENT '+sent['id']+' / '+sent['to']+' / 6첨부. 수신자·제목·본문·첨부 이름/MIME/복호 크기 재조회 확인.',
 'GENOS 실제 checkout/commit/리비전/내부모델/화면 및 Oracle접속은 미확인. 로컬 MAIN 전환과 코드메일 인계까지 완료.'])
(ART/'수정과_메인반영_발송결과.txt').write_text('\n'.join(lines)+'\n')
AUD=ROOT/'09_ARTIFACTS/AUDITS/20261105-guided-answer-main151';AUD.mkdir(exist_ok=True)
shutil.copyfile(ART/'수정과_메인반영_발송결과.txt',AUD/'수정과_메인반영_발송결과.txt')
put(AUD/'final-validation.json',{'main':active,'report':{'path':str((ART/'result.json').relative_to(ROOT)),'sha256':sha(ART/'result.json')},'email':sent,'quality_certified':False})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),selection_rule='Existing CM003, four adaptive prompt revisions with every trial retained; final source-boundary integration preserves latest core input/prompt/schema. No independent held-out legal accuracy claim.')
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':4}]
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'legal_answer_rerun':False},'explanation':{'implementation_pass':True,'legal_quality_pass':False,'report':str((ART/'result.json').relative_to(ROOT)),'main_generation':151}},comparisons=[],judge_disagreements=0,usage=usage,latency={'final_stage_seconds':[t['result']['seconds'] for t in trials]},error_taxonomy=[{'type':'condition_exception','count':4,'note':'All trial omissions retained; not an automated legal scorer'},{'type':'unsupported_inference','count':4,'note':'Conditional/categorical overstatement in human inspection'}])
m['reservation']['scope']='Latest user steering: remove final condition/exception review and use one guided answer, continue same-goal facts, confirm resolved experience ontology; user then authorized MAIN151 and Samsung email.'
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
sections=[('결정 요약','사용자 지시로 MAIN151 반영 및 삼성메일 SENT '+sent['id']+'. 구현 완료, 실제 Qwen 법률 품질 미통과. USER_DIRECTED_CUTOVER/quality_certified=false. [전체 결과](artifacts/수정과_메인반영_발송결과.txt).'),
 ('문제와 변경 전 구조','실제 CM003 최종 조건·예외 판단85.655초+보완62.972초 뒤 주장0·원문전용. 이전 표시가 원문 미리보기를 중복하고 사용자가 출처는 별도로 제공한다고 정정했다. 최신 지시는 반복 검토 대신 모름과 구체 질문으로 대화를 이어가는 방식이다.'),
 ('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False)+' 최초 표현만 변경하던 범위는 사용자 추가 지시로 final ASSESS/COMPOSE까지 확대. design/scope-steering.json 및 실제 모델별 입력·후보 revision 보존. 호출 한도2는 각 독립 최종단계 trial의 정상1+기존429전환1 한도이며 전체 합계5를 별도 집계한다.'),
 ('실험 설계','MAIN150 530파일 기반 격리후보. final guided answer 신규1 및 기존제품13/native메타1/pin31. 원문 조회·ACL·세대 검증 유지. 최종 단계만 교체하며 대화/조사/별도 workflow·scenario는 유지. 현재 사용자 요청에 따라 후보동결·준비검사·MAIN151 전환·Gold동일 엔진·정확한 전달 ZIP 검사 후 메일 발송.'),
 ('데이터·모델·재현성','기존 financial cm-003 원문 질문 및 ADR1409 실제 확보 공개 원문2개/24옵션, readonly store span27 대조. Risk CM은 태그·작업 지침에 따라 선택0. Qwen3.8 Parasail FP8/none; trial5 Parasail429→기존 정책 NearAI. 답변키 입력0. 각 trial의 request/response는 gzip, 모든 버전 결과를 보존한다.'),
 ('결과','핵심42/작업39/준비39(중복), 실제 selected root38/Gold9. Qwen 실제4정상+4291/UNKNOWN0. 최신24.752초/최종1회·추가 검토0·같은 평가 재조회0. 설명 후 구체 질문은 관찰했지만 예외 누락과 과도한 적용 표현으로 법률 품질 통과 아님.'),
 ('사례별 오류 분석',json.dumps(findings,ensure_ascii=False)+' 초기 시험기 import/승인필드 오류는 모델0. 첫 신규검사 함수 인자 오류, 이후 기존 fixture 갱신, native 증거 전달 검사 version5 fixture 오류와 패키지 검증 도구 누락/whitespace 실패를 보존했다.'),
 ('비용·지연·회수 규모',json.dumps(usage,ensure_ascii=False)+' 이번에는 신규 검색/후보 탈락이 없어 회수 원장 해당없음. 이전 실제 원문 범위를 고정한 최종단계 시험이다. 모델 입력5건 원문/권한/wire 불일치0, 최신 prompt/schema/본문입력은 최종 코드와 동일. 전체 사용자 요청 지연 비교로 확대하지 않는다.'),
 ('해석','검토·보완을 기다리지 않고 설명/질문을 반환하는 제어와 미해결 저장 차단은 확인했다. 모델의 의미 오류를 제거한 것은 아니다. 현재 선택모드에서는 독립 최종 의미 검토를 생략하므로 일반 정확도 인증을 하지 않는다.'),
 ('한계와 일반화 가능 범위','인샘플1질문·수정중4trial. 실제 full retrieval/멀티턴/Qwen 경험 저장/공유 도메인 온톨로지 게시 미시험. 모의 멀티턴 및 원문 전달 gateway 계약과 구분. 실제 GENOS·Oracle·운영 데이터 변경0. 법률 품질 미통과를 사용자에게 알린 뒤 메인 지시를 받아 반영했다.'),
 ('운영 결정·롤백 조건','MAIN151 release 및 main/authorization.json 사용. main/gold-binding-before-exact.json과 릴리스 rollback의150 포인터 보존. 인계 ZIP531서빙 동일, JavaScript1 기존 해시 요구. 검증보조11개 포함, helper1 공백 제거 AST동일. 정확한 TXT 설치/코드+원문세대 gate/원복 통과. 삼성메일6첨부 재조회 확인. 코드서빙 실제 리비전은 현장 적용 전이다.'),
 ('재현 명령','freeze.py → check.py → prepare_live.py/live.py(기존 결과를 덮어쓰지 않는 새 trial 필요) → integrate.py → prepare_main.py → 준비본 check.py → activate.py → package_mail.py → test_mail_package.py → prepare_mail.py → Gmail 명시 발송 → finish.py. 실행 스크립트는 06_TOOLS/EXPERIMENTS/adr_1410, 영구검사는 05_TESTS/CONTRACTS/test_guided_answer.py와 test_workflow_review_followup.py. 외부모델/발송은 자동 재실행하지 않는다.')]
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN151 설명·추가 질문 연결 및 인계\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
q=ADR/'실험/질문-001-cm-003.md'
q.write_text('# 질문 001 — cm-003\n\n## 1. 실행 메타\n\n2026-11-05 / exact / explanation / Qwen3.8. baseline은 재실행하지 않았고 동일 질문을 네 prompt revision으로 실행했다.\n\n## 2. 사용자 질문 원문\n\n'+fixture['question']+'\n\n## 3. 기준답변\n\n정답키를 입력하거나 자동 채점하지 않았다. 실제 확보 원문 조건·예외와 사람이 대조하여 모두 법률 품질 미통과로 남겼다.\n\n## 4. 제품 입력 원값\n\n[전체 fixture](../artifacts/design/actual-cm003.json.gz). 신규 회수0, 원문2/선택옵션24.\n\n## 5. 제품 모델 호출\n\n'+ '\n'.join('- trial'+str(t['trial'])+': [실제 답변](../artifacts/actual-final-r'+str(t['trial'])+'/사용자답변.txt), [원 입력·schema](../artifacts/actual-final-r'+str(t['trial'])+'/actual-input.json.gz), [호출 결과](../artifacts/actual-final-r'+str(t['trial'])+'/result.json); model/call-*에 모든 원 request/response/output gzip 보존.' for t in trials)+'\n\n## 6. 중간 호출\n\n최종 단계 검토·보완0. trial5의 기존 확인429 제공자 전환1은 별도 물리호출로 집계.\n\n## 7. 채점\n\n외부 judge0, 사람이 문구와 원문 조건을 확인했다.\n\n## 8. 최종 판정\n\n설명·추가 질문 방식과 제어 연결은 구현 확인. 실제 법률 내용은 예외 생략 등으로 미통과. '+json.dumps(findings,ensure_ascii=False)+'\n')
(ADR/'실험/README.md').write_text('# 질문 및 결과\n\n- [cm-003](질문-001-cm-003.md)\n- [전체 결과](../artifacts/수정과_메인반영_발송결과.txt)\n')
prep=ART/'host-preparation';prep.mkdir(exist_ok=True)
for n in ['implement_guided1410.py','refine_guided1410.py','fixture_guided1410.py','wire_guided1410.py','fix_mail_deps1410.py']:
 p=Path('/tmp')/n
 if p.exists() and not (prep/n).exists():shutil.copyfile(p,prep/n)
print('Report ready; MAIN151 and SENT',sent['id'],'physical5 / normal4 / 4291 / unknown0')
