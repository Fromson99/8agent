from runtime import *
import finalize
finalize.main()
m=read(A/'metrics.json');rs=read(A/'results.json');front=(D/'README.md').read_text().split('---',2)[1]
summary='목록·매핑은 양쪽16/16. 내용은 양쪽0/2. 새후보는 두질문 모두 필요한4조문을 채택했으나 navigation_synthesis의 응답 schema를 Gemini가 HTTP400으로 거절하여 최종답변 실패. 사전18/18기준 미달.'
errors=[]
for p in sorted((A/'calls').glob('*/*/call-*/response.json')):
 r=read(p)
 if r.get('error'):errors.append({'path':rel(p),'error':r['error']})
(A/'provider-errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2)+'\n')
sections=[('결정 요약',summary),('문제와 변경 전 구조','후보정보·조문판정·질문요건·미해결참조가 후속호출에 일관되게 전달되지 않았다. 기존후보455의 내용탐색과 비교했다.'),('가설과 사전 판정 기준','공통work state, 반복노출 후보페이지, 읽기/판정대기열, 요구사항별 근거와 종합검증으로18/18성공·회귀0·오류0. 사전설계와 입력은 결과전에 고정했다.'),('실험 설계','부모ADR0455/repaired와 새stateful을 동일18문항·14호출/180초예산·질문별교대 단회비교. 2개의오프라인내용judge는제품컨텍스트에서분리. 결과후수정/재실행없음.'),('데이터·모델·재현성','합성10문서12조문·희소occurrence고정. gemini-3.1-flash-lite/temperature0/minimal/4096. 실제자료 전송없음. [114입력hash](artifacts/input-lock.json), drift0.'),('결과',summary+' [질문별원문·상태·채점](실험/README.md).'),('사례별 오류 분석','두내용사례에서 후보7개읽기→정답4개채택/방해3개제외까지성공. 호출9회째 첫종합단계의중첩배열schema에서400. 답변생성이실패했으므로근거회수를답변성공으로세지않는다. [실제provider오류](artifacts/provider-errors.json).'),('비용·지연·회수 규모','[실제호출·usage·지연](artifacts/metrics.json), [회수/탈락원장](artifacts/retrieval-ledger.json). 오류는error.json뿐아니라response.json.error로확인했다. 실제청구액미측정.'),('해석','공통상태전달과읽기/판정대기열은이두사례의근거누락을해결했다. 종합/검증품질은400으로미확인. 이전ADR0453의배열bound제거진단을참고한전송schema후보는새ADR에서만실험한다.'),('한계와 일반화 가능 범위','알려진모의18질문·단회·in-sample. 다양한실제문서/질문과GENOS내부모델은미검증. 상태는요청내메모리공유이며재시작복원저장소가아니다.'),('운영 결정·롤백 조건','[명시적factory연결](GUIDE.md). 활성MAIN/GENOS변경없음. 후보선택을부모455로돌리면복귀. 품질기준미달로자동승격없음.'),('재현 명령','고정후보32단위/계약테스트통과, snapshot/pre-call검증통과. [최종검증](VALIDATION.md). 완료run/score덮어쓰기금지. 새수정은새ADR.')]
(D/'README.md').write_text('---'+front+'---\n\n# 공통 탐색 상태와 다중 조문 종합\n'+''.join(f'\n## {i}. {h}\n\n{b}\n' for i,(h,b) in enumerate(sections,1)))
(D/'RESULT.md').write_text('# 결과\n\n'+summary+'\n\n[구현·실행 연결](GUIDE.md) · [전체기록](실험/README.md) · [조건·한계](README.md)\n')
(D/'VALIDATION.md').write_text('# 검증\n\n고정후보32 tests PASS. snapshot/pre-call validate PASS. 입력drift0. 품질18/18기준 FAIL(16/18). 최종ADR검증은별도수행.\n')
for p in (D/'실험').glob('질문-*.md'):
 s=p.read_text().replace('ADR0454/run-001, baseline(ADR0451 mapped), routed(ADR0454).','ADR0456/run-001, baseline(ADR0455 repaired), stateful(ADR0456).').replace('위 structured_navigation 호출에 포함한다.','위 structured_navigation, navigation_requirements, navigation_review, navigation_synthesis, navigation_verify 역할별 호출로 기록한다.')
 p.write_text(s)
p=D/'실험/README.md';p.write_text(p.read_text().replace('기존 mapped | 수정 routed','기존 repaired | 수정 stateful'))
finalize.inventory();print(summary)
