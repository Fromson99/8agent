"""r11 (ADR-1523): the 대사 must not stop because rows asked together each carried the follow-up's read list.

ADR-1523 liquidity: four rows were asked to the external side in one follow-up; each row stored the 300 original IDs
that follow-up read (22 KB each), the item list grew to 104 KB and every model input over the 94 KB limit, so item
review stopped the whole 대사 with "시스템 오류로 멈춤". The same run had 1,244 originals of 3 documents; the
evidence check re-read the document and re-scanned every original for each one, and the report's original check
ran past its 30 s window.
"""
import json
from types import SimpleNamespace


def test_rows_asked_together_keep_the_follow_up_reads_once(monkeypatch):
    from workflow.risk_team_compare_workflow import task_board
    ids = [f'E{n:04d}' + 'x' * 60 for n in range(300)]
    issues = [{'id': f'I{n}', 'label': f'항목{n}', 'concept': {'pair_status': 'INTERNAL_ONLY', 'label': f'항목{n}',
                                                              'external_task': f'외규 과제 {n}', 'internal_task': ''}}
              for n in range(4)]
    state = {'scope': {'issues': issues}, 'rag_attempts': {'external': {'evidence_ids': ['OLD']}}}

    def ask_side(ctx, state, side, question, reason):
        state['rag_attempts'][side] = {'evidence_ids': ['OLD', *ids]}
        return True

    monkeypatch.setattr(task_board.retrieval, 'ask_side', ask_side)
    monkeypatch.setattr(task_board, 'time_left_for_more', lambda ctx: True)
    monkeypatch.setattr(task_board, 'calls_left_for_followup', lambda ctx, state, reviews: True)
    task_board.fill_unpaired(SimpleNamespace(repo=SimpleNamespace(save=lambda state: None)), state)

    assert list(state['followup_reads'].values()) == [sorted(ids)]
    for issue in issues:
        followup = issue['concept']['followup']
        assert followup['status'] == 'ASKED' and followup['read_count'] == 300 and 'evidence_ids' not in followup
        assert task_board.followup_ids(state, issue['concept']) == sorted(ids)
    # The rows in every model input stay small (they were 4 x 22 KB).
    assert len(json.dumps(state['scope'], ensure_ascii=False)) < 3000


def test_a_run_saved_before_r11_still_finds_its_follow_up_reads():
    from workflow.risk_team_compare_workflow import task_board
    assert task_board.followup_ids({}, {'followup': {'status': 'ASKED', 'evidence_ids': ['E1', 'E2']}}) == ['E1', 'E2']
    assert task_board.followup_ids({}, {'followup': {'status': 'NOT_ASKED', 'reason': 'BUDGET'}}) == []
    assert task_board.followup_ids({}, {}) == []


def test_the_evidence_check_reads_each_document_once_with_the_same_values():
    from semantic_runtime.legal_agent.source_recall import spans_complete
    from semantic_runtime.workflow_bridge import SourcePort
    sources = {'S1': {'id': 'S1', 'blocks': [{'block_id': 'b1', 'text': 'abcdef'}]},
               'S2': {'id': 'S2', 'blocks': [{'block_id': 'b2', 'text': 'ghijkl'}]}}
    span = lambda block, a, z, text: {'block_id': block, 'start_cp': a, 'end_cp': z, 'text': text}
    values = [{'evidence_id': 'E1', 'source_id': 'S1', 'document_id': 'D1', 'metadata': {'document_name': 'd1'},
               'spans': [span('b1', 0, 3, 'abc')]},
              {'evidence_id': 'E2', 'source_id': 'S1', 'document_id': 'D1', 'metadata': {'document_name': 'd1'},
               'spans': [span('b1', 3, 6, 'def')]},
              {'evidence_id': 'E3', 'source_id': 'S2', 'document_id': 'D2', 'metadata': {'document_name': 'd2'},
               'spans': [span('b2', 0, 2, 'gh')]}] * 50
    reads = []

    def execute(sql, args):
        reads.append(args[0])
        return SimpleNamespace(fetchone=lambda: (json.dumps({'document_metadata': {'document_title': '문서 ' + args[0]}}),))

    port = SimpleNamespace(
        session=SimpleNamespace(repo=SimpleNamespace(evidence=lambda: values), store=SimpleNamespace(db=SimpleNamespace(execute=execute)),
                                tools=SimpleNamespace(sources=sources), context=SimpleNamespace(request={'as_of': None})),
        categories={'D1': 'internal', 'D2': 'external'}, _check_verification_time=lambda: None)
    out = SourcePort.evidence(port)

    assert sorted(reads) == ['D1', 'D2']
    assert [e['source_complete'] for e in out] == [spans_complete(sources[e['source_id']], values) for e in values]
    assert [e['source_complete'] for e in out[:3]] == [True, True, False]
    assert [e['citation_names'] for e in out[:3]] == [['문서 D1'], ['문서 D1'], ['문서 D2']]
    assert [e['side'] for e in out[:3]] == ['internal', 'internal', 'external']


def test_an_input_over_the_limit_is_named_for_legal_users():
    from workflow.contracts import WorkflowError
    from workflow.runtime import stop_name
    name = stop_name(WorkflowError('WORKFLOW_CONTEXT_UNIT_TOO_LARGE', '질문·비교 조건이 입력 한도를 초과했습니다.'))
    assert name == 'AI에게 한 번에 넘길 수 있는 분량을 넘어 멈춤'
