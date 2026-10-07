"""Synthetic publication regressions, without model calls or legal evaluation."""
from copy import deepcopy
import pytest
from conftest import term_glossary
from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import session, drafted, review
from test_tool_exploration_v3 import delivered
from semantic_runtime.legal_agent.errors import ProposalError, TransportError
from test_legal_agent_v5_sources import article_generation


def finish(s, monkeypatch, value=None, failure=None):
    phases = []

    def generate(phase, view, name):
        phases.append(phase)
        delivered(s, view)
        if failure:
            raise failure
        return deepcopy(value)

    monkeypatch.setattr(s.gateway, 'generate', generate)
    s.next_mode = 'REVIEW'
    result, control = s.answer_and_review({
        'request': s.context.request, 'query': s.context.query,
        'retrieval': s.retrieval(), 'selection': {}, 'assembly': {}})
    assert phases == ['review']
    assert control['decision'] == 'FINAL'
    return result, control


def test_missing_relation_check_preserves_chosen_answer_with_named_articles(tmp_path, term_glossary, monkeypatch):
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    raw = source(tmp_path/'source.sqlite', [('d', '모의승인규정', [
        '승인은 제2조를 준용한다.', '승인 요건은 신청서의 제출이다.'])])
    build_generation(raw, term_glossary, tmp_path/'g', serving=True)
    with session(tmp_path, tmp_path/'g/generation') as s:
        drafted(s)
        relation = next(n for n in s.work.notices() if n['family'] == 'reference' and n['direction'] == 'outgoing')
        head = s.work.heads('claim', current=True)[0]
        paragraph = deepcopy(head['payload'])
        paragraph['relation_dependencies'] = [relation['relation_id']]
        view = s.view('compose', required=s.packed['evidence_ids'])
        delivered(s, view)
        s.commit_draft(view, {'paragraphs': [paragraph], 'limitations': []})
        v, value = review(s)
        with pytest.raises(ProposalError, match='review relation checks omitted'):
            s.commit_review(v, value)
        result, control = finish(s, monkeypatch, value)
        answer = result['answer']
        assert len(answer['claims']) == 1
        assert answer['claims'][0]['text'] == paragraph['text']
        assert control['gate'] == 'BOUNDED'
        assert '**법률 검토 필요사항**' in answer['text']
        relation_note = next(x['reason'] for x in answer['unresolved'] if '조문 사이' in x['reason'])
        assert '모의승인규정' in relation_note and '제1조' in relation_note and '제2조' in relation_note
        assert '최종 대조가 빠졌습니다' in relation_note
        assert '최종 근거에서 빠졌' not in relation_note
        assert relation['relation_id'] not in answer['text']
        assert 'relation_checks' not in answer['text']
        assert 'review relation checks omitted' not in answer['text']
        assert not s.work.heads('review', current=True)
        assert set(answer['provider_receipt']['claim_review_status'].values()) == {'UNREVIEWED'}
        assert s.work.db.execute("SELECT 1 FROM event WHERE kind='FINAL_REVIEW_ADVISORY'").fetchone()


@pytest.mark.parametrize('issue', ['quote', 'draft_quote', 'dimensions', 'missing_claim', 'missing_obligation', 'rejected'])
def test_final_review_defects_become_notes_without_hiding_claims(tmp_path, generation, monkeypatch, issue):
    monkeypatch.setenv('GENOS_RAG_RELAX_REVIEW_QUOTE_MATCH', '0')
    with session(tmp_path, generation) as s:
        drafted(s)
        _, value = review(s)
        check = value['checks'][0]
        if issue == 'quote':
            check['source_checks'][0]['quote'] = '원문에 없는 인용문'
        elif issue == 'draft_quote':
            check['source_checks'][0]['draft_quote'] = '작성하지 않은 문장'
        elif issue == 'dimensions':
            check['source_checks'][0]['dimensions']['conditions'] = 'CHANGED'
            check['source_checks'][0]['reason'] = '제출 요건의 충족 여부를 확인해야 합니다.'
        elif issue == 'missing_claim':
            value['checks'] = []
        elif issue == 'missing_obligation':
            value['obligation_checks'] = []
        else:
            check.update(verdict='NEEDS_REWRITE', reason='예외가 적용되는 대상인지 확인해야 합니다.')
            value['obligation_checks'][0]['status'] = 'NEEDS_REWRITE'
        result, _ = finish(s, monkeypatch, value)
        answer = result['answer']
        assert answer['claims'][0]['text'] == '모의 승인 대상입니다.'
        assert answer['text'].startswith('모의 승인 대상입니다.')
        assert answer['unresolved']
        assert '법률 검토 필요사항' in answer['text']
        assert 'MODEL_' not in answer['text'] and 'source check' not in answer['text']
        assert not answer['provider_receipt']['quality_certified']
        if issue == 'dimensions':
            assert '적용 요건과 요건 사이의 관계' in answer['text']
            assert '제출 요건' in answer['text']
        if issue == 'rejected':
            assert '예외가 적용되는 대상' in answer['text']
            assert 'NEEDS_REWRITE' in answer['provider_receipt']['claim_review_status'].values()


@pytest.mark.parametrize('failure', [ProposalError('structured model output invalid'), TransportError('internal URL /secret/path')])
def test_unavailable_review_keeps_draft_without_exposing_runtime_error(tmp_path, generation, monkeypatch, failure):
    with session(tmp_path, generation) as s:
        drafted(s)
        result, _ = finish(s, monkeypatch, failure=failure)
        assert result['answer']['claims']
        assert '최종 원문 대조가 완료되지 않았습니다' in result['answer']['text']
        assert str(failure) not in result['answer']['text']


def test_clean_review_has_no_spurious_legal_warning(tmp_path, generation, monkeypatch):
    with session(tmp_path, generation) as s:
        drafted(s, both=True)
        _, value = review(s, 'ANSWERED')
        result, control = finish(s, monkeypatch, value)
        # The independent source-coverage gate can remain BOUNDED; publication
        # of the clean draft must not invent a legal defect from that status.
        assert control['gate'] in ('READY', 'BOUNDED')
        assert len(result['answer']['claims']) == 2
        assert result['answer']['unresolved'] == []
        assert '법률 검토 필요사항' not in result['answer']['text']
        assert set(result['answer']['provider_receipt']['claim_review_status'].values()) == {'SUPPORTED'}


def test_new_draft_does_not_reuse_prior_review_notes(tmp_path, generation, monkeypatch):
    with session(tmp_path, generation) as s:
        drafted(s)
        _, value = review(s)
        value['checks'][0]['source_checks'][0]['quote'] = '원문에 없는 인용문'
        finish(s, monkeypatch, value)
        v = s.view('compose', required=s.packed['evidence_ids'])
        delivered(s, v)
        paragraph = deepcopy(s.work.heads('claim', current=True)[0]['payload'])
        paragraph['text'] = '새로 작성한 승인 대상입니다.'
        s.commit_draft(v, {'paragraphs': [paragraph], 'limitations': []})
        _, value = review(s)
        result, _ = finish(s, monkeypatch, value)
        assert result['answer']['claims'][0]['text'] == paragraph['text']
        assert '인용 문구가 확보한 원문과 일치하지' not in result['answer']['text']


def test_legal_coordinates_include_article_and_paragraph(tmp_path, article_generation):
    from semantic_runtime.legal_agent.final_review_notes import LegalNotes
    with session(tmp_path, article_generation) as s:
        notes = LegalNotes(s)
        label = notes.unit_label('d', '2')
        assert '제1조' in label and '제2항' in label
        assert '제2조' not in label
