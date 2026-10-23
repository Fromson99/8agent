from common import *
o=read(ART/'observations.json')['by_arm']['candidate']
review={'verdict':'종료 조립·122검사 통과; ASSESS 부족이 목표에 미반영되어 실제 재조사 실패', 'criteria_met':False,'reference_model_calls':0,
'findings':[
'기존 탐색 호출의 목표 갱신을 유지하고, 모든 목표가 종료 의견이며 연결·인용 게이트를 만족하면 도구 제안 대신 FINISH를 조립한다. 원래 모델 의견·제안과 보정 이유를 함께 저장한다. 별도 목표 모델 호출0회다.',
'동일 제품 후보503파일에서122검사를 통과했다(113개와 수정한 API fixture9개). 최초 fixture 실패와 재검사 이력은 보존했다. 종료 조립·근거 검증·중복·재개·연결 게이트를 포함한다.',
f'실제 질문은 HTTP{o["service_status"]}, 9호출, 입력{o["usage"]["input_tokens"]}·출력{o["usage"]["output_tokens"]}토큰, 보고비용${o["usage"]["cost_usd"]}, 서비스{o["native_result"]["seconds"]:.3f}초였다. 원문95검사 일치·권한범위 위반0, 연결 목록 반복0이다.',
'목표 갱신3건은 모두 기존 탐색 호출에 포함됐다. 호출4의 ANSWERABLE+BROWSE_STRUCTURE 모순은 새 호출 없이 FINISH로 조립됐다. 이 단계의 수정 호출0회다.',
'그러나 호출5 ASSESS가 시행령 세부 내용 부족을 발견해 재조사를 요청한 뒤에도 current_goals는 과거 ANSWERABLE 상태였다. 호출6과 수정7에서 모델은 ANSWERABLE+LOCATE를 반복했다. 기존 검증이 실행을 막아 MODEL_DECISION_UNRESOLVED로 제한 답변에 도달했다. 시행령163조 원문 미확보다.',
'총9호출은 사전7호출 이하 목표를 넘었고 전체 성공 기준은 실패다. 종료 조립의 정상 동작과 질문 답변의 충분성은 구분한다. ASSESS의 검증된 부족을 현재 목표에 연결하는 후속 후보가 필요하다.',
'작업 제품 코드·MAIN102·GENOS는 변경하지 않았다.'
], 'interpretation':'검증된 종료 의견의 기계적 행동 조립은 실제로 불필요한 수정 호출을 제거했다. 후속 ASSESS 의견과 재탐색 목표의 연결이 빠져 재조사에 실패했다. 과거 충분성 의견과 새 부족 의견을 함께 보존하는 목표 갱신이 필요하다.',
'limitations':['알려진 질문1개·승인 gold 없음·out-of-sample 아님. 법률 품질 인증·승격 근거가 아니다.','별도 목표 모델 호출0회와 모든 종류의 수정 호출0회는 다르다. 전체 수정 호출은1회였다.','후보만 변경했다. 작업 제품·MAIN102·GENOS 미반영.','전역 graph의 기존9개 오류는 별도로 기록한다.'],
'error_taxonomy':[{'type':'other','count':1,'reason':'ASSESS missing-source reentry not reflected in goal context; repeated ANSWERABLE+LOCATE rejected.'},{'type':'required_issue_omission','count':1,'reason':'Delegated detail not read; operational targets missed.'}]}
save(ART/'manual-review.json',review)
