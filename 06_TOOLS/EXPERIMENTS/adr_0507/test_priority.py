"""Synthetic contracts for priority and exact retained text; no model quality scores."""
import json
import pytest
from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import session, decision, plan, delivered
from test_tool_exploration_v3 import tool, read
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.legal_agent.priority_matching import retained_sources


def test_priority_is_advisory_and_secondary_tools_remain_available(tmp_path,generation):
    with session(tmp_path,generation,question='모의승인규정 제1조 승인 요건은?') as s:
        v=s.view('investigate');q=v['question_matches']
        assert q['ordering_is_advisory'] and q['secondary_tools_allowed']
        assert q['matches']['explicit_structure']
        action=tool('search',target=s.sources.root,query='승인',mode='literal',cursor=None)
        s.sources.validate_action(action,set(v['offered_handles']))
        assert not s.work.evidence()  # constructing hints never reads every occurrence
        assert not s.work.observations()


def test_term_selection_lists_articles_before_reading(tmp_path,term_glossary):
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    raw=source(tmp_path/'terms.sqlite',[('d','모의승인규정',['영업일에 승인한다.'])])
    build_generation(raw,term_glossary,tmp_path/'terms',serving=True)
    with session(tmp_path,tmp_path/'terms/generation',question='영업일') as s:
        v=s.view('investigate')
        entries=s.sources.priority_matching.matches['body_terms']
        assert entries
        action=entries[0]['inspect_action']
        result=s.sources.execute(action,'term-selection',actor='MODEL',view_id=v['view_id'])
        assert result['items'] and result['items'][0]['document_name']
        assert result['items'][0]['read_action']
        assert not result['evidence_ids'] and not s.work.evidence()


def test_unmatched_can_fallback(tmp_path,generation):
    with session(tmp_path,generation,question='zzunmatched991?') as s:
        v=s.view('investigate')
        s.sources.validate_action(tool('search',target=s.sources.root,query='승인',mode='literal',cursor=None),set(v['offered_handles']))


def test_read_without_model_delivery_is_retained(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s)
        found=retained_sources(s)
        assert found and all(not x['model_presented'] for x in found)
        assert all(not x['citation_eligible'] for x in found)
        for c in found:
            e=s.work.evidence(c['evidence_id'])
            assert c['text']==e['text'] and c['spans']==e['spans']
        meta=s.metadata();assert meta['found_sources']==found
        assert meta['question_matches']['candidate_count']==len(s.sources.priority_matching.candidates)


def test_input_omission_is_not_lost_or_claimed_presented(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);ids=[e['evidence_id'] for e in s.work.evidence()]
        s.work.event('SOURCE_INPUT_OMITTED',{'evidence_ids':ids,'reason':'MODEL_INPUT_OR_PAGE_LIMIT'})
        cards=retained_sources(s)
        assert all(c['status']=='READ_NOT_PRESENTED_INPUT_LIMIT' for c in cards)
        assert all(c['text'] and not c['model_presented'] for c in cards)


def test_schema_not_duplicated_and_exact_delivery_guard(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);v=s.view('investigate')
        req=s.gateway.request('investigate',v,'TurnDecision')
        payload=json.loads(req['messages'][1]['content'])
        assert 'output_schema' not in payload
        assert req['response_format']['json_schema']['schema']
        assert len(json.dumps(req,ensure_ascii=False).encode())<s.gateway.transport.binding['max_input_bytes']
        with pytest.raises(ProposalError):
            s.work.visible(v['view_id'],[e['evidence_id'] for e in s.work.evidence()])


def test_real_packing_omits_whole_source_but_retains_exact_text(tmp_path,term_glossary):
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    text='영업일에 승인한다. '+('긴 원문 조건을 보존한다. '*350)
    raw=source(tmp_path/'long.sqlite',[('d','모의승인규정',[text])])
    build_generation(raw,term_glossary,tmp_path/'long',serving=True)
    with session(tmp_path,tmp_path/'long/generation',question='제1조') as s:
        c=s.sources.priority_matching.candidates[0]
        s.sources.execute(tool('read',**c['read_action']['args']),'long-read',actor='MODEL')
        before=retained_sources(s);assert before
        s.profile['max_context_chars']=6500
        v=s.view('investigate')
        assert v['omitted_counts']['exact_evidence']>0
        after=retained_sources(s)
        assert [x['text'] for x in after]==[x['text'] for x in before]
        assert any(x['status']=='READ_NOT_PRESENTED_INPUT_LIMIT' for x in after)
        assert not any(x['model_presented'] for x in after)
