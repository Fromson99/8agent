from common import *
import collections
b=ART/'public-live/charter-bounded';trace=read(ART/'navigation-trace.json.gz');audit=read(ART/'source-wire-audit.json')['cells'][0]
frames={f['number']:f for f in trace['frames']};events=collections.Counter(e['kind'] for e in trace['events'])
calls=read(b/'calls.json');saved=read(ART/'inspection-summary.json')['saved_assessments'][0]
assert len(calls)==8 and all(c['http_status']==200 for c in calls)
assert frames[4]['output']['choice']=='FOLLOW_CONNECTION' and frames[6]['output']['choice']=='FINISH'
v4=read(b/'canonical/004.json.gz')['view'];v6=read(b/'canonical/006.json.gz')['view']
target=frames[4]['output']['target'];option=next(o for o in v4['tool_options'] if o['target']==target)
assert option['selected_scope']['structural_selection']['unit_id']=='1403'
assert any(o['choice']=='FOLLOW_CONNECTION' and o['selected_scope']['structural_selection']['unit_id']=='1769' for o in v4['tool_options'])
assert v4['connection_review']['required_before_finish'] is True and v6['connection_review']['required_before_finish'] is False
assert any(not x['selected'] and x['structural_selection']['unit_id']=='1769' for x in v6['connection_scope_choices'])
assert audit['acquired_articles']==[['7bbe815ff43b6635','1403'],['7bbe815ff43b6635','1769']]
assert not events['READ_CANDIDATE_PAGE_SELECTED'] and not events['READ_CANDIDATE_PAGE_HANDOFF']
assert read(b/'canonical/007-output.json.gz')==read(b/'canonical/008-output.json.gz')
assert saved['claims']==0 and saved['answer_coverage']=='INSUFFICIENT'
assert [x['code'] for x in saved['failure']['issues']]==['SCOPE_CLAIM_EVIDENCE','SCOPE_CLAIM_EVIDENCE']
assert '제368조의 일반 규정이 적용됩니다' in (b/'turn-1/answer.txt').read_text()
review={
 'all_criteria_passed':False,'final_answer_passed':False,'guard_exercised':False,'paging_moves':0,'paging_handoffs':0,
 'verdict_ko':'미통과: 특별결의 조문 미확보·최종 검토 보완 실패로 원문전용. 페이지 반복0, 새 중단 분기 발동0.',
 'conclusion_ko':'수정본 실제1질문은113.605초/8정상호출로 종료했지만 정답 설명을 완성하지 못했다. 이번에는433 연결을 고르지 않고368 연결만 확인해434를 놓쳤다. 후보15개/1페이지로 왕복이 없어 페이지 중단 수정의 실제 발동 효과는 미검증이다.',
 'findings_ko':[
 'call002는433 원문을 선택했고 call003은433에 결의 수치가 없다는 이유로 일반결의368을 추가 목표로 정했다. 저장 원문 확보는433·368 두 조문뿐,434는 미확보다.',
 'call004에는433 전체/제1항의 FOLLOW_CONNECTION 선택지가 실제 제시되어 있었다. 모델은368 전체 연결을 골랐다. call005 감독도 과반수·1/4 일반규정으로 충분하다는 잘못된 적용 판단을 반복하며 동일 선택을 승인했다.',
 'call006에서368 연결 목록은완료/후보15개·1페이지,433 연결은NOT_SELECTED였다. 그런데 connection_review.required_before_finish=false이고 모델이ANSWERABLE·빈material_need·FINISH를 제출해 SUPERVISOR_FINISH_HANDOFF로 최종검토에 진입했다. 의미적인 특별규정 확인 부족과 기술적 선택범위 완료를 구분해야 한다.',
 'call007 초안3주장 중C3가 일반결의 요건을 정관 변경에 적용했다. 최종 검토 실패 원인은 특별규정 누락을 탐지한 것이 아니라C3의 주장별 근거 채택 연결이 비어 발생한SCOPE_CLAIM_EVIDENCE2개다. call008 보완은 출력전체가call007과 정확히 같아 같은2오류로 거절됐다.',
 '최종 저장LIMITED_ANSWER/INSUFFICIENT·주장0·원문전용. 공개 응답에 미완료 판단 설명으로 일반규정을 적용한다는 오판 문장이 남아 있어, 주장0을 오판문구 노출0으로 해석할 수 없다.',
 'NEXT/PREV0회·페이지중단이벤트0·UNKNOWN0·예산8일치·동일요청재조회추가0. 수정된 반복 중단이 조사를 조기에 끊어434를 놓친 것은 아니다. 이번 호출에는 그 분기가 전혀 실행되지 않았다.'
 ],
 'recommendations_ko':[
 '우선 후속은 특정 조문 하드코딩이 아니라, 질문 대상 행위의 핵심 원문과 실제 확인한 연결범위가 종료 판단에서 일치하는지 검토하는 것이다. 다른 일반조문 연결 조회가 완료됐다는 사실만으로 대상행위의 특별규정 검토가 끝났다고 보지 않도록 설계한다.',
 '일반규정의 다른정함/예외 조건을 현재 행위에 적용할 수 있다는 근거를 감독·최종 검토에서 확인하고, C3 같은 설명주장도 채택 근거에 정확히 연결하거나 삭제/보류하도록 동일오류 보완 경로를 점검한다. 검증기를 제거해서 통과시키지 않는다.',
 '원문전용 응답에 잘못된 미완료 판단이 남는 표시 경로도 따로 점검해야 한다. 이번은실험/읽기전용 분석이며 추가제품수정·MAIN승격은 수행하지 않았다.'
 ],
 'error_taxonomy':[{'type':'governing_rule_selection','count':1,'denominator':1,'detail':'Applied general meeting resolution rule before examining charter-specific connected rule'}, {'type':'required_issue_omission','count':1,'denominator':1,'detail':'Required special-resolution original not acquired'}, {'type':'other','count':1,'denominator':1,'detail':'Final claim-to-adopted-evidence link failure repeated unchanged; source-only fallback'}],
 'historical_comparison':{'previous_adr':'ADR-1338','previous_seconds':199.06079813896213,'previous_calls':39,'previous_page_moves':32,'previous_final_claims':2,'current_seconds':read(b/'result.json')['turns'][0]['request_seconds'],'current_calls':8,'current_page_moves':0,'current_final_claims':0,'causal_speed_improvement_claimed':False,'reason':'Different discovered evidence/route, answer failure and additional1332/1337 working changes'}
}
put(ART/'semantic-review.json',review)
put(ART/'termination-link-evidence.json',{'chosen_connection':option,'before_connection_review':v4['connection_review'],'after_connection_review':v6['connection_review'],'after_scope_choices':v6['connection_scope_choices'],'final_failure':saved['failure'],'same_assessment_output':True,'event_counts':dict(events),'paging_guard_exercised':False})
print(review['verdict_ko'])
