"""A 별표 citation reaches its separately stored annex file only under the citing document's folder."""
import json
import sqlite3
import pytest
from test_unit_fulltext_adaptive_read import unit_fts, SourceRecall
from test_document_release import source
from test_bounded_source_main import settings
from test_legal_agent_v5 import app_for
from test_unified_legal_agent import ScriptedTransport
from lawrag.pipeline.term_generation import build_generation
rel = pytest.importorskip('semantic_runtime.legal_agent.unit_relations')

MAIN = '외부 > 모의승인규정'
ANNEX = MAIN + ' > 별표서식 > [별표 1] 긴급 승인 기준표'


def session_for(tmp_path, term_glossary, documents, scope):
    raw = source(tmp_path/'raw.sqlite', [
        ('d', MAIN, ['제1조 승인', '① 긴급 승인 기준은 다음 각 호와 같다.',
                     '1. 긴급 승인은 별표 1에서 정하는 기준에 따른다.', '2. 일반 승인은 제한한다.']),
        *documents])
    with sqlite3.connect(raw) as db:
        db.execute("DELETE FROM source_unit WHERE document_id='d'")
        for uid, parent, family, surface, lo, hi in [('0', None, 'kr_article', '제1조', 0, 4), ('1', '0', 'circled', '①', 1, 4),
                                                     ('2', '1', 'dot_number:1', '1.', 2, 3), ('3', '1', 'dot_number:1', '2.', 3, 4)]:
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', ('d', uid, parent,
                json.dumps({'family': family, 'surface': surface, 'title': '', 'span': [lo, hi]}, ensure_ascii=False)))
    build_generation(raw, term_glossary, tmp_path/'built', serving=True)
    gen = tmp_path/'built/generation'
    unit_fts.build(gen, gen/'navigation', tmp_path/'index', workers=1)
    idx = unit_fts.UnitFulltextIndex(tmp_path/'index', json.loads((gen/'navigation/manifest.json').read_text()))
    app = app_for(tmp_path, gen, ScriptedTransport(), {**settings(), 'page_size': 1, 'max_read_chars': 80})
    p = app.state.pipeline
    p.term_agent.unit_fulltext = idx
    request = {'question': '긴급 승인 기준', 'document_ids': scope, 'use_llm': False}
    return p, p.term_agent.open_session(request, query=p.plan(request['question'], scope), runtime=tmp_path/'runtime')


def connections(p, opened):
    try:
        with opened as session:
            s = session.sources
            src = next(v for v in s.tools.sources.values() if v['document_id'] == 'd')
            recall = SourceRecall(s)
            recall.discover = lambda: ([src['id']], {'discovery_mode': 'structure', 'routes': {},
                                                      'unit_hits': [rel.hit_for(s, src['id'], '2')]})
            record = recall.prepare()
            return rel.catalog(s, [src['id']], {'U1': record['unit_reads'][0]}, set())
    finally:
        p.store.close()


def annex_unresolved(unresolved):
    return [u for u in unresolved if '별표' in (u.get('locator') or '')]


def test_annex_file_under_citing_folder_becomes_outgoing_connection(tmp_path, term_glossary):
    groups, _, _, unresolved = connections(*session_for(tmp_path, term_glossary, [
        ('annex', ANNEX, ['[별표 1] 긴급 승인 기준표', '1. 긴급 승인 한도는 100만 원으로 한다.']),
        ('other', '외부 > 다른규정 > 별표서식 > [별표 1] 다른 기준표', ['[별표 1] 다른 기준표', '1. 다른 한도.'])],
        ['d', 'annex', 'other']))
    group = next(g for g in groups if g['target']['document_id'] == 'annex')
    edge = group['connections'][0]
    assert group['direction'] == 'OUTGOING'
    assert edge['resolution'] == 'EXACT_DETACHED_ANNEX_FOLDER'
    assert edge['reading_policy']['kind'] == 'ANNEX_STANDARD'
    assert not any(g['target']['document_id'] == 'other' for g in groups)
    assert not annex_unresolved(unresolved)


