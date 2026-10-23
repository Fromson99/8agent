from common import *
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');C=ROOT/s['roots']['candidate']
assert '107 passed' in (ART/'contracts-final.log').read_text()
assert all(sha(C/n)==h for n,h in f['files']['candidate'].items())
findings=[
 '직접 원인은 FOLLOW_CONNECTION을 일반 중복 검사에서 제외하고, 현재 선택 범위 외에는 이미 확인한 연결도 NOT_SELECTED로 되돌린 것이다. 행동 이력을 저장했지만 완료한 목록의 재실행 차단에는 쓰지 않았다. 이전 작업은 조기 종료와 검토 위치 출처에 집중해 A→B→A의 동일 상태 반복 검사를 놓쳤다.',
 'ADR1022의5개 모듈 수정 위에 연결 범위별 실제 조회 결과 영수증을 저장했다. 동일 요청·권한·확보 원문 범위는 목록을 재조회하지 않고 저장 결과를 재사용한다. UI 이름이나 선택 경로가 달라도 같은 원문 범위이면 중복으로 판정한다.',
 '이미 확인한 범위는 FOLLOW_CONNECTION 선택지에서 제거하고, 오래된 선택지를 직접 실행해도 실행 경계에서 거절한다. 기존 검증/수정 담당과 예산은 유지했다. 완료·부분 조회·조회 실패를 구분하고, 미확보를 부재로 바꾸지 않는다. 같은 요청에 대한 무진전 조회를 반복하는 대신 기존 구조 검색 또는 확보 범위 종료가 가능하다.',
 '모델 입력에 연결 확인 행동의 범위·이유·실제 결과·미확보 대상 수를 전달한다. 이전 범위의 저장 목록은 별도로 보존하고 필요한 원문을 직접 선택할 수 있다. 실제 READ 직전에 원래 범위와 참조 인용·endpoint·권한을 다시 검증한다. 원문 확보 상태는 현재 확보 원문으로 다시 계산한다.',
 '관련107검사가 최종 동결 코드에서 통과했다. A→B→A→B, 화면 경로만 바뀐 같은 범위, 부분/실패 조회, 새 원문 범위 허용, 무관한 원문 추가로 중복 제한 해제 금지, 오래된 도구 실행 거절, 해시·바인딩·권한 변조, 저장 후 복원, 실제 API의 이전 목록 직접 읽기·오류 제안 수정·동일 요청 재사용을 포함한다. 성공해 저장된 목록은 accepted action 복원에서도 보존하고 카운터를 초기화하지 않는다.',
 '실제 질문은 동일한 공개 필요경비 질문1회를 동결 후보의 service.service로 실행했다. 첫 request-entry 모델 호출이 제공자429로 실패해 HTTP503으로 종료했다. 물리1호출, 서비스18.928초, 준비 포함 전체34.034초, 최대RSS약2.86GiB. 추가 모델 호출·전송 재시도·fallback은0회다.',
 '실제 연결 탐색과 답변 생성은 시작하지 못했다. 따라서 실제 모델의 반복 감소·호출 수·입력 토큰·자발적 FINISH 개선은 미검증이며, 사전 전체 성공 기준은 충족하지 못했다. 사용량 보고0/1회로 실제 토큰·비용은 미확인이다. 합계 필드의0은 보고된 사용량의 빈 합계이며 무료 실행이나 실제0토큰을 뜻하지 않는다.',
 '변경은 ADR1023 격리 후보501파일에 보존했다. 작업 제품 코드·MAIN102 선택 포인터·GENOS는 변경하지 않았다. 기존 작업 변경과 이전 실패 실험을 보존했다.'
]
limitations=[
 '합성 계약/API 검증과 외부 모델 실제 성능은 다르다. 첫 제공자429로 실제 행동 효과 비교 불가. 승인된 법률 정답 gold와 미사용 평가셋이 없고 알려진 질문1개이므로 decision_eligible=false, quality_certified=false다.',
 '현재 범위의 부분 목록에는 전진하는 cursor가 없어 같은 범위의 반복 조회를 차단한다. 미확보 상태와 구조 검색 경로를 남긴다. 데이터 세대·권한·원문 바인딩은 보존하며 상태 변조를 재조회로 우회하지 않는다.',
 '전역 graph의 기존9개 이력 오류와 이전 확대 MAIN50의6개 기존 실패는 이번 수정 범위가 아니다. 현재 구조 검증·graph 결과는 final-checks.json에 기록한다.'
]
save(ART/'manual-review.json',{'verdict':'동일 연결 목록 반복 차단107검사 통과; 실제 질문 첫 제공자429로 효과 미검증','criteria_met':False,'user_problem_fully_resolved':False,'reference_model_calls':0,'findings':findings,'interpretation':'기존 예외·완료 상태 손실을 코드와 계약 검사에서 수정했다. 이번 실호출은 탐색 전 제공자 오류이므로 모델의 반복·조기 종료 개선 성공으로 보고하지 않는다. 단일 실행 결과를 보존하고 재실행하지 않았다.','limitations':limitations,'error_taxonomy':[{'type':'other','count':1,'reason':'provider429 before investigation; effectiveness unmeasured'}]})
save(ART/'regression-review.json',{'same_frozen_product_code':True,'tests_passed':107,'log':'contracts-final.log','candidate_files':501,'physical_model_calls':1,'synthetic_only_no_progress_override':'cycle/cycle_repair and gap_repair fixtures use4 to exercise deliberate conflict chains; real max_no_progress stays2','preflight_failures_preserved':['contracts-initial.log','contracts-regression.log'],'remaining_live_validation':'Provider rejected initial call429; no query navigation or answer observed.'})
