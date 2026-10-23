from common import *
o=read(ART/'observations.json')['by_arm']['candidate']
review={'verdict':'목표·검토 부족 연결137검사 통과; 실제 수정 호출0이나 첫 필수 본문 읽기 전 중단', 'criteria_met':False,'reference_model_calls':0,
'findings':['기존 탐색 호출에 요구별 목표·근거·부족·다음 행동을 포함했다. 검토의 부족은 현재 목표 실행 상태에 반영하고 탐색의 충분성 의견도 별도로 보존한다. 별도 목표 모델 호출0회다.',
'검증된 ASSESS 요구에 연결된 도구는 재판단 문구를 다시 생성하지 않고 진행할 수 있다. 원래 요구·실제 저장된 검토·세대·권한·색인 결속을 검사하며 같은 요청 재개는 추가 호출 없이 재사용한다.',
'후보504파일137검사 통과. API 재조사 fixture의 초기 오류와 target_binding_hash 해석 수정 이력은 보존했다. 해당 합성 재조사 fixture만 no_progress3이며 실제 실행은 기존2다.',
f'실제 HTTP{o["service_status"]},9호출,입력{o["usage"]["input_tokens"]}·출력{o["usage"]["output_tokens"]}토큰,비용${o["usage"]["cost_usd"]},서비스{o["native_result"]["seconds"]:.3f}초. 별도 목표 호출0·수정 호출0·연결 목록 반복0·원문95검사 일치·범위 위반0.',
'목표 갱신5건과 종료 조립1건이 기록됐다. 호출5 검토가 시행령 부족을 제시하자 호출6 목표가 NEEDS_SOURCE로 바뀌고 시행령163조 LOCATE가 실행됐다. 이전 후보의 같은 판단 충돌 수정 반복은 없어졌다.',
'호출7은163조 하위 본문 READ를 선택했지만 모델이 직전 두 단계 모두 NO_CHANGE라고 보고했다. 목표 무진전2회 중단이 첫 필요 본문 읽기 전에 발동해 READ는 실행되지 않았다. NO_ANSWER_PROGRESS 제한 답변이다. 구조 위치 탐색과 첫 원문 조회 사이의 중단 자격 보완이 필요하다.',
'운영9호출/입력304086이하 목표는 충족했지만 필수 세부 원문 확보는 실패하여 전체 성공 판정은 하지 않는다. 작업 코드·MAIN102·GENOS는 이 후보 종료 시점에 변경하지 않았다.'],
'interpretation':'요구 갱신과 ASSESS 재조사의 연결은 동작했으나 모델의 무진전 의견만으로 아직 시도하지 않은 원문 READ를 차단했다. 이미 검토가 확정한 필수 부족에 대해 제공된 첫 원문 조회는 기존 예산 안에서 허용해야 한다.',
'limitations':['알려진 질문1개·승인 gold 없음·out-of-sample 아님·법률 품질 미인증.','실제 필수 본문 READ 이전 중단을 후속 ADR로 보완한다.','MAIN102·GENOS 미변경. 작업 코드 통합은 후속 검증 후 별도 기록한다.','전역 graph 기존9오류는 별도 보존한다.'],
'error_taxonomy':[{'type':'other','count':1,'reason':'NO_ANSWER_PROGRESS preempted first offered READ for an unattempted material ASSESS target.'}]}
save(ART/'manual-review.json',review)
