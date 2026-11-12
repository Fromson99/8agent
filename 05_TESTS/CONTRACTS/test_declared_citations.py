"""Citations written with a name the citing document declared in another article (2026-11-08).

`이 요령은 모의승인규정(이하 "규정"이라 한다)` in 제1조 makes `규정 제3조` in 제2조 a citation
of 모의승인규정 제3조. The index stores the mention but cannot name the document; the stored
reference is completed per request from the document's own declaration (no stored change)
for every consumer: the navigation connection menu, the reference tool and research locators.
"""
import json
import sqlite3

import pytest

from test_unit_fulltext_adaptive_read import unit_fts, SourceRecall
from test_document_release import source
from test_bounded_source_main import settings
from test_legal_agent_v5 import app_for
from test_unified_legal_agent import ScriptedTransport
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.legal_agent import declared_names as dn

rel = pytest.importorskip('semantic_runtime.legal_agent.unit_relations')

INSIDE = ['제1조(목적) 이 요령은 모의승인규정(이하 "규정"이라 한다)에 따라 정한다.',
          '제2조(서류) 회사는 규정 제3조에 따라 원본 서류를 첨부한다.',
          '제3조(시행) 이 규정 제1조는 공포한 날부터 시행한다.']
APPROVAL = ['제1조(승인) 승인 후 보고한다.', '제2조(보고) 보고는 5일 이내에 한다.', '제3조(서류) 신청인은 원본 서류를 첨부한다.']


@pytest.mark.parametrize('text,expected', [
    ('회사는 규정 제32조제1항에 따른다', [('규정', '제32조', '제1항')]),
    ('법 제9조 제5항제1호', [('법', '제9조', '제5항')]),
    ('이 규정 제5조에 따른다', []), ('같은 법 제3조', []), ('동법 제2조제5호', []),
    ('한국은행법 제28조', []), ('규정에서 정한 제7조', []), ('위원장 제3조', [])])
def test_citation_needs_a_declared_name_as_its_own_word(text, expected):
    declarations = [{'name': '규정', 'long_form': '이 요령은 코스닥시장상장규정', 'kind': 'CLAUSE', 'scope_text': '', 'source_id': 's1'},
                    {'name': '법', 'long_form': '자본시장과 금융투자업에 관한 법률', 'kind': 'TITLE', 'scope_text': '', 'source_id': 's1'},
                    # Declared only for one provision: not usable from another source.
                    {'name': '위원장', 'long_form': '위원회의 위원장', 'kind': 'CLAUSE', 'scope_text': '이 조에서', 'source_id': 's9'}]
    found = dn.declared_citations(declarations, [{'block_id': '1', 'text': text, 'source_id': 's2'}])
    assert [(c['name'], c['article'], c['paragraph']) for c in found] == expected


@pytest.fixture
def declared(tmp_path, term_glossary):
    raw = source(tmp_path / 'raw.sqlite', [('inside', '모의요령', INSIDE), ('d', '모의승인규정', APPROVAL)])
    build_generation(raw, term_glossary, tmp_path / 'built', serving=True)
    gen = tmp_path / 'built/generation'
    unit_fts.build(gen, gen / 'navigation', tmp_path / 'index', workers=1)
    idx = unit_fts.UnitFulltextIndex(tmp_path / 'index', json.loads((gen / 'navigation/manifest.json').read_text()))
    app = app_for(tmp_path, gen, ScriptedTransport(), settings())
    p = app.state.pipeline
    p.term_agent.unit_fulltext = idx
    request = {'question': '원본 서류 첨부', 'document_ids': ['inside', 'd'], 'use_llm': False}
    try:
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['inside', 'd']), runtime=tmp_path / 'runtime') as session:
            yield session.sources
    finally:
        p.store.close()


def stored(s, did, mention):
    rows = [json.loads(r[0]) for r in s.tools.db.execute('SELECT json FROM reference WHERE document_id=?', (did,))]
    return [r for r in rows if mention in (r.get('mention_text') or r.get('locator') or '')]


def test_stored_unresolved_reference_is_completed_from_the_documents_own_declaration(declared):
    s = declared
    refs = stored(s, 'inside', '제3조')
    assert refs and not any(r.get('targets') or str(r.get('resolution', '')).startswith('EXACT_') for r in refs), refs
    completed = [dn.upgrade_reference(s, r) for r in refs]
    completed = [r for r in completed if r]
    assert len(completed) == 1, completed
    ref = completed[0]
    assert ref['resolution'] == 'EXACT_DECLARED_NAME' and ref['declared_name']['name'] == '규정'
    assert ref['id'] == refs[0]['id'] or ref['id'] in {r['id'] for r in refs}           # same stored reference
    target = s.tools.sources[ref['targets'][0]['source_id']]
    assert target['document_id'] == 'd' and target['heading'].startswith('제3조')
    # `이 규정 제1조` (제3조 of the 요령) points at the citing document, not the declaration.
    assert all(dn.upgrade_reference(s, r) is None for r in stored(s, 'inside', '제1조'))


def test_navigation_connection_menu_offers_the_declared_target(declared):
    s = declared
    src = next(v for v in s.tools.sources.values() if v['document_id'] == 'inside' and v['heading'].startswith('제2조'))
    hit = rel.hit_for(s, src['id'], str(src['unit_id']))
    recall = SourceRecall(s)
    recall.discover = lambda: ([src['id']], {'discovery_mode': 'structure', 'routes': {}, 'unit_hits': [hit]})
    record = recall.prepare()
    groups, statuses, limits, unresolved = rel.catalog(s, [src['id']], {'U1': record['unit_reads'][0]}, set())
    outgoing = [g for g in groups if g['direction'] == 'OUTGOING' and g['target']['document_id'] == 'd']
    assert outgoing, (groups, unresolved)
    assert not any(u.get('locator', '').startswith('제3조') for u in unresolved)



def test_question_comparison_locators_offer_only_read_units(declared):
    """Partial comparison (질문 대사): locators offer the read article itself; since 2026-11-11 they no longer
    query the reference join (field 60 s timeout). The cited external article stays reachable through follow_reference."""
    from semantic_runtime.workflow_bridge import SourcePort
    from semantic_runtime.comparison_research_bridge import locators
    s = declared.source          # the workflow's source tools (SourceSession)
    src = next(v for v in s.tools.sources.values() if v['document_id'] == 'inside' and v['heading'].startswith('제2조'))
    result = s.execute({'tool': 'read_node', 'args': {'node': s.node('inside', src['unit_id'], src['id']), 'cursor': None}, 'reason': '내규 원문 읽기'})
    evidence = [s.repo.evidence(i) for i in result['evidence_ids']]
    found = locators(SourcePort(s), evidence)
    assert found and all(v['document_id'] == 'inside' and v['reference_id'] is None for v in found.values()), found
    # The reference tool returns the same completed reference, with the declared name.
    refs = s.execute({'tool': 'follow_reference', 'args': {'evidence_id': evidence[0]['evidence_id'], 'direction': 'outgoing', 'cursor': None},
                      'reason': '내규가 적은 외규 확인'})['items']
    assert any(r.get('declared_name', {}).get('name') == '규정' and r['targets'] for r in refs), refs
