"""Synthetic contract checks, not a Gemma quality evaluation."""
from conftest import term_glossary
from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import session
from test_tool_exploration_v3 import read, delivered, tool
from semantic_runtime.legal_agent import question_obligations as obligations


def test_phase_skill_is_loaded_without_maintenance_records():
    assert '검색 스킬 공통 규칙' in obligations.SYSTEM
    assert 'cursor=null' in obligations.PROMPTS['investigate']
    assert 'draft_quote' in obligations.PROMPTS['review']
    assert 'draft_quote' not in obligations.PROMPTS['select_sources']
    assert 'ADR0508' not in obligations.SYSTEM + str(obligations.PROMPTS)


def test_search_receipt_reaches_model_view(tmp_path, generation):
    with session(tmp_path, generation) as s:
        result = s.sources.execute(tool('search', target=s.sources.root, query='승인', mode='literal', cursor=None), 'query', actor='MODEL')
        assert result['search_receipt']
        view = s.view('investigate')
        assert view['last_action_results'][0]['search_receipt'] == result['search_receipt']


def test_final_selection_can_deliver_previously_unpresented_sources(tmp_path, term_glossary):
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    raw = source(tmp_path/'raw.sqlite', [('d', '모의승인규정', ['승인 조건 '+str(i) for i in range(7)])])
    build_generation(raw, term_glossary, tmp_path/'data', serving=True)
    with session(tmp_path, tmp_path/'data/generation') as s:
        for i in range(1, 8): read(s, '모의승인규정 제'+str(i)+'조', name=str(i))
        ids = {e['evidence_id'] for e in s.work.evidence()}
        assert len(ids) >= 7
        view = s.view('select_sources')
        assert {e['evidence'] for e in view['exact_evidence']} == ids
        assert view['delivery_counts']['previously_presented'] == 0
        for item in view['exact_evidence']:
            assert item['text'] == s.work.evidence(item['evidence'])['text']
        delivered(s, view)
        chosen = view['exact_evidence'][0]['source']
        s.commit_selection(view, {'choices':[{'source':chosen, 'decision':'KEEP_CORE', 'reason':'모의 승인 조건 확인'}]})
        assert s.work.heads('source_selection', current=True)
        s.select({'retrieval':s.retrieval()})
        compose=s.view('compose',required=[chosen])
        assert {e['evidence'] for e in compose['exact_evidence']} == {chosen}


def test_composition_does_not_expose_unselected_text(tmp_path, generation):
    with session(tmp_path, generation) as s:
        read(s)
        view=s.view('investigate'); delivered(s, view)
        selected=view['exact_evidence'][0]['source']
        s.commit_selection(view, {'choices':[{'source':selected,'decision':'KEEP_CORE','reason':'선택한 승인 원문'}]})
        s.select({'retrieval':s.retrieval()})
        compose=s.view('compose', required=[selected])
        assert {e['evidence'] for e in compose['exact_evidence']} == {selected}
        assert compose['exact_evidence'][0]['text'] == s.work.evidence(selected)['text']


def test_cursor_error_proposes_reset_without_executing(tmp_path, generation):
    with session(tmp_path, generation) as s:
        view=s.view('investigate')
        action=tool('search', target=s.sources.root, query='새 검색 조건', mode='literal', cursor='invalid-old-cursor')
        before=s.work.observations(100)
        corrected=s.corrective_actions(view, action)
        assert corrected and corrected[0]['args']['cursor'] is None
        assert corrected[0]['args']['query'] == action['args']['query']
        assert s.work.observations(100) == before
        s.sources.validate_action(corrected[0], set(view['offered_handles']))
