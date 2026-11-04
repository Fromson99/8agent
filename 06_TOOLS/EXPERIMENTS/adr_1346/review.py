"""Post-run manual interpretation backed by exact retained records."""
from common import *
from collections import Counter

base=ART/'public-live/charter-bounded';calls=read(base/'calls.json')
turn=read(base/'turn-1/result.json');audit=read(ART/'source-wire-audit.json')['cells'][0]
trace=read(ART/'charter-navigation-trace.json.gz');counts=Counter(e['kind'] for e in trace['events'])
assert len(calls)==9 and calls[-1]['status']=='unknown' and turn['http_status']==504
assert calls[-1]['transport_diagnostics']['whitespace_only'] and calls[-1]['transport_diagnostics']['worker_reaped']
assert (ART/'STOP_EXTERNAL.json').exists() and not (ART/'public-live/charter-repeat-bounded').exists()
assert not any('supervisor' in c['stage'] for c in calls)
assert counts['READ_CANDIDATE_PAGE_HANDOFF']==1 and counts['READ_CANDIDATE_PAGE_SELECTED']==3
assert not counts['COMPLETION_ASSESSMENT_REJECTED'] and not counts['ASSESSMENT_VALIDATED']
assert all(not audit[k] for k in ('source_mismatches','acl_violations','wire_mismatches')) and audit['budget_matches']
assert {x[1] for x in audit['acquired_articles']}=={'1375','1769'}
v3=read(base/'canonical/003.json.gz')['view'];o3=read(base/'canonical/003-output.json.gz')
scope=next(s for s in v3['connection_scope_choices'] if s.get('read_action')==o3['target'])
assert o3['choice']=='FOLLOW_CONNECTION' and scope['structural_selection']['unit_id']=='1769'
dispatch=next(e for e in trace['events'] if e['kind']=='SOURCE_GOAL_DISPATCH' and e['payload']['cancelled'].get('next_action')=='FOLLOW_CONNECTION')
assert dispatch['payload']['coordinate']=='제363조' and dispatch['payload']['accepted']['next_action']=='SEARCH_STRUCTURE'
selected=[e['payload']['scope']['structural_selection']['unit_id'] for e in trace['events'] if e['kind']=='CONNECTION_SCOPE_SELECTED']
assert selected==['1375']
v9=read(base/'canonical/009.json.gz')['view']
assert v9['investigation_stop_reason']=='READ_CANDIDATE_PAGE_NO_PROGRESS'
assert {s['unit_id'] for s in v9['sources']}=={'1375','1769'} and all(s['article_complete'] for s in v9['sources'])
sys.path.insert(0,str(ROOT/read(DES/'candidate-bounded.json')['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent import journal_storage
acquired=set()
for p in (base/'runtime').rglob('*.sqlite'):
    db=journal_storage.connect(p.as_uri()+'?mode=ro',uri=True)
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if {'evidence_unit','evidence_span'}<=tables:
        for r in db.execute('SELECT u.document_id,s.block_id,s.start_cp,s.end_cp,s.text FROM evidence_unit u JOIN evidence_span s ON s.evidence_id=u.evidence_id'):
            acquired.add((r['document_id'],str(r['block_id']),r['start_cp'],r['end_cp'],r['text']))
    db.close()
delivered={(s['document_id'],str(s['block_id']),s['start_cp'],s['end_cp'],s['text']) for s in v9['evidence_options']}
assert acquired==delivered and len(delivered)==11
findings=[
 '독립2회 계획 중 첫1회 실행, 최종검토 UNKNOWN으로 두번째 미실행. 263.523초·9물리/정상8/UNKNOWN1·API504·최종답변0. 이전1344 요청을 재전송하거나 이어 실행한 것이 아니다.',
 '003 모델은433 FOLLOW_CONNECTION을 선택하면서 source_targets에363 원문도 선언했다. 원문목표 우선제어가433 연결 제안을 취소하고363 구조조회/읽기를 먼저 집행했다(SOURCE_GOAL_DISPATCH seq117/122). 이후004는363 연결을 선택했다. 실제 연결조회는363만 완료됐고433은 실행되지 않았다. 433선택 제안과433연결 실행을 동일하게 세면 안 된다.',
 '모델이363을 결의 수치 근거로 기대한 해석 자체도 부정확했다. 원문목표 선집행 후 원래 연결 경로로 돌아오지 않은 문제와 모델의 관련성 판단 문제를 분리한다. 434원문과후보는이번에확보하지못했다.',
 '005~008에서NEXT/PREV 각2번을 제안했다. 실제 이동3회 뒤4번째 반복 이동에서 READ_CANDIDATE_PAGE_HANDOFF가 발동해 기존 bounded_result/ASSESS로 넘겼다. 페이지 반복 중단의 실제 발동은 확인했으나, 이 종료는 충분한 근거 확보나 올바른 답변을 뜻하지 않는다.',
 '확보433/363의 원문18행을 중복 좌표·본문으로 합친11개 구간이009 최종검토 evidence_options의11개와 정확히 같다. 두 조문 article_complete=true, 원문/ACL/wire불일치0. 저장 영수증별 미전달 표시는 별칭/중복을 포함하므로 전체 원문 누락으로 해석하지 않는다.',
 '탐색 감독모델 호출0, 최종ASSESS 호출1이 응답불명으로 끝나 검토 거절/보완/채택은0이다. 따라서 이번 실행은 다찾은근거를감독이거절한사례가아니다. 434미확보와 최종검토 통신실패가 확인됐다.',
 '이전1325에는365 전체를 확보한 뒤 USE 범위에 불필요한 제3항까지 넣어 SCOPE_USE_UNSUPPORTED_RANGE가 반복됐고 원문만 반환됐다. 현행 completion_execution은 최종 보완 실패 시 claims=[]와INSUFFICIENT를 만들고 원문을 보존한다. 확보 실패와 검토 실패가 사용자에게 유사하게 보일 수 있는 실제 경로다. 검증기 오류 판정이 틀렸다는 뜻은 아니며 감독 추가의 인과효과를 입증한 A/B도 아니다.',
 '009는HTTP200헤더뒤 공백60조각660bytes/179.942초에UNKNOWN→API504. 로컬worker회수확인, 원격원인·취소확정·미보고비용미확인. 재전송0·두번째독립실행미착수·원문/제품/MAIN142/현장/메일변경0.',
 '호출 전 제한 실행의 준비 정지를 별도 보존하고 프로세스 종료 후 같은 동결 실행기로 준비검사를 통과했다. 준비 실패/검사 모두 실제모델0. binding.json의 상속된 parent_adr=ADR1340 문구는 설명메타오류이며 실제 코드528SHA·candidate manifest·import origin은1342동일/1346rev001이다. 원기록은 고치지 않고 이 정정 영수증을 추가한다.'
]
semantic={'all_criteria_passed':False,'verdict_ko':'미통과: 특별결의 원문 미확보·최종검토 통신중단. 페이지 반복 중단은 실제 발동 확인.',
 'conclusion_ko':'재실험에서 페이지 반복은 중단됐지만 최종검토가179.942초 공백 응답으로 끝나 답변을 완성하지 못했다. 확보한433/363 원문11개 구간은 최종검토까지 모두 전달됐다. 추가로433 연결 제안이363 원문 우선집행으로 바뀐 실행경로를 확인했다.',
 'findings_ko':findings,'planned_runs':2,'executed_runs':1,'successful_answers':0,
 'new_guard_exercise':{'page_cycle':True,'finish_supervision':False,'assessment_repair':False,'incomplete_publication':False},
 'retention':{'unique_acquired_spans':11,'assessment_delivered_spans':11,'exact_match':True,'supervisor_model_calls':0,'final_assessment_responses':0,'required_434_acquired':False},
 'error_taxonomy':[{'type':'required_issue_omission','count':1,'denominator':1,'reason':'434 not acquired; 433 connection proposal preempted by declared363 source acquisition; subsequent navigation only followed363.'},
 {'type':'other','count':1,'denominator':1,'reason':'Final ASSESS unknown at absolute deadline; no answer or review decision. Second planned run not executed.'}],
 'recommendations_ko':['원문목표 우선집행 후 미실행 연결 의도를 계속 검토할 수 있도록 보존·재제시하는 계약을 별도 설계한다. 자동정답조문 강제나 모든연결 읽기는 금지한다.',
 '최종 검토에서 원문확보·주장별근거검증·최종채택 상태를 분리하고, 실패 범위와 검증된 주장 보존 가능성을 검토한다. 실제 검증되지 않은 주장을 자동 통과시키거나 검증기를 끄지 않는다.',
 '공백응답 UNKNOWN은 별도 통신문제로 기록한다. 본실험에서추가재전송/제공자전환/제품수정없음.'],
 'no_automatic_resend':True,'main_unchanged':True,'quality_certified':False}
put(ART/'semantic-review.json',semantic)
put(ART/'connection-review-evidence.json',{'proposed433':{'choice':o3['choice'],'target':o3['target'],'scope':scope['structural_selection']},
 'preempting_source_dispatch':dispatch,'actually_inspected_scope_units':selected,'acquired_equals_assessment_unique_spans':True,'unique_spans':11,
 'event_counts':dict(counts),'last_transport':calls[-1],'binding_parent_label_correction':{'stored':'ADR-1340','actual_product':'ADR-1342 exact528','actual_candidate':'ADR-1346/bounded/rev001','raw_binding_preserved':True}})
put(ART/'skipped-cells.json',{'cells':[{'case_id':'charter-repeat','status':'NOT_EXECUTED','reason':'Frozen global stop after unknown provider outcome','physical_calls':0}]})
print(semantic['conclusion_ko'])
