"""Synthetic state/transport/API tests. No live model or answer-quality evaluation."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.contracts import Contracts, digest
from semantic_runtime.legal_agent.context import RequestContext, question_pieces
from semantic_runtime.legal_agent.domain import DEFAULT_PROFILE, DOMAIN, profile
from semantic_runtime.legal_agent.repository import WorkRepository, text_hash
from semantic_runtime.legal_agent.errors import BudgetExhausted, ContractError, ProposalError, StaleProposal, TransportError, PublicationConflict
from semantic_runtime.legal_agent.composer import commit_draft
from semantic_runtime.legal_agent.reviewer import commit_review
from semantic_runtime.legal_agent.packer import pack
from semantic_runtime.legal_agent.gate import evaluate
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.publication import prepare, export, recover, owner_lock
from lawrag.pipeline.term_generation import build_generation
from test_document_release import source

ROOT = Path(__file__).resolve().parents[2]
BINDING = {'provider': 'fixture', 'model': 'synthetic-contract', 'adapter_version': 'fixture-v1',
           'endpoint_identity': 'no-network', 'trust_zone': 'internal', 'max_input_bytes': 500000}
PROFILE = {**DEFAULT_PROFILE, 'model_binding': BINDING}


def tool(name, **args):
    return {'tool': name, 'args': args, 'reason': '합성 계약 검사'}


def issue(text='승인 필요 여부', evidence_ids=None):
    return {'text': text, 'question_piece_ids': ['Q1'], 'required': True,
            'origin': 'source_trigger' if evidence_ids else 'question', 'evidence_ids': evidence_ids or []}


def proposal(*updates, reads=None, intent='CONTINUE'):
    return {'updates': list(updates), 'reads': reads or [], 'intent': intent, 'reason': '합성 변경안'}


@pytest.fixture
def work(tmp_path):
    request = {'question': '이사회 승인이 필요한가?', 'document_ids': ['d'], 'use_llm': True}
    query = {'id': 'query:synthetic', 'question': request['question'], 'generation_id': 'g', 'scope': {'document_version_ids': ['d']}}
    context = RequestContext.create(query, request, {'generation_id': 'g', 'store_sha256': 'a'*64,
                                    'export_allowed': False, 'scope': query['scope']}, 300)
    repo = WorkRepository(tmp_path/'journal.sqlite', context, PROFILE)
    yield repo
    repo.close()


def seed(repo, text='원칙상 승인이 필요하다.', ident='E1', *, source_id=None, start=0, block_text=None):
    e = {'evidence_id': ident, 'source_id': source_id or 'source:'+ident, 'document_id': 'd', 'unit_id': '0',
         'generation_id': 'g', 'source_artifact_hash': 'b'*64, 'text_hash': text_hash(text),
         'role': 'normative', 'temporal_status': 'unknown', 'metadata': {'document_name': '모의 규정'},
         'spans': [{'block_id': '0', 'start_cp': start, 'end_cp': start+len(text), 'text': text,
                    'block_hash': text_hash(block_text or text), 'span_hash': text_hash(text)}]}
    repo.record_observation(tool('read_node', node='synthetic', cursor=None),
        {'status': 'OK', 'items': [], 'evidence_ids': [ident]}, [e], verify=lambda value: None)
    return e


def visible_view(repo, phase='investigate', evidence_ids=()):
    view = repo.save_view(phase, {'test': 'synthetic'}, evidence_ids)
    attempt = repo.reserve_attempt(view, {}, uuid.uuid4().hex, 1, phase)
    repo.attempt_sent(attempt)
    repo.finish_attempt(attempt, 'SUCCEEDED', {'fixture': True}, {'model': BINDING['model'], 'usage': None})
    return view


def apply(repo, *updates, evidence_ids=()):
    v = visible_view(repo, evidence_ids=evidence_ids)
    return repo.apply_proposal(v, proposal(*updates), event_id=uuid.uuid4().hex)


def establish(repo):
    seed(repo)
    return apply(repo,
        {'op': 'create_issue', 'temp_id': 'tmp:i', 'issue': issue(evidence_ids=['E1'])},
        {'op': 'assess', 'temp_id': 'tmp:a', 'issue_id': 'tmp:i', 'evidence_ids': ['E1'], 'relation': 'supports', 'reason': '모의 원칙'},
        {'op': 'propose_finding', 'temp_id': 'tmp:f', 'issue_id': 'tmp:i', 'assessment_ids': ['tmp:a'], 'fact_ids': [],
         'text': '해당 판본에서는 원칙상 승인이 필요하다.', 'applicability': 'source_only'}, evidence_ids=['E1'])


def draft_and_review(repo, missing=False):
    packed = pack(repo, PROFILE)
    cited = sorted({e for f in repo.heads('finding', current=True) for e in f['payload']['evidence_ids']})
    view = visible_view(repo, 'compose', packed['evidence_ids'])
    claims = commit_draft(repo, view, {'paragraphs': [{'text': '해당 판본에서는 원칙상 승인이 필요하다.',
                              'finding_ids': packed['finding_ids'], 'evidence_ids': cited}], 'limitations': []}, packed)
    view = visible_view(repo, 'review', packed['evidence_ids'])
    review = {'claims': [{'claim_id': c, 'claim_version': 1, 'verdict': 'SUPPORTED', 'reason': '합성 원문 대조',
                         'evidence_ids': packed['evidence_ids'], 'follow_up_reads': []} for c in claims],
              'question_checks': [{'question_piece_id': 'Q1', 'claim_ids': claims, 'status': 'MISSING' if missing else 'RESOLVED',
                                   'reason': '질문 일부 누락' if missing else '직접 대조', 'follow_up_reads': []}],
              'whole_question': {'status': 'MISSING' if missing else 'RESOLVED', 'reason': '질문 전체 직접 대조', 'follow_up_reads': []}}
    commit_review(repo, view, review)
    return packed, claims


def test_server_question_ids_preserve_unicode_and_whitespace():
    text = '이사회 승인?\n😀 위임 예외는?  '
    pieces = question_pieces(text)
    assert ''.join(p['text'] for p in pieces) == text
    assert all(text[p['start_cp']:p['end_cp']] == p['text'] for p in pieces)


def test_trailing_parenthetical_context_stays_with_the_question():
    question = '어디에 해당하는가?\n(업무 문맥: 신규상장 의무보유)'
    pieces = question_pieces(question)
    assert pieces == [{'id': 'Q1', 'text': question, 'start_cp': 0, 'end_cp': len(question)}]


def test_initial_source_trigger_aliases_matching_unassessed_question_issue(work):
    seed(work)
    question_issue = {**issue('질문 쟁점', evidence_ids=['E1']), 'origin': 'question'}
    source_issue = issue('원문에서 발견한 조건', evidence_ids=['E1'])
    result = apply(work,
        {'op': 'create_issue', 'temp_id': 'tmp:q', 'issue': question_issue},
        {'op': 'create_issue', 'temp_id': 'tmp:s', 'issue': source_issue},
        evidence_ids=['E1'])
    assert result['tmp:q'] == result['tmp:s']
    heads = work.heads('issue', current=True)
    assert len(heads) == 1
    assert heads[0]['payload']['origin'] == 'question'


def test_many_question_segments_remain_reviewable_without_losing_text():
    question = '확인할 질문?\n' * 100
    pieces = question_pieces(question)
    assert len(pieces) == 64
    assert ''.join(p['text'] for p in pieces) == question
    assert all(question[p['start_cp']:p['end_cp']] == p['text'] for p in pieces)


def test_attempt_records_do_not_stale_view_and_batch_is_idempotent(work):
    view = visible_view(work)
    before = work.run()['state_revision']
    p = proposal({'op': 'create_issue', 'temp_id': 'tmp:i', 'issue': issue()})
    first = work.apply_proposal(view, p, event_id='same')
    assert work.run()['state_revision'] == before+1
    assert work.apply_proposal(view, p, event_id='same') == first
    with pytest.raises(ProposalError, match='reused'):
        work.apply_proposal(view, proposal(), event_id='same')
    with pytest.raises(StaleProposal):
        work.apply_proposal(view, p, event_id='different')


def test_atomic_rollback_and_unpresented_evidence_rejected(work):
    seed(work)
    view = visible_view(work)
    with pytest.raises(ProposalError, match='not presented'):
        work.apply_proposal(view, proposal(
            {'op': 'create_issue', 'temp_id': 'tmp:i', 'issue': issue()},
            {'op': 'assess', 'temp_id': 'tmp:a', 'issue_id': 'tmp:i', 'evidence_ids': ['E1'], 'relation': 'supports', 'reason': 'invalid'}), event_id='rollback')
    assert work.heads() == []
    assert not work.db.execute("SELECT 1 FROM event WHERE event_id='rollback'").fetchone()
    assert work.evidence('E1')


def test_retract_stales_transitive_claim_review_but_preserves_other_issue(work):
    ids = establish(work)
    other = apply(work, {'op': 'create_issue', 'temp_id': 'tmp:other', 'issue': issue('다른 쟁점')},
                  {'op': 'assess', 'temp_id': 'tmp:othera', 'issue_id': 'tmp:other', 'evidence_ids': ['E1'], 'relation': 'supports', 'reason': '다른 사용'})
    draft_and_review(work)
    apply(work, {'op': 'retract_assessment', 'assessment_id': ids['tmp:a'], 'expected_version': 1, 'reason': '예외 확인'})
    assert work.head('finding', ids['tmp:f'], current=False)['validity'] == 'STALE'
    assert all(c['validity'] == 'STALE' for c in work.heads('claim'))
    assert all(r['validity'] == 'STALE' for r in work.heads('review'))
    assert work.head('assessment', other['tmp:othera'])['validity'] == 'CURRENT'
    assert work.evidence('E1')['text'] == '원칙상 승인이 필요하다.'
    with pytest.raises(sqlite3.IntegrityError):
        work.db.execute("UPDATE evidence_span SET text='변조'")


@pytest.mark.parametrize('operation', ['revise_issue', 'split_issue', 'supersede_issue'])
def test_issue_revision_operations_invalidate_previous_judgments(work, operation):
    ids = establish(work)
    update = {'op': operation, 'issue_id': ids['tmp:i'], 'expected_version': 1, 'reason': '초기 해석 수정'}
    if operation == 'split_issue':
        update['replacements'] = [{'temp_id': 'tmp:new1', 'issue': issue('원칙')}, {'temp_id': 'tmp:new2', 'issue': issue('예외')}]
    else:
        update['issue'] = issue('수정된 질문 해석')
        if operation == 'supersede_issue':
            update['temp_id'] = 'tmp:new'
    apply(work, update)
    assert work.head('assessment', ids['tmp:a'], current=False)['validity'] == 'STALE'
    assert work.head('finding', ids['tmp:f'], current=False)['validity'] == 'STALE'
    assert work.evidence('E1')


def test_merge_preserves_required_and_question_coverage(work):
    ids = establish(work)
    other = apply(work, {'op': 'create_issue', 'temp_id': 'tmp:j', 'issue': issue('중복 질문')})['tmp:j']
    u = {'op': 'merge_issue', 'targets': [{'issue_id': ids['tmp:i'], 'expected_version': 1}, {'issue_id': other, 'expected_version': 1}],
         'temp_id': 'tmp:merged', 'issue': issue('통합된 질문'), 'reason': '중복 가설 병합'}
    bad = deepcopy(u)
    bad['issue']['required'] = False
    with pytest.raises(ProposalError, match='required'):
        apply(work, bad)
    merged = apply(work, u)['tmp:merged']
    assert work.head('issue', ids['tmp:i'])['payload']['state'] == 'SUPERSEDED'
    assert work.head('issue', merged)['payload']['required'] is True


def test_question_to_issue_link_does_not_pass_direct_answer_review(work):
    establish(work)
    packed, claims = draft_and_review(work, missing=True)
    result = evaluate(work, packed)
    assert result['control']['gate'] == 'BOUNDED'
    assert any('질문 일부 누락' in r for r in result['unresolved'])


def test_unknown_facts_never_become_stated_and_use_server_piece_ids(work):
    ids = establish(work)
    with pytest.raises(ProposalError):
        apply(work, {'op': 'attach_fact', 'temp_id': 'tmp:fact', 'issue_id': ids['tmp:i'], 'name': '금액', 'status': 'unknown', 'question_piece_ids': ['Q1']})
    fact = apply(work, {'op': 'attach_fact', 'temp_id': 'tmp:fact', 'issue_id': ids['tmp:i'], 'name': '질문 진술', 'status': 'stated', 'question_piece_ids': ['Q1']})['tmp:fact']
    assert work.head('fact', fact)['payload']['value'] == work.context.query['question']


def test_recompose_rejects_stale_assembly(work):
    ids = establish(work)
    work.save_artifact('assemble', {'fixture': True})
    work.assert_assembly_current()
    apply(work, {'op': 'revise_issue', 'issue_id': ids['tmp:i'], 'expected_version': 1, 'issue': issue('수정'), 'reason': '다른 의미'})
    with pytest.raises(ContractError, match='stale assembly'):
        work.assert_assembly_current()


class WireTransport:
    binding = BINDING

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def validate_model(self):
        return {'verified': True, 'synthetic': True, 'model': BINDING['model']}

    def send_once(self, *, body, ticket):
        self.calls.append(body)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return wire(response)


def wire(value):
    return {'status_code': 200, 'body_json': {'model': BINDING['model'], 'choices': [{'message': {
        'content': json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value}}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 20}}}


def test_retry_and_schema_repair_consume_physical_budget(work):
    transport = WireTransport([TransportError('synthetic timeout', retryable=True, unknown=True), '{invalid', proposal()])
    gateway = ModelGateway(work, work.context, PROFILE, DOMAIN, transport)
    view = work.save_view('investigate', {}, [])
    assert gateway.generate('investigate', view, 'InvestigateDecision')['updates'] == []
    assert work.budget()['model_reserved'] == 3
    assert [r[0] for r in work.db.execute('SELECT status FROM model_attempt ORDER BY created_seq')] == ['UNKNOWN', 'SUCCEEDED', 'SUCCEEDED']
    assert work.db.execute("SELECT input_tokens FROM model_attempt WHERE status='UNKNOWN'").fetchone()[0] is None


def test_investigation_cannot_spend_finalization_reserve(work):
    view = work.save_view('investigate', {}, [])
    cap = PROFILE['max_model_attempts']-PROFILE['finalization_reserve']
    for i in range(cap):
        work.reserve_attempt(view, {}, str(i), 1, 'investigate')
    with pytest.raises(BudgetExhausted):
        work.reserve_attempt(view, {}, 'extra', 1, 'investigate')
    work.reserve_attempt(view, {}, 'compose', 1, 'compose')


@pytest.fixture
def generation(tmp_path, term_glossary):
    raw = source(tmp_path/'raw.sqlite', [('d', '모의승인규정', [
        '원칙상 이사회 승인을 받아야 한다. 다만 제2조의 예외를 확인한다.',
        '적법하게 위임된 경우에는 별도 이사회 승인을 받지 않는다.']),
        ('other', '다른문서', ['이 자료는 이번 요청 범위 밖이다.'])])
    build_generation(raw, term_glossary, tmp_path/'built', serving=True)
    return tmp_path/'built/generation'


class RevisionTransport(WireTransport):
    def send_once(self, *, body, ticket):
        self.calls.append(body)
        view = json.loads(body['messages'][1]['content'])['view']
        phase = view['phase']
        entities = view['work']['entities']
        current = lambda kind: [h for h in entities if h['kind'] == kind and h['validity'] == 'CURRENT']
        evidence = view['evidence']
        outlines = [o for o in view['observations'] if o['action']['tool'] == 'list_structure']
        if phase == 'investigate':
            if not outlines:
                docs = next(o for o in view['observations'] if o['action']['tool'] == 'list_documents')['items']
                value = proposal(reads=[tool('list_structure', document=docs[0]['document'], cursor=None)])
            elif not evidence:
                assert not current('issue'), 'source discovery must not require an issue'
                value = proposal(reads=[tool('read_node', node=outlines[0]['items'][0]['node'], cursor=None)])
            elif not current('issue'):
                e = evidence[0]['evidence_id']
                value = proposal({'op': 'create_issue', 'temp_id': 'tmp:i', 'issue': issue(evidence_ids=[e])},
                    {'op': 'assess', 'temp_id': 'tmp:a', 'issue_id': 'tmp:i', 'evidence_ids': [e], 'relation': 'supports', 'reason': '원칙 확인'},
                    {'op': 'propose_finding', 'temp_id': 'tmp:f', 'issue_id': 'tmp:i', 'assessment_ids': ['tmp:a'], 'fact_ids': [],
                     'text': '해당 규정은 원칙상 이사회 승인을 요구한다.', 'applicability': 'source_only'}, intent='DRAFT')
            else:
                i = next(h for h in current('issue') if h['payload']['state'] != 'SUPERSEDED')
                a = current('assessment')[0]
                eids = [e['evidence_id'] for e in evidence]
                assert len(eids) == 2
                value = proposal({'op': 'retract_assessment', 'assessment_id': a['entity_id'], 'expected_version': a['version'], 'reason': '예외 확인으로 무조건 승인 판단 철회'},
                    {'op': 'supersede_issue', 'issue_id': i['entity_id'], 'expected_version': i['version'], 'temp_id': 'tmp:i2',
                     'issue': issue('승인 원칙과 위임 예외', eids), 'reason': '원문에 따른 쟁점 교체'},
                    {'op': 'assess', 'temp_id': 'tmp:a2', 'issue_id': 'tmp:i2', 'evidence_ids': eids, 'relation': 'qualifies', 'reason': '원칙과 예외 함께 확인'},
                    {'op': 'propose_finding', 'temp_id': 'tmp:f2', 'issue_id': 'tmp:i2', 'assessment_ids': ['tmp:a2'], 'fact_ids': [],
                     'text': '해당 판본은 원칙상 승인을 요구하지만 적법하게 위임된 경우 별도 승인을 요구하지 않는다.', 'applicability': 'conditional'}, intent='DRAFT')
        elif phase == 'compose':
            findings = current('finding')
            value = {'paragraphs': [{'text': f['payload']['text'], 'finding_ids': [f['entity_id']], 'evidence_ids': f['payload']['evidence_ids']} for f in findings], 'limitations': []}
        else:
            claims = current('claim')
            revised = any('위임' in c['payload']['text'] for c in claims)
            reads = [] if revised else [tool('read_node', node=outlines[0]['items'][1]['node'], cursor=None)]
            value = {'claims': [{'claim_id': c['entity_id'], 'claim_version': c['version'],
                'verdict': 'SUPPORTED' if revised else 'NEEDS_RESEARCH', 'reason': '원칙과 예외 대조' if revised else '인용된 예외 원문 미확인',
                'evidence_ids': c['payload']['evidence_ids'], 'follow_up_reads': reads} for c in claims],
                'question_checks': [{'question_piece_id': p['id'], 'claim_ids': [c['entity_id'] for c in claims],
                    'status': 'RESOLVED' if revised else 'MISSING', 'reason': '질문과 답변 직접 대조', 'follow_up_reads': []} for p in view['question_pieces']],
                'whole_question': {'status': 'RESOLVED' if revised else 'MISSING', 'reason': '질문 전체 대조', 'follow_up_reads': []}}
        return wire(value)


def make_app(tmp_path, generation, transport=None, execution_profile=None):
    return create_app(tmp_path, generation, contracts_root=ROOT, implementation='legal-agent-v1',
                      provider=object(), legal_agent_profile=execution_profile or PROFILE,
                      legal_agent_transport=transport or RevisionTransport())


def test_http_research_retraction_revision_publication_and_feedback(tmp_path, generation):
    transport = RevisionTransport()
    app = make_app(tmp_path, generation, transport)
    with TestClient(app) as client:
        result = client.post('/v1/rag/ask', json={'question': '이사회 승인이 필요한가?', 'document_ids': ['d']})
        assert result.status_code == 200, result.text
        value = result.json()
        assert '위임' in value['answer']['text'] and len(value['answer']['claims']) == 1
        assert value['assembly']['term_agent']['final'] is True
        assert len(value['assembly']['context']) == 2
        assert client.post('/v1/rag/feedback', json={'run_id': value['run_id'], 'signal': 'MISSING_EVIDENCE', 'reason': '합성 검사'}).status_code == 200
        assert client.get('/health').json()['rag_mode'] == 'legal-agent-v1'
        assert client.get('/v1/rag/links/summary').status_code == 200
        assert client.get('/v1/rag/links', params={'source_id': value['answer']['claims'][0]['source_ids'][0]}).status_code == 200
        count = len(transport.calls)
        assert client.get('/v1/rag/search', params={'q': '승인', 'doc_id': 'd'}).status_code == 200
        meta = client.post('/v1/rag/ask', json={'question': '승인', 'document_ids': ['d'], 'use_llm': False})
        assert meta.status_code == 200, meta.text
        assert not meta.json()['answer']['claims'] and len(transport.calls) == count
        assert client.post('/v1/rag/ask', json={'question': '승인', 'document_ids': ['not-found']}).status_code == 422
    journals = list((tmp_path/'90_RUNTIME/semantic/legal-agent/runs').glob('*/*/journal.sqlite'))
    path = next(p for p in journals if p.parent.name == value['run_id'])
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM run').fetchone()[0] == 'COMPLETED'
        assert db.execute('SELECT query_id FROM run').fetchone()[0] == value['query']['id']
        assert db.execute("SELECT count(*) FROM stage_artifact WHERE stage='retrieve'").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM entity_head WHERE kind='assessment' AND validity='RETRACTED'").fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM evidence_unit').fetchone()[0] == 2
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    saved = json.loads((tmp_path/'90_RUNTIME/semantic/runs'/(value['run_id']+'.json')).read_text())
    assert saved == value


def test_long_read_cursor_scope_and_undisclosed_evidence(tmp_path, generation):
    settings = {**PROFILE, 'max_read_chars': 12, 'page_size': 1}
    app = make_app(tmp_path, generation, execution_profile=settings)
    pipeline = app.state.pipeline
    request = {'question': '승인', 'document_ids': ['d'], 'use_llm': False}
    query = pipeline.plan(request['question'], ['d'])
    with pipeline.term_agent.open_session(request, query=query, runtime=tmp_path/'runtime') as s:
        result = s.sources.execute(tool('list_documents', query='', cursor=None))
        document = result['items'][0]['document']
        outline = s.sources.execute(tool('list_structure', document=document, cursor=None))
        node = outline['items'][0]['node']
        first = s.sources.execute(tool('read_node', node=node, cursor=None))
        assert first['status'] == 'TRUNCATED' and first['next_cursor']
        fragments = [first['items'][0]['text']]
        cursor = first['next_cursor']
        while cursor:
            page = s.sources.execute(tool('read_node', node=node, cursor=cursor))
            fragments.append(page['items'][0]['text'])
            cursor = page['next_cursor']
        assert ''.join(fragments) == '원칙상 이사회 승인을 받아야 한다. 다만 제2조의 예외를 확인한다.'
        with pytest.raises(ProposalError, match='cursor'):
            s.sources.execute(tool('list_structure', document=document, cursor=first['next_cursor']))
        with pytest.raises(ProposalError):
            s.sources.resolve('other', 'D')
        cross_cursor = first['next_cursor']
    with pipeline.term_agent.open_session(request, query=query, runtime=tmp_path/'runtime') as s:
        with pytest.raises(ProposalError, match='cursor'):
            s.sources.cursor_position(tool('read_node', node=node, cursor=cross_cursor))


def test_model_schema_errors_are_502_not_request_422(tmp_path, generation):
    transport = WireTransport(['{invalid', '{invalid'])
    app = make_app(tmp_path, generation, transport)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json={'question': '승인', 'document_ids': ['d']})
        assert response.status_code == 502, response.text
        assert response.json()['code'] == 'MODEL_PROPOSAL_INVALID'
    assert not list((tmp_path/'90_RUNTIME/semantic/runs').glob('*.json'))


def test_schema_registry_and_generated_model_protocol_match():
    from semantic_runtime.legal_agent.protocol import SCHEMA
    contracts = Contracts(ROOT)
    assert contracts.schemas['urn:8-agent:legal-agent-v1'] == SCHEMA
    assert contracts.pipeline['profiles']['document-navigation-rag-v1']['nodes'][0]['parameters']['term_agent']['implementation'] == 'document-navigation-v1'
    assert contracts.pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']['implementation'] == 'legal-agent-tools-v5'


def test_owner_lock_recovery_does_not_interrupt_live_request(work, tmp_path):
    folder = tmp_path/'journals/20260919'/work.context.run_id
    folder.mkdir(parents=True)
    # Backup creates a real second durable journal, without changing the fixture.
    db = sqlite3.connect(folder/'journal.sqlite')
    work.db.backup(db)
    db.close()
    with owner_lock(folder):
        assert recover(tmp_path/'journals', tmp_path/'runs') == []
    assert recover(tmp_path/'journals', tmp_path/'runs')[0]['status'] == 'INTERRUPTED'
