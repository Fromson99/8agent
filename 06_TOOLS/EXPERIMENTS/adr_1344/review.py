from common import *
import collections
base=ART/'public-live/charter-bounded';calls=read(base/'calls.json');turn=read(base/'turn-1/result.json')
trace=read(ART/'charter-navigation-trace.json.gz');audit=read(ART/'source-wire-audit.json')['cells'][0]
assert len(calls)==6 and calls[-1]['status']=='unknown' and turn['http_status']==504
assert calls[-1]['transport_diagnostics']['whitespace_only'] and calls[-1]['transport_diagnostics']['received_bytes']==660
assert (ART/'STOP_EXTERNAL.json').exists() and not (ART/'public-live/charter-repeat-bounded').exists()
counts=collections.Counter(e['kind'] for e in trace['events'])
assert counts['CONNECTION_SCOPE_SELECTED']==2 and counts['SUPERVISOR_FINISH_HANDOFF']==0
assert counts['READ_CANDIDATE_PAGE_HANDOFF']==0 and not any('assess' in c['stage'] or 'supervisor' in c['stage'] for c in calls)
frames={r['number']:r for r in trace['frames']}
v5=read(base/'canonical/005.json.gz')['view'];o5=read(base/'canonical/005-output.json.gz')
scope=next(c for c in v5['connection_scope_choices'] if c.get('read_action')==o5['target'])
assert scope['structural_selection']['unit_id']=='1769' and o5['choice']=='FOLLOW_CONNECTION'
v6=read(base/'canonical/006.json.gz')['view']
incoming=next(c for c in v6['references']['dependency_cards'] if c['target']['source_id']=='article:816aee85d53f84a3b2f322dd')
assert incoming['direction']=='INCOMING' and incoming.get('read_action')
assert ('7bbe815ff43b6635','1772') not in {tuple(r) for r in audit['acquired_articles']}
assert all(not audit[k] for k in ('source_mismatches','acl_violations','wire_mismatches')) and audit['budget_matches']
assert all(g['status']=='NEEDS_SOURCE' and g['material_need'] for g in o5['answer_progress']['goals'])
from importlib import util
candidate=ROOT/read(DES/'candidate-bounded.json')['code_root'];sys.path.insert(0,str(candidate/'02_BACKEND'))
from semantic_runtime.legal_agent.connection_scope import FINISH_GUIDANCE
wire=read(base/'raw/call-006/request.json.gz')
assert FINISH_GUIDANCE in wire['messages'][0]['content']
assert 'source_inspections' in wire['messages'][1]['content']
findings=[
 '계획2회 중 첫1회 실행. 002까지361·433원문,003에서일반368원문을 추가 확보했다.004는368연결을 선택했지만NEEDS_SOURCE와예외확인필요를 유지했다.',
 '005에서433전체 FOLLOW_CONNECTION을 실제 선택했다.006 입력에는433의 OUTGOING363과 INCOMING434가 제시됐고434 READ선택지가 있었다.1341의433미선택종료 경로와 다르지만 전체정답성공이나 인과효과비교는 아니다.',
 '004/005의 잠정 answer_so_far에는 일반규정이 적용된다는 잘못된 문장이 여전히 있었다. 다만 material_need에는 다른정함/특별요건 확인을 남겨 실제 추가탐색을 이어갔다. 의미오판이 해결됐다고 보고하지 않는다.',
 '006 선택 호출이HTTP200헤더뒤 공백60조각660bytes만 전송한 채179.909초에UNKNOWN/API504로 종료됐다. 원격원인·취소확정·UNKNOWN비용은미확인, 로컬worker회수확인. 전역중단에따라두번째실행미착수·재전송0.',
 '434원문미확보·ASSESS/COMPOSE0·최종답변0. 새빠른종료차단/최종보완/미완료표시의실모델발동은미검증이며기술검사통과와분리한다. NEXT/PREV0·페이지반복중단0.',
 '원문8/전달28대조불일치0·ACL0·wire0·물리6/정상5/UNKNOWN1·예산6일치. 후보528과선택MAIN142불변. 제품수정/원문DB/현장/메일0.'
]
semantic={'all_criteria_passed':False,'verdict_ko':'전체 미통과: 통신기한 종료로 최종답변 및 두번째실행 미검증',
 'conclusion_ko':'연결 종료 검토 수정본은 정관 변경 원문의 연결을 다시 선택해 특별결의 조항434 후보까지 제시했다. 그러나 다음 선택 호출의179.909초 UNKNOWN으로246.393초에API504 종료, 최종답변0·두번째실행미착수다. 답변 성공이나 반복 안정성은 입증하지 못했다.',
 'findings_ko':findings,'planned_runs':2,'executed_runs':1,'successful_answers':0,
 'connections':{'selected_scope_unit_ids':['1403','1769'],'special_rule_candidate_presented':True,'special_rule_original_acquired':False},
 'new_guard_exercise':{'finish_supervision':False,'assessment_repair':False,'incomplete_publication':False,'page_cycle':False},
 'error_taxonomy':[{'type':'other','count':1,'denominator':1,'reason':'Provider outcome unknown at absolute deadline; final answer unavailable. Provisional general-rule inference remained unvalidated.'}],
 'technical_checks_reference':'ADR1342 new19/unique163 passed; no live answer equivalence claim', 'no_automatic_resend':True}
put(ART/'semantic-review.json',semantic)
put(ART/'connection-review-evidence.json',{'chosen_scope':scope,'offered_special_rule':incoming,'event_counts':dict(counts),'transport':calls[-1],
 'physical_budget_matches':audit['budget_matches'],'same_guidance_in_actual_wire':True,'source_inspections_in_actual_wire':True,'new_product_changes':0})
put(ART/'skipped-cells.json',{'cells':[{'case_id':'charter-repeat','status':'NOT_EXECUTED','reason':'Frozen global stop after unknown provider outcome','physical_calls':0}]})
print(semantic['conclusion_ko'])
