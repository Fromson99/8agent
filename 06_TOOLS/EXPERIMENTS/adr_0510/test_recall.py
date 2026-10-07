"""Synthetic boundary checks; no public evaluation inputs or gold."""
import pytest
from conftest import term_glossary
from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import session
from semantic_runtime.legal_agent.source_recall import spans_complete, evidence_packets, query_variants
from semantic_runtime.legal_agent.errors import ContractError

def source():
    return {'id': 'a', 'blocks': [{'block_id': '1', 'text': 'abcdef'}, {'block_id': '2', 'text': 'exception'}]}

def evidence(spans, ident='e'):
    return {'evidence_id': ident, 'source_id': 'a', 'document_id': 'd', 'unit_id': '1',
            'generation_id': 'g', 'source_artifact_hash': 'h', 'text_hash': 't', 'metadata': {},
            'spans': [{'block_id': b, 'start_cp': a, 'end_cp': z, 'text': t} for b,a,z,t in spans]}

def test_partial_article_is_not_complete():
    assert not spans_complete(source(), [evidence([('1',0,6,'abcdef')])])

def test_gap_cannot_be_hidden_by_duplicate_spans():
    spans=[('1',0,2,'ab'),('1',3,6,'def'),('2',0,9,'exception')]
    assert not spans_complete(source(), [evidence(spans), evidence(spans)])

def test_multiple_pages_cover_the_complete_article():
    assert spans_complete(source(), [evidence([('1',0,3,'abc')]), evidence([('1',3,6,'def'),('2',0,9,'exception')])])

def test_packets_keep_exact_evidence_across_page_boundary():
    es=[evidence([('1',0,6,'abcdef')],str(i)) for i in range(5)]
    packets=evidence_packets('q',es,limit=700)
    assert len(packets)>1
    assert [e for p in packets for e in p['evidence']]==es
    assert all(p['delivery_status']=='PREPARED_NOT_SENT' for p in packets)

def test_single_oversize_evidence_fails_without_truncation():
    with pytest.raises(ContractError):
        evidence_packets('q',[evidence([('1',0,1000,'x'*1000)])],limit=700)

def test_queries_use_only_original_question_strings():
    q='질문은?\n(업무 문맥: 맥락)'
    assert query_variants(q)==[q,'맥락','질문은?']

def test_existing_session_acquires_sources_without_model_or_adoption(tmp_path,generation):
    with session(tmp_path,generation,question='모의승인규정 제1조의 승인 대상은?') as s:
        result=s.prepare_source_recall()
        assert result['read_complete']
        assert result['read_complete']==result['prepared_complete']
        assert all(e['document_id']=='d' for p in result['packets'] for e in p['evidence'])
        assert not s.gateway.transport.calls
        assert not s.work.heads('source_selection',current=True)
        assert s.work.db.execute('SELECT count(*) FROM presentation').fetchone()[0]==0
        before=s.work.budget()
        assert s.prepare_source_recall() is result
        assert s.work.budget()==before
