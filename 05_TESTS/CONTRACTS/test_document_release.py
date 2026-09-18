"""Synthetic GENOS addition contracts. Scripted internal provider, no live calls."""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import pytest

from semantic_runtime.contracts import sha, write
from semantic_runtime.storage import Store, publish
from semantic_runtime.term_index import TermIndex
from semantic_runtime.navigation_agent import glossary_assets
from semantic_runtime.navigation_match import ReverseMatcher
from semantic_runtime.navigation_loop import NavigationSession
from lawrag.pipeline import glossary_assembly as assembly, glossary_v1 as v1
from lawrag.pipeline import glossary_document_update, glossary_review, document_release
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.term_serving_bundle import verify_assets

ROOT = Path(__file__).resolve().parents[2]


def source(path, documents):
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
          CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
          CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);''')
        for did, name, texts in documents:
            artifact = __import__('hashlib').sha256(json.dumps(texts).encode()).hexdigest()
            db.execute('INSERT INTO document VALUES (?,?,?,?)', (did, name, artifact, '{}'))
            for i, text in enumerate(texts):
                unit = {'family': 'kr_article', 'surface': f'제{i+1}조', 'title': '정의' if i == 0 else '적용', 'span': [i, i+1]}
                db.execute('INSERT INTO source_unit VALUES (?,?,?,?)', (did, str(i), None, json.dumps(unit)))
                db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)', (did, str(i), str(i), text, artifact, '{}'))
    return path


@pytest.fixture
def glossary(term_glossary):
    return term_glossary


class ReviewProvider:
    def __init__(self): self.calls = 0
    def prepare(self): return {'backend': 'genos', 'model': 'synthetic-contract'}
    def call(self, role, task, data, schema):
        self.calls += 1
        return {'job_id': data['job_id'], 'input_sha256': data['input_sha256'],
                'identity': {'decision': 'UNKNOWN', 'evidence_ids': []},
                'relation_assessment': 'UNKNOWN', 'relations': [], 'rationale': '모의 응답',
                'missing_information': '의미 검토 미확정'}, {'synthetic': True, 'backend': 'genos'}


def test_full_link_index_bundle_and_scoped_navigation(tmp_path, glossary):
    original = source(tmp_path / 'source.sqlite', [('internal:v1', '가상내규', [
        '이 규정에서 “영업일”이란 은행이 영업하는 날을 말한다. 자금지원 Business Day',
        '「가상법」 제1조에 따른다.']), ('law:v1', '가상법', ['영업일에 관한 원문'])])
    result = build_generation(original, glossary, tmp_path / 'built', serving=True)
    generation = tmp_path / 'built/generation'
    assert verify_assets(generation)['verified']
    assert build_generation(original, glossary, tmp_path / 'built', serving=True) == result
    manifest = json.loads((generation / 'navigation/manifest.json').read_text())
    assert manifest['schema_version'] == 'term-navigation-index-v3'
    with closing(Store(generation)) as store:
        index = TermIndex(generation / 'navigation', store)
        tools = index.tools(['internal:v1', 'law:v1'])
        try:
            assert tools.search_labels(['Business Day'], ['internal:v1'])
            assert tools.search(['fixture:day'], ['internal:v1'])
            refs = [json.loads(r[0]) for r in tools.db.execute('SELECT json FROM reference')]
            assert any(r['resolution'] == 'EXACT_NAMED_DOCUMENT_ARTICLE' and r['target_source_ids'] for r in refs)
            g = glossary_assets(generation, {'glossary': {'bundle': 'INVALID'}})
            try:
                matcher = ReverseMatcher(store.db, tools, g)
                starts = matcher.starts('자금지원 영업일', ['internal:v1'])
                assert any(r['id'].startswith('concept:') for r in starts['terms'])
                assert any(r['id'] == 'fixture:day' for r in starts['terms'])
            finally: g.close()
        finally: tools.db.close()
    assert not (tmp_path / 'generations/CURRENT.json').exists()


def test_new_definitions_review_only_and_no_repeated_calls(tmp_path, glossary):
    original = source(tmp_path / 'input.sqlite', [('new:v1', '가상내규', [
        '이 규정에서 “영업일”이란 은행이 영업하는 날을 말한다.',
        '“신규용어”란 다음 각 호의 사항'])])
    merged = document_release.merge_sources([original], tmp_path / 'sources')
    report = glossary_document_update.augment(glossary, merged, tmp_path / 'draft')
    assert report['document_update']['new_definitions'] == 2
    plan = glossary_review.prepare(tmp_path / 'draft', tmp_path / 'review')
    assert plan['total_jobs'] > 0 and bool(plan['deferred'])
    provider = ReviewProvider()
    result = glossary_review.complete(tmp_path / 'draft', tmp_path / 'review', tmp_path / 'reviewed', max_jobs=100, provider=provider)
    assert result['completed'] and result['review_status'] == 'PARTIAL'
    assert document_release.verify_glossary(tmp_path / 'reviewed')['verified']
    with pytest.raises(ValueError, match='receipt'):
        document_release.verify_glossary(tmp_path / 'draft')
    before = provider.calls
    assert glossary_review.complete(tmp_path / 'draft', tmp_path / 'review', tmp_path / 'reviewed', provider=provider)['cached']
    assert provider.calls == before
    with sqlite3.connect(tmp_path / 'reviewed/dictionary.sqlite') as db:
        assert db.execute('SELECT count(*) FROM meaning').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM membership').fetchone()[0] == 0
    # Repeating the same document evidence does not generate another definition review.
    follow = glossary_document_update.augment(tmp_path / 'reviewed', merged, tmp_path / 'next')
    assert follow['document_update']['new_definitions'] == 0
    assert glossary_review.prepare(tmp_path / 'next', tmp_path / 'next-review')['total_jobs'] == 0
    build_generation(merged, tmp_path / 'reviewed', tmp_path / 'served', serving=True)
    assert verify_assets(tmp_path / 'served/generation')['verified']


def test_merge_versions_conflicts_explicit_exclusion_and_tamper(tmp_path):
    a = source(tmp_path / 'a.sqlite', [('a', '법', ['원문'])])
    b = source(tmp_path / 'b.sqlite', [('b', '내규', ['내부 원문'])])
    merged = document_release.merge_sources([a, b, a], tmp_path / 'merged')
    with sqlite3.connect(merged) as db:
        assert db.execute('SELECT count(*) FROM document').fetchone()[0] == 2
    document_release.merge_sources([a, b], tmp_path / 'excluded', exclude=['a'])
    conflict = source(tmp_path / 'conflict.sqlite', [('a', '법', ['다른 버전'])])
    with pytest.raises(ValueError, match='Conflicting'):
        document_release.merge_sources([a, conflict], tmp_path / 'bad')
    with pytest.raises(ValueError, match='not in'):
        document_release.merge_sources([a], tmp_path / 'bad-exclusion', exclude=['missing'])
    with merged.open('ab') as stream: stream.write(b'drift')
    with pytest.raises(ValueError, match='selection changed'):
        document_release.merge_sources([a, b, a], tmp_path / 'merged')


@pytest.mark.parametrize('names,citation,reason', [
    (['대상법', '대상법'], '「대상법」 제1조', 'DOCUMENT_VERSION_AMBIGUOUS'),
    (['다른법'], '「대상법」 제1조', 'DOCUMENT_MISSING'),
    (['대상법'], '「대상법」 제1조부터 제2조까지', 'RANGE_OR_SUBARTICLE_UNRESOLVED'),
])
def test_ambiguous_references_stay_unresolved(tmp_path, glossary, names, citation, reason):
    documents = [('internal', '내규', [citation + '를 확인한다.'])]
    documents += [(str(i), name, ['대상 원문']) for i, name in enumerate(names)]
    original = source(tmp_path / 'source.sqlite', documents)
    build_generation(original, glossary, tmp_path / 'build')
    with sqlite3.connect(tmp_path / 'build/generation/navigation/navigation.sqlite') as db:
        refs = [json.loads(r[0]) for r in db.execute('SELECT json FROM reference')]
        assert any(r['reason'] == reason for r in refs)
        assert all(not r['target_source_ids'] for r in refs)


def test_missing_provision_links_the_article_and_keeps_the_reason(tmp_path, glossary):
    # 항·호가 붙은 인용은 조 아래 마디까지 잇는다. 그 항이 구조에 없으면 조까지만 잇고 사유를 남긴다.
    original = source(tmp_path / 'source.sqlite', [('internal', '내규', ['「대상법」 제1조 제2항을 확인한다.']),
                                                   ('0', '대상법', ['대상 원문'])])
    build_generation(original, glossary, tmp_path / 'build')
    with sqlite3.connect(tmp_path / 'build/generation/navigation/navigation.sqlite') as db:
        refs = [json.loads(r[0]) for r in db.execute('SELECT json FROM reference')]
    hit = next(r for r in refs if r['document_id'] == 'internal')
    assert hit['target_source_ids'] and hit['target_level'] == 'article'
    assert hit['reason'] == 'PROVISION_NOT_IN_STRUCTURE'


def test_release_build_review_pause_activation_rollback(tmp_path, glossary, monkeypatch):
    raw = source(tmp_path / 'source.sqlite', [('internal', '가상내규', [
        '“영업일”이란 은행이 영업하는 날을 말한다.', '“영업일”이란 금융기관이 일하는 날을 말한다.'])])
    # Selection validation has its own real structure test below; exercise the complete join here.
    monkeypatch.setattr(document_release, 'selected_sources', lambda *a: ([raw], {str(raw): sha(raw)}))
    provider = ReviewProvider()
    result = document_release.build(tmp_path, 'new', glossary, max_jobs=1, provider=provider)
    assert result['status'] == 'REVIEW_PENDING'
    assert not (tmp_path / 'TERM_RELEASES/new/release.json').exists()
    result = document_release.build(tmp_path, 'new', glossary, max_jobs=100, provider=provider)
    assert result['completed'] and not result['activated']
    release = Path(result['path'])
    document_release.verify_release(release)
    with pytest.raises(ValueError, match='confirm'):
        document_release.change_pointer(tmp_path, release=release, expected_current='absent')
    event = document_release.change_pointer(tmp_path, release=release, expected_current='absent', confirm=True)
    with pytest.raises(ValueError, match='CURRENT changed'):
        document_release.change_pointer(tmp_path, release=release, expected_current='absent', confirm=True)
    document_release.change_pointer(tmp_path, rollback=Path(event['receipt']), expected_current=event['current_sha256'], confirm=True)
    assert not (tmp_path / 'generations/CURRENT.json').exists()
    dictionary = release / 'serving/generation/glossary/dictionary.sqlite'
    with dictionary.open('ab') as stream: stream.write(b'drift')
    with pytest.raises(ValueError, match='dictionary binding'):
        document_release.verify_release(release)


def test_internal_definition_scope_not_exposed(tmp_path, glossary):
    original = source(tmp_path / 'input.sqlite', [('private', '비공개내규', ['“영업일”이란 비공개 정의를 말한다.']),
                                                ('public', '공개법', ['영업일 원문'])])
    merged = document_release.merge_sources([original], tmp_path / 'sources')
    glossary_document_update.augment(glossary, merged, tmp_path / 'draft')
    build_generation(merged, tmp_path / 'draft', tmp_path / 'build', serving=True)
    generation = tmp_path / 'build/generation'
    with closing(Store(generation)) as store:
        tools = TermIndex(generation / 'navigation', store).tools(['public'])
        g = glossary_assets(generation, {})
        try:
            matcher = ReverseMatcher(store.db, tools, g)
            session = NavigationSession(matcher, tools, g, '영업일', ['public'])
            assert '비공개 정의' not in json.dumps(session.context(), ensure_ascii=False)
            private = next(t for t in tools.terms if tools.terms[t].get('scope_document_id') == 'private')
            with pytest.raises(ValueError, match='scope'): session.term_card(private)
        finally: tools.db.close(); g.close()


def test_raw_xml_addition_to_integrated_serving_generation(tmp_path, glossary, monkeypatch):
    from lawrag.pipeline import genos_build, genos_stages
    from lawrag.core import llm
    monkeypatch.setattr(llm, 'load_env', lambda: None)
    raw = tmp_path / 'raw'; raw.mkdir()
    (raw / 'internal.xml').write_text('''<법령><기본정보><법령명_한글>가상내규</법령명_한글></기본정보><조문>
      <조문단위><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>정의</조문제목>
      <조문내용>제1조(정의) “영업일”이란 은행이 영업하는 날을 말한다. 「가상외규」 제1조에 따른다.</조문내용>
      </조문단위></조문></법령>''')
    options = genos_build.parser().parse_args(['build', '--input-root', str(raw), '--build-dir', str(tmp_path / 'work'),
                                              '--glossary-dir', str(glossary), '--execute'])
    plan = genos_build.inventory(raw, 'internal', None)
    class Progress:
        def document(self, *a, **k): pass
        def emit(self, *a, **k): pass
        def finish(self, *a, **k): pass
        def error(self, error): raise error
    data = tmp_path / 'data'
    status = genos_stages.execute(plan, options, data, 'added', 'structure', progress=Progress(), dependencies={'fixture': 'xml'})
    assert status['ok']
    base_source = source(tmp_path / 'base.sqlite', [('external:v1', '가상외규', ['영업일에 관한 외규 원문'])])
    base = data / 'baseline'; publish(ROOT, base_source, base)
    prepared = document_release.build(data, 'added', glossary, bases=[base], prepare_only=True)
    assert prepared['status'] == 'PREPARED'
    result = document_release.build(data, 'added', glossary, bases=[base], provider=ReviewProvider())
    assert result['completed']
    generation = Path(result['generation_path'])
    with closing(Store(generation)) as store:
        assert store.manifest['counts']['document'] == 2
        tools = TermIndex(generation / 'navigation', store).tools(store.manifest['scope']['document_version_ids'])
        g = glossary_assets(generation, {})
        try:
            matcher = ReverseMatcher(store.db, tools, g)
            session = NavigationSession(matcher, tools, g, '영업일', store.manifest['scope']['document_version_ids'])
            menu = session.listing(['fixture:day'])
            assert menu['total'] == 2
            found = [json.loads(r[0]) for r in tools.db.execute('SELECT json FROM reference')]
            assert any(r['resolution'] == 'EXACT_NAMED_DOCUMENT_ARTICLE' for r in found)
        finally: tools.db.close(); g.close()
    # Retaining the same explicit baseline and input reuses work and never calls the model again.
    class ForbiddenProvider:
        def prepare(self): pytest.fail('completed review was rerun')
    assert document_release.build(data, 'added', glossary, bases=[base], provider=ForbiddenProvider())['completed']
    pointer = data / 'LOGS/added/structure-selection.json'
    selection = json.loads(pointer.read_text()); selection['completed'] = False; pointer.write_text(json.dumps(selection))
    with pytest.raises(ValueError, match='incomplete'):
        document_release.selected_sources(data, 'added', [base])


def test_reviewed_relationship_is_an_observation_with_scoped_evidence(tmp_path, glossary):
    original = source(tmp_path / 'input.sqlite', [('new', '내규', ['“영업일”이란 은행이 영업하는 날을 말한다.'])])
    merged = document_release.merge_sources([original], tmp_path / 'sources')
    glossary_document_update.augment(glossary, merged, tmp_path / 'draft')
    class SameProvider(ReviewProvider):
        def call(self, role, task, data, schema):
            evidence = list(dict.fromkeys(data['left_sense']['evidence_ids'] + data['right_sense']['evidence_ids']))
            return {'job_id': data['job_id'], 'input_sha256': data['input_sha256'],
                    'identity': {'decision': 'SAME', 'evidence_ids': evidence},
                    'relation_assessment': 'NOT_ESTABLISHED', 'relations': [],
                    'rationale': '양쪽 정의의 근거를 선택한 모의 응답', 'missing_information': ''}, {'synthetic': True}
    reviewed = glossary_review.complete(tmp_path / 'draft', tmp_path / 'review', tmp_path / 'reviewed', provider=SameProvider())
    assert reviewed['completed']
    build_generation(merged, tmp_path / 'reviewed', tmp_path / 'build', serving=True)
    with sqlite3.connect(tmp_path / 'build/generation/navigation/navigation.sqlite') as db:
        edges = [json.loads(r[0]) for r in db.execute('SELECT json FROM edge')]
        assert any(e['code'] == 'SAME' and e['evidence'] and not e['canonical_approval'] for e in edges)
        assert all(e['status'] == 'MODEL_REVIEWED_PROPOSAL' for e in edges)


def test_new_serving_bundle_http_answer_and_feedback(tmp_path, glossary):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from test_navigation_main_wiring import Provider
    original = source(tmp_path / 'source.sqlite', [('internal:v1', '가상내규', ['영업일에 관한 모의 원문입니다.'])])
    build_generation(original, glossary, tmp_path / 'build', serving=True)
    provider = Provider(tmp_path / 'provider')
    # The scripted provider speaks the navigation-loop protocol.
    app = create_app(tmp_path / 'runtime', tmp_path / 'build/generation', contracts_root=ROOT, provider=provider,
                     implementation='navigation-loop-v1')
    with TestClient(app) as client:
        result = client.post('/v1/rag/ask', json={'question': '가상내규 제1조 내용을 확인해 주세요.', 'use_llm': True})
        assert result.status_code == 200, result.text
        value = result.json()
        assert value['retrieval']['term_agent']['status'] == 'FINISH', value
        assert provider.calls == 2 and value['answer']['claims']
        assert client.post('/v1/rag/feedback', json={'run_id': value['run_id'], 'signal': 'MISSING_EVIDENCE', 'reason': 'synthetic'}).status_code == 200


def test_pending_parent_and_new_definitions_share_one_review(tmp_path, glossary):
    first = source(tmp_path / 'first.sqlite', [('first', '가상외규', ['“영업일”이란 은행이 영업하는 날을 말한다.'])])
    second = source(tmp_path / 'second.sqlite', [('second', '가상내규', ['“영업일”이란 은행이 근무하는 날을 말한다.'])])
    first_store = document_release.merge_sources([first], tmp_path / 'first-sources')
    glossary_document_update.augment(glossary, first_store, tmp_path / 'pending-parent')
    parent_hash = sha(tmp_path / 'pending-parent/dictionary.sqlite')
    merged = document_release.merge_sources([first, second], tmp_path / 'both-sources')
    glossary_document_update.augment(tmp_path / 'pending-parent', merged, tmp_path / 'combined')
    plan = glossary_review.prepare(tmp_path / 'combined', tmp_path / 'combined-review')
    assert plan['total_jobs'] >= 2
    with sqlite3.connect(tmp_path / 'pending-parent/dictionary.sqlite') as parent, sqlite3.connect(tmp_path / 'combined/dictionary.sqlite') as combined:
        old_ids = {r[0] for r in parent.execute('SELECT id FROM external_candidate')}
        new_ids = {r[0] for r in combined.execute('SELECT id FROM external_candidate')}
        assert old_ids and old_ids < new_ids
    with sqlite3.connect(tmp_path / 'combined-review/review.sqlite') as db:
        contexts = [json.loads(r[0]) for r in db.execute('SELECT input_json FROM job')]
        assert {c['external']['document_id'] for c in contexts} == {'first', 'second'}
    assert sha(tmp_path / 'pending-parent/dictionary.sqlite') == parent_hash


def test_completed_evidence_reused_but_changed_definition_reviewed(tmp_path, glossary):
    raw = source(tmp_path / 'source.sqlite', [('doc', '가상규정', ['“영업일”이란 은행이 영업하는 날을 말한다.'])])
    merged = document_release.merge_sources([raw], tmp_path / 'sources')
    glossary_document_update.augment(glossary, merged, tmp_path / 'draft')
    provider = ReviewProvider()
    glossary_review.complete(tmp_path / 'draft', tmp_path / 'review', tmp_path / 'reviewed', provider=provider)
    glossary_document_update.augment(tmp_path / 'reviewed', merged, tmp_path / 'unchanged')
    plan = glossary_review.prepare(tmp_path / 'unchanged', tmp_path / 'reuse')
    assert plan['total_jobs'] == 0 and plan['reused_jobs'] > 0
    # A changed source definition must invalidate evidence reuse, even at the same entry ID.
    altered = tmp_path / 'altered'; shutil.copytree(tmp_path / 'unchanged', altered)
    with sqlite3.connect(altered / 'dictionary.sqlite') as db:
        db.execute("UPDATE entry SET definition='주말에도 영업하는 날을 말한다.' WHERE id='fixture:day'")
    report = json.loads((altered / 'report.json').read_text())
    report['dictionary_sha256'] = sha(altered / 'dictionary.sqlite')
    (altered / 'report.json').write_text(json.dumps(report))
    changed = glossary_review.prepare(altered, tmp_path / 'changed-review')
    assert changed['total_jobs'] > 0 and changed['reused_jobs'] == 0


def test_legacy_archived_candidates_restored_in_new_draft(tmp_path, glossary):
    raw = source(tmp_path / 'source.sqlite', [('doc', '가상규정', ['“영업일”이란 은행이 영업하는 날을 말한다.'])])
    merged = document_release.merge_sources([raw], tmp_path / 'sources')
    glossary_document_update.augment(glossary, merged, tmp_path / 'parent')
    archived = tmp_path / 'archived'; shutil.copytree(tmp_path / 'parent', archived)
    with sqlite3.connect(archived / 'dictionary.sqlite') as db:
        for table in ('external_candidate', 'review_queue'):
            db.execute(f'CREATE TABLE inherited_{table} AS SELECT * FROM {table}')
            db.execute(f'DELETE FROM {table}')
    report = json.loads((archived / 'report.json').read_text())
    report['dictionary_sha256'] = sha(archived / 'dictionary.sqlite')
    (archived / 'report.json').write_text(json.dumps(report))
    glossary_document_update.augment(archived, merged, tmp_path / 'restored')
    assert glossary_review.prepare(tmp_path / 'restored', tmp_path / 'review')['total_jobs'] > 0
