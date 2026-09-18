"""Post-run reporting only; never changes product results or grading."""
from runtime import *
import finalize
finalize.main()
m=read(A/'metrics.json');rs=read(A/'results.json');front=(D/'README.md').read_text().split('---',2)[1];b=m['by_arm']['baseline'];c=m['by_arm']['portable']
summary=f"부모 {b['pass']}/18 → 수정 {c['pass']}/18. 수정안의 목록·매핑 {c['metadata_pass']}/16, 다중 조문 답변 {c['content_pass']}/2. 사전 기준 충족={m['success_criteria_pass']}."
errors=[]
for p in sorted((A/'calls').glob('*/*/call-*/response.json')):
 r=read(p)
 if r.get('error'):errors.append({'path':rel(p),'error':r['error']})
(A/'provider-errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2)+'\n')
rows=[];details=[]
for cid in ['multi-entry-alias','multi-entry-literal']:
 for arm in ARMS:
  v=m['by_arm'][arm]['by_case'][cid];o=rs['cases'][cid][arm]['output'];s=o['retrieval']['term_agent'];claims=o['answer'].get('claims',[]);ids=sorted({sid for claim in claims for sid in claim.get('source_ids',[])})
  rows.append({'case':cid,'arm':arm,'initial_pool':s.get('initial_pool_source_ids',[]),'read':s.get('read_source_ids',[]),'adopted':s.get('selected_ids',[]),'final_answer_cited_sources':ids,'requirement_count':len(s.get('requirements',{})),'synthesis':s.get('synthesis'),'calls':v['calls'],'answer':o['answer']['text'],'pass':v['pass']})
  details.append(f"| {cid} | {arm} | {v['initial_pool_count']} | {v['read_count']} | {v['selected_count']} | {len(ids)} | {v['required_selected']}/{v['required_total']} | {v['calls']} | {v['pass']} |")
(A/'content-outcomes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
table='| 질문 | 방식 | 초기 후보 | 읽음 | 채택 | 최종 인용 | 정답 조문 채택 | 총 호출 | 답변 통과 |\n|---|---|---:|---:|---:|---:|---:|---:|---|\n'+'\n'.join(details)
sections=[('결정 요약',summary+' 명시적 로컬 후보 배선이며 활성 MAIN과 GENOS는 변경하지 않았다.'),('문제와 변경 전 구조','ADR0456은 두 질문에서 필요한4조문 모두 채택했으나 종합단계의 중첩 배열 응답 schema가 Gemini HTTP400으로 거절됐다. 최초455의 문제는 후보·범위·미검토 근거를 다음 도구로 일관되게 넘기지 못하고 최종 조합 검증도 없었던 것이다.'),('가설과 사전 판정 기준','원래 로컬 제약을 유지하며 종합/검증 전송 schema의 배열 크기 bound만 설명문으로 옮기면400을 제거할 수 있다. 성공18/18, 기존만 성공한 회귀0, 잘못된 인용·범위 이탈·provider 오류0. [사전 설계](artifacts/design-before-snapshot.json).'),('실험 설계','완료 부모456/stateful과 portable을 같은18질문, Gemini/설정, 14호출/180초예산, 질문별 교대 순서로 단회 비교했다. 후보 종합/검증 역할의 전송 schema만 변경했다. 원문·prompt·요구사항·선택·허용범위·로컬검증은 고정했다. 결과 후 변경/재실행/재채점은 없다. [초기 단위검사 fixture 보정](artifacts/preflight/correction.json)은 첫 외부 호출 전에만 했고 제품은 바꾸지 않았다.'),('데이터·모델·재현성','합성10문서12조문과 알려진18질문. 실제 내부자료/법률 원문 전송 없음. gemini-3.1-flash-lite, temperature0, minimal, maxOutputTokens4096, 공통 GeminiExperimentClient. [122개 입력hash](artifacts/input-lock.json), drift='+str(m['input_drift'])+'.'),('결과',summary+'\n\n'+table+'\n\n[최종 답변과 종합 검증 상태](artifacts/content-outcomes.json), [18질문 원요청·원응답·판정](실험/README.md).'),('사례별 오류 분석','[실제 provider 오류](artifacts/provider-errors.json)는response.json.error도 확인한다. 근거를 채택한 수와 최종 답변에 인용한 수를 구분한다. HTTP400 이후 답변 없는 기존 결과를 정답 성공으로 처리하지 않았다. [실패별 기록](artifacts/diagnosis.md).'),('비용·지연·회수 규모',f"기존 제품{b['calls']}회, 수정 제품{c['calls']}회. 수정 p50={c['latency_p50']:.2f}s, p95={c['latency_p95']:.2f}s. 의미 채점 모델2회는 제품 예산 밖의 평가이며 제품에 피드백하지 않는다. 토큰은 [metrics](artifacts/metrics.json), 단계별 조문 좌표는 [원장](artifacts/retrieval-ledger.json). 실제 청구액 미측정."),('해석','공통 상태가 후보→읽기→판정→참조→요구사항→종합/검증→하위 Pipeline까지 연결된다. 복수 진입점의 후보를 유지하며 문서 범위를 확대하지 않는다. 요청 내 유효한 용어 매핑은 후속 검색에도 적용한다. provider 문법 제약을 바꿔도 응답은 원래 schema와 근거 검증을 통과해야 한다.'),('한계와 일반화 가능 범위','모의 in-sample18질문과 내용2질문의 단회 결과다. 미지 질문 일반화, 대규모 후보, 실제 내부자료, GENOS 모델·배포는 검증하지 않았다. 의미 검증/채점은 LLM 판단이고 전문가 보정이 없다. work_state는 요청 내 메모리 상태이며 디스크 재시작 복원을 구현한 것은 아니다.'),('운영 결정·롤백 조건','[실행 factory/계약/검증](GUIDE.md). 명시적으로 선택하는 후보 Conversation에 배선했다. MAIN 포인터와 GENOS 리비전은 유지한다. 이전456 또는455 factory로 복귀할 수 있다. 운영 승격은 별도 holdout·승격 절차가 필요하다.'),('재현 명령','동결 후보의35단위/계약검사 PASS, snapshot/pre-call 검증 PASS. 완료 run/score 덮어쓰기는 거부한다. 후속 비교는 새ADR로 분기한다. [최종 검증](VALIDATION.md).')]
(D/'README.md').write_text('---'+front+'---\n\n# 공통 탐색 상태와 다중 조문 종합의 전송 호환성\n'+''.join(f'\n## {i}. {h}\n\n{body}\n' for i,(h,body) in enumerate(sections,1)))
(D/'RESULT.md').write_text('# 구현 및 검증 결과\n\n'+summary+'\n\n'+table+'\n\n[구현과 호출 방법](GUIDE.md) · [전체 기록](실험/README.md) · [조건과 한계](README.md)\n')
(D/'VALIDATION.md').write_text('# 검증\n\n동결 후보35 tests PASS. snapshot/pre-call validate PASS. 입력drift='+str(m['input_drift'])+'. 사전품질기준='+str(m['success_criteria_pass'])+'. 최종ADR검증결과는다음에기록.\n')
index=R/'04_EXPERIMENTS/ADR/README.md';s=index.read_text().replace('ADR-0457 Gemini 질문 해석·표현 매핑 실험','ADR-0457 공통 탐색 상태와 다중 조문 종합').replace('ADR-0456 Gemini 질문 해석·표현 매핑 실험','ADR-0456 공통 탐색 상태 구현');index.write_text(s)
finalize.inventory();print(summary);print(table)
