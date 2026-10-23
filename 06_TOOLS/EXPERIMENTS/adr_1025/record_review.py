from common import *
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');C=ROOT/s['roots']['candidate'];prior=ROOT/s['parent']
assert all(sha(C/n)==h for n,h in f['files']['candidate'].items())
assert f['files']==read(prior/'artifacts/design-freeze.json')['files']
o=read(ART/'observations.json')['by_arm']['candidate'];g=read(ART/'guard-result.json')['outcomes'][0]
assert o['native_result']['model_calls']==1 and read(ART/'stop.json')['status_code']==429
findings=[
 '사용자 재실험 요청에 따라 ADR1023 최종 후보501파일을 모두 동일한 해시로 동결해 새 ADR1025에서 실행했다. 코드·프롬프트·모델·질문·데이터·호출 한도를 변경하지 않았다.',
 '질문: 양도차익을 산정할 때 양도가액에서 공제되는 경비는 무엇인가? 실제 service.service → API → request-entry 첫 외부 모델 호출이429로 실패했다. 서비스 응답503, 실패 원인technical, 연결 조회0회·원문 회수0건·답변 생성0회다.',
 '제공자 원문은 Parasail의 upstream_provider_shared_pool 일시 rate limit을 명시한다. Qwen3.8 / qwen/qwen3.8-27b, Parasail FP8 단독, reasoning none 설정을 유지했다. 전송 재시도·다른 제공자 fallback·추가 모델 호출은0회다.',
 f"물리1호출, 서비스{o['native_result']['seconds']:.3f}초, 초기화 포함{g['seconds']:.3f}초, 감시 최대RSS {g['peak_rss_bytes']/1024**3:.3f}GiB. 사용량 보고0/1회여서 실제 입력·출력 토큰과 비용은 미확인이다. 합계 필드0은 보고값이 없는 빈 합계이며 실제0사용량이나 무료 실행을 뜻하지 않는다.",
 '이번 실행도 탐색 시작 전 중단됐다. 동일 목록 반복 차단·97조→시행령163조 도달·자발적 FINISH·호출 수와 토큰 개선 효과는 미검증이다. 사전 전체 성공 기준은 충족하지 못했다.',
 '이전107개 계약/API 검사 통과 기록은 같은501파일 해시로 결속했다. 이번에는 코드 변경이 없어 해당 검사를 다시 돌리지 않았다. 작업 제품 코드·선택 MAIN102·GENOS는 변경하지 않았다. 이전 실패와 이번 원시 입출력·저널·자원 감시 결과를 별도로 보존했다.'
]
limitations=['알려진 공개 질문1개를 대상으로 한 probe이며 승인된 법률 정답 gold나 미사용 평가셋이 없다. decision_eligible=false, quality_certified=false다. 이번 결과는 제공자 오류 관측이며 RAG 품질·성능 개선의 증거가 아니다.',
 '전체 graph에 남아 있던 기존9개 이력 오류는 이번 작업 범위가 아니다. 이번 ADR의 구조·후보 검증과 graph 결과를 final-checks.json에 기록한다.']
save(ART/'manual-review.json',{'verdict':'동일 후보 재실험 첫 호출429; 연결 탐색·종료 효과 미검증','criteria_met':False,'user_problem_fully_resolved':False,'reference_model_calls':0,'findings':findings,'interpretation':'재실험은 실행했지만 제공자 공유 풀 제한으로 첫 요청이 거절됐다. 탐색 경로가 실행되지 않았으므로 개선 성공/실패를 판단할 근거가 없으며 추가 반복하지 않았다.','limitations':limitations,'error_taxonomy':[{'type':'other','count':1,'reason':'Parasail upstream shared-pool429 before investigation'}]})
