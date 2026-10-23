from common import *
o=read(ART/'observations.json')['by_arm']['candidate'];g=read(ART/'goal-review.json');c=read(ART/'cycle-review.json')
assert read(ART/'contract-verification.json')['tests_passed']==113
review={'verdict':'목표 갱신 단일 호출 구현·113검사 통과; 실제 목표/행동 모순 반복으로 종료해 실측 기준 미달',
'criteria_met':False,'reference_model_calls':0,
'findings':[
'ADR1026의 연결 반복 차단·근거 위치 검증을 보존하고 answer_progress.py와 decision_projection.py를 확장했다. 기존 탐색 선택 호출이 원래 요구마다 현재 답·근거·필수 부족·다음 조회의 답변 변화를 갱신한다. 별도 목표 모델 호출은 추가하지 않았다.',
'모델이 원래 요구를 빠뜨리거나 생성하지 못하게 검사하며 ANSWERABLE인 요구의 추가 도구와 NEEDS_SOURCE인 요구의 종료를 거절한다. 조회 missing_need는 검증된 목표의 material_need에서 시스템이 조립한다. 목표 상태·카운터·receipt를 요청/권한/상태에 결속하고 해시 검증·재개·동일 요청 재사용을 유지한다.',
'동일 후보502파일의113검사 통과(74+39). 실제 API 정상 경로는 entry + 행동당1호출 + ASSESS임을 검사했고, 연결 반복·조기 종료 게이트·잘못된 위치·ACL·상태 변조·반복 충돌·예산·재개 검사도 포함한다.',
f'실제 동일 질문: HTTP{o["service_status"]}, 물리{o["native_result"]["model_calls"]}호출, 입력{o["usage"]["input_tokens"]}·출력{o["usage"]["output_tokens"]}토큰, 보고 비용${o["usage"]["cost_usd"]}, 서비스{o["native_result"]["seconds"]:.3f}초. 전7회 사용량이 기록됐다.',
'기존 행동 선택 호출에서 목표 갱신2건을 채택했다. 별도 목표 갱신 호출0회, 연결 목록 동일 범위 반복0회, 원문 검사95건 모두 일치·범위 위반0이다.',
'실제 경로는92조②1 연결 확인 →97조 읽기다. 호출4에서 모델은 목표를 ANSWERABLE로 쓰면서 BROWSE_STRUCTURE를 제안했다. 코드가 이 모순을 거절했고 기존 수정 호출5에서도 같은 모순이 반복돼 MODEL_DECISION_UNRESOLVED로 검토에 넘겼다. 해당 추가 탐색 도구는 실행되지 않았다.',
'이후 ASSESS도 법97조의 세 가지 범주로 답할 수 있다고 판단했다. 시행령163조 미확보·모델 FINISH 없음·제한 답변으로 사전 실측 성공 기준은 실패다. 비용 감소를 정상 종료 개선이나 법률 품질 통과로 해석하지 않는다.',
'후속 보완은 ANSWERABLE 목표와 추가 도구의 모순을 새 의미 판단으로 재호출하지 않고, 허용된 종료 게이트·검증 근거를 만족할 때 원래 모델의 충분성 판단을 기존 검토 단계에 전달하는 것이다. 이 결과와 후보는 변경하지 않고 새 ADR로 분기한다.',
'작업 제품 코드·MAIN102·GENOS는 변경하지 않았다. 감사 스크립트의 계보 ID 오기만 analyze_current.py에서 ADR1027로 바로잡았으며 동결 runner와 제품 입력·결과는 변경하지 않았다.'
],
'interpretation':'요구별 상태와 다음 행동의 구조적 결속은 실제 경로에서 동작했다. 그러나 의미 판단의 적절성은 별개이며 모델은 이미 충분하다는 의견과 모순되는 도구를 두 번 냈다. 추가 모델 수정 없이 전달할 결정적 복구가 필요하다.',
'limitations':['알려진 질문1개이며 승인된 gold·out-of-sample 평가 없음. 결정 적격·법률 품질 인증·MAIN 승격 근거가 아니다.','실제 호출7회에는 기존 충돌 수정1회가 포함된다. 별도 목표 갱신 모델 호출0과 모든 유형의 추가 호출0을 혼동하지 않는다.','후보만 변경했다. 현재 작업 코드·선택 MAIN102·GENOS에 자동 반영하지 않았다.','전역 graph 기존9개 오류는 별도 기록하며 해당 ADR 관련 여부를 최종 확인한다.'],
'error_taxonomy':[{'type':'other','count':1,'reason':'ANSWERABLE goal paired with tool proposal twice; bounded MODEL_DECISION_UNRESOLVED handoff.'},{'type':'required_issue_omission','count':1,'reason':'Predeclared delegated original reach/native FINISH criteria not met; no approved legal gold.'}]}
save(ART/'manual-review.json',review)
