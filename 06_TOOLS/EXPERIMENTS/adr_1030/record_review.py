from common import *
o=read(ART/'observations.json')['by_arm']['candidate']
review={'verdict':'동일 호출 목표 갱신·첫 필수 조회 보장148검사 통과; 실제6호출이나 시행령 세부 원문 미확보', 'criteria_met':False,'reference_model_calls':0,
'findings':['원래 요구별 목표 상태·현재 답·근거·필수 부족·다음 조회의 답변 변화를 기존 탐색 행동 선택 응답에 포함한다. 별도의 목표 갱신 모델 호출을 추가하지 않는다. 코드 갱신·검증·상태 저장·재개는 모델 호출 없이 수행한다.',
'모든 목표가 종료 의견인데 도구를 제안하면 연결·인용 게이트가 허용하는 FINISH로 조립한다. 검토 ASSESS의 새 부족은 현재 목표 실행 상태에 연결하고 이전 탐색 의견도 보존한다. 정확히 연결된 도구를 문구 수정 재호출 없이 진행할 수 있다.',
'원래 요구·저장된 검토·세대·권한·색인·원문 참조·요청 상태를 검사한다. 동일 범위 연결 목록의 반복 조회는 저장된 실행 receipt로 차단한다. 근거 없는 검토 조항 번호는 다음 조회 대상에 넘기지 않는다.',
'검토의 필수 부족에 대해 아직 본문 읽기를 시도하지 않았으면 무진전 의견2회만으로 첫 제공 READ를 막지 않는다. 부족별1개 조회 배치만 허용하며 이전 완료/실패 시도·재개·중복은 재허용하지 않는다. 의견·카운터·기존14호출/1800초 예산은 유지한다.',
'동일 후보505파일의148검사가 통과했다. 실제 API 첫 조회 허용·요청 재사용, 기존 중단·권한·상태·근거·연결 회귀를 포함한다. 최초 합성 receipt id 누락3실패와 수정 이력을 보존했다.',
f'실제 동일 질문: HTTP{o["service_status"]},6호출,입력{o["usage"]["input_tokens"]}·출력{o["usage"]["output_tokens"]}토큰,보고비용${o["usage"]["cost_usd"]},서비스{o["native_result"]["seconds"]:.3f}초. 목표 갱신3건은 기존 탐색 호출에 포함됐다. 별도 목표 호출0·수정 호출0·연결 목록 반복0·원문95검사 일치·범위 위반0이다.',
'실제 경로는92조②1 연결 확인→97조 읽기→종료 조립→검토→답변이다. 이번 검토는 추가 gap을 내지 않아 재조사 및 첫 본문 허용 분기가 실측에서 발생하지 않았다. 이 분기는 API 합성 검사로 검증했으며 실제 성공으로 세지 않는다.',
'예산/충돌/무진전 강제 중단 없이 제한 답변이 나왔지만 시행령 세부 본문은 미확보다.6호출/입력145695의 감소는 질문 품질 통과의 증명이 아니다. 필수 세부 원문 도달 기준이 미달하여 전체 성공·품질 인증·MAIN 승격을 선언하지 않는다.',
'후보 완료 시점까지 작업 제품·MAIN102·GENOS는 불변이다. 검증 코드의 후속 작업 통합은 working-integration.json과 별도 검사로 기록한다.'],
'interpretation':'목표 갱신을 기존 호출 안에 묶고 목표·행동·검토 부족을 코드로 연결했다. 호출·중복·상태 제어는 검증됐다. 모델이 질문에 필요한 상세 수준을 과소평가하는 문제는 남아 있으며, 실제 분기 미발생과 모델 의미 판단을 코드 검사 통과로 대체하지 않는다.',
'limitations':['알려진 질문1개·승인 gold 없음·out-of-sample 아님·법률 품질 미인증.','이 실측에는 ASSESS 재조사가 없었다. 최초 READ 허용의 실제 모델 경로 성공은 미검증이며 API 합성 검사를 통과했다.','재조사 API fixture의 no_progress3과 실제 no_progress2를 구분한다. 실제 예산과 기본 데이터·모델 정책은 유지했다.','활성 MAIN102·GENOS는 변경하지 않는다. 작업 통합 후에도 기본 answer_progress_control=false를 유지한다.','전역 graph 기존9오류를 보존하며 이번 ADR 관련 오류는 최종 검사한다.'],
'error_taxonomy':[{'type':'required_issue_omission','count':1,'reason':'Delegated-detail original reach criterion not met; model ASSESS returned no gaps. No approved legal gold.'}]}
save(ART/'manual-review.json',review)