def test_two_files_with_same_label_stay_unresolved(tmp_path, term_glossary):
    groups, _, _, unresolved = connections(*session_for(tmp_path, term_glossary, [
        ('annex', ANNEX, ['[별표 1] 긴급 승인 기준표', '1. 한도 100만 원.']),
        ('annex2', ANNEX + '(개정)', ['[별표 1] 긴급 승인 기준표(개정)', '1. 한도 200만 원.'])],
        ['d', 'annex', 'annex2']))
    assert not any(g['target']['document_id'] in ('annex', 'annex2') for g in groups)
    assert [u['stored_resolution_reason'] for u in annex_unresolved(unresolved)] == ['DETACHED_ANNEX_AMBIGUOUS']


def test_annex_file_outside_request_scope_is_not_offered(tmp_path, term_glossary):
    groups, _, _, _ = connections(*session_for(tmp_path, term_glossary, [
        ('annex', ANNEX, ['[별표 1] 긴급 승인 기준표', '1. 한도 100만 원.'])], ['d']))
    assert not any(g['target']['document_id'] == 'annex' for g in groups)


def test_annex_with_same_label_under_other_regulation_is_not_bound(tmp_path, term_glossary):
    groups, _, _, unresolved = connections(*session_for(tmp_path, term_glossary, [
        ('other', '외부 > 다른규정 > 별표서식 > [별표 1] 다른 기준표', ['[별표 1] 다른 기준표', '1. 다른 한도.'])],
        ['d', 'other']))
    assert not any(g['target']['document_id'] == 'other' for g in groups)
    assert [u['stored_resolution_reason'] for u in annex_unresolved(unresolved)] == ['ANNEX_BODY_NOT_IN_SELECTION']


# Runtime fallback for indexes built before the builder bound detached files.
from semantic_runtime import annex_files as af

LAW = '외부 > 모의법 시행규칙'
SOURCES = [('s-body', 'body', LAW), ('s-other', 'other', '외부 > 다른법 시행규칙'),
           ('s-f9', 'f9', LAW + ' > 별표서식 > [서식 9] 신청서'),
           ('s-f11', 'f11', LAW + ' > 별표서식 > [서식 11] 감면신청서'),
           ('s-f11-8', 'f11-8', LAW + ' > 별표서식 > [서식 11의8] 특례신청서'),
           ('s-t3-2', 't3-2', LAW + ' > 별표서식 > [별표 3의2] 산출기준'),
           ('s-o9', 'o9', '외부 > 다른법 시행규칙 > 별표서식 > [서식 9] 다른 신청서')]
INDEX = af.index(SOURCES)
NAMES = {did: name for _, did, name in SOURCES}


def bind(origin, text, mention, hint=None, index=INDEX):
    start = text.index(mention)
    ref = {'source_text': text, 'mention_start': start, 'mention_end': start + len(mention),
           'mention_text': mention, 'locator': mention, 'document_name_hint': hint}
    out = rel.detached_annex(ref, {'document_id': origin, 'document_name': NAMES[origin]}, index)
    return out and (out.get('detached_annex', {}).get('document_id') or out['reason'])


@pytest.mark.parametrize('origin,text,mention,hint,expected', [
    ('body', '신청은 별지 제9호서식에 따른다.', '별지 제9호', None, 'f9'),
    ('body', '산출은 별표 3-2에 따른다.', '별표 3-2', None, 't3-2'),
    ('t3-2', '세부는 별표 3의2에 따른다.', '별표 3의2', None, None),
    ('f11-8', '■ 모의법 시행규칙[별지 제11호의8서식] <개정>', '[별지 제11호', '모의법 시행규칙', None),
    ('f11', '관련 서식은 별지 제9호서식이다.', '별지 제9호', None, 'f9'),
    ('body', '「다른법 시행규칙」 별지 제9호서식을 쓴다.', '별지 제9호', '다른법 시행규칙', 'o9'),
    ('body', '「없는법 시행규칙」 별지 제9호서식을 쓴다.', '별지 제9호', '없는법 시행규칙', None),
    ('body', '별지 제12호서식에 따른다.', '별지 제12호', None, None),
])
def test_runtime_binding_rule(origin, text, mention, hint, expected):
    assert bind(origin, text, mention, hint) == expected


def test_runtime_two_files_with_one_label_are_ambiguous():
    index = af.index(SOURCES + [('s-f9b', 'f9b', LAW + ' > 별표서식 > [별지 제9호서식] 신청서(구)')])
    assert bind('body', '별지 제9호서식에 따른다.', '별지 제9호', index=index) == 'DETACHED_ANNEX_AMBIGUOUS'
