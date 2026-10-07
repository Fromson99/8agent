"""Lifecycle and source integrity of local investigation wiki projection."""
import pytest

from semantic_runtime.action_memory_store import Memory
from lawrag.pipeline.legal_llm_wiki import export_wiki, check_wiki, operate


@pytest.fixture
def experience(tmp_path):
    directory = tmp_path / 'action-memory'
    memory = Memory(directory / 'memory.sqlite')
    binding = {'generation_id': 'mock:v1', 'store_sha256': 'a' * 64}
    from semantic_runtime.action_memory_store import data_key
    sources = [{'source_id': 'source:1', 'document_id': 'doc:1', 'unit_id': '1',
                'origin_hash': 'b' * 64, 'heading': '모의 조항', 'text': '모의 원문: 적용 요건',
                'reason': '질문의 적용 요건을 확인하는 원문이다.'}]
    episode = {'id': 'run:1', 'binding': binding, 'data_key': data_key(binding),
               'question': '모의 적용 요건은?', 'purpose_reason': '적용 요건을 조사한다.',
               'selected': sources, 'originals': sources, 'negative_feedback': []}
    memory.ingest(episode)
    assignment = {'episode_id': 'run:1', 'concept_id': '', 'label': '적용 요건 확인',
                  'definition': '원문에서 적용 요건을 확인하는 조사 목적',
                  'source_ids': ['source:1'], 'reason': '질문과 원문 선택 이유가 요건 확인이다.'}
    memory.adopt([assignment])
    purpose = memory.catalogue()[0]['id']
    oid = memory.db.execute('SELECT id FROM observation').fetchone()[0]
    yield memory, directory, binding, episode, assignment, purpose, oid
    memory.close()


def test_projection_is_idempotent_and_preserves_verbatim_reasons(experience):
    m, directory, binding, episode, assignment, purpose, oid = experience
    wiki = directory / 'legal_llm_wiki'
    first = export_wiki(m, wiki)
    raw = next((wiki / 'raw/experiences').glob('*.md'))
    original = raw.read_bytes()
    log = (wiki / 'wiki/log.md').read_bytes()
    assert export_wiki(m, wiki) == first
    assert raw.read_bytes() == original
    assert (wiki / 'wiki/log.md').read_bytes() == log
    page = next((wiki / 'wiki/investigation').glob('*.md')).read_text()
    assert episode['question'] in page and assignment['reason'] in page
    assert episode['selected'][0]['reason'] in page
    assert first['legal_truth_certified'] is False and first['online_wired'] is False
    assert check_wiki(wiki)['ok']


def test_unlink_survives_reassignment_and_changed_episode(experience):
    m, directory, binding, episode, assignment, purpose, oid = experience
    operate(directory, 'wiki-unlink', observation_id=oid,
            reason='목적이 다른 경험을 잘못 묶음', reviewer='tester')
    assert m.catalogue() == []
    assert m.compile(purpose, binding, ['source:1'], 'read')['guide_node_ids'] == []
    m.adopt([assignment])
    assert m.catalogue() == []
    m.ingest({**episode, 'purpose_reason': '수정된 조사 이유'})
    m.adopt([assignment])
    assert m.compile(purpose, binding, ['source:1'], 'read')['guide_node_ids'] == []
    export_wiki(m, directory / 'legal_llm_wiki')
    assert len(list((directory / 'legal_llm_wiki/raw/experiences').glob('*.md'))) == 2
    assert m.db.execute('SELECT count(*) FROM event WHERE kind="ABSTRACTION_DISCONNECTED"').fetchone()[0] == 1


def test_retire_concept_keeps_sources_and_other_concepts(experience):
    m, directory, binding, episode, assignment, purpose, oid = experience
    m.adopt([{**assignment, 'label': '별개 목적', 'definition': '구분한 조사 목적'}])
    operate(directory, 'wiki-retire', concept_id=purpose, reason='개념 범위가 너무 넓음', reviewer='tester')
    assert [c['label'] for c in m.catalogue()] == ['별개 목적']
    assert m.compile(purpose, binding, ['source:1'], 'read')['allowed_node_ids'] == ['source:1']
    assert m.db.execute('SELECT count(*) FROM episode').fetchone()[0] == 1
    assert m.db.execute('SELECT count(*) FROM observation').fetchone()[0] == 2


def test_disputed_exclusion_restores_access_and_generation_drift_fails_closed(experience):
    m, directory, binding, episode, assignment, purpose, oid = experience
    # A reviewed exclusion would otherwise constrain the source pool.
    with m.transaction():
        m.db.execute("UPDATE observation SET predicate='EXCLUDES' WHERE id=?", (oid,))
    assert m.compile(purpose, binding, ['source:1'], 'read')['allowed_node_ids'] == []
    m.disconnect('observation', oid, reason='제외 근거에 이견이 있음', reviewer='tester', status='DISPUTED')
    assert m.compile(purpose, binding, ['source:1'], 'read')['allowed_node_ids'] == ['source:1']
    assert m.compile(purpose, {**binding, 'generation_id': 'mock:v2'}, ['source:1'], 'read')['observation_ids'] == []


def test_projection_detects_raw_tampering_and_refuses_to_rewrite_it(experience):
    m, directory, *_ = experience
    wiki = directory / 'legal_llm_wiki'
    export_wiki(m, wiki)
    raw = next((wiki / 'raw/experiences').glob('*.md'))
    raw.write_text('changed')
    assert not check_wiki(wiki)['ok']
    with pytest.raises(ValueError, match='immutable wiki source changed'):
        export_wiki(m, wiki)


def test_lifecycle_requires_reason_and_old_readonly_v1_is_compatible(experience):
    m, directory, binding, episode, assignment, purpose, oid = experience
    with pytest.raises(ValueError, match='reason and reviewer'):
        m.disconnect('observation', oid, reason='', reviewer='tester')
    with m.transaction():
        m.db.execute('DROP TABLE abstraction_state')
    readonly = Memory(directory / 'memory.sqlite', readonly=True)
    try:
        assert readonly.catalogue()[0]['id'] == purpose
        assert readonly.compile(purpose, binding, ['source:1'], 'read')['guide_node_ids'] == ['source:1']
    finally:
        readonly.close()


def test_group_disconnection_rolls_back_if_any_identity_is_unknown(experience):
    m, directory, binding, episode, assignment, purpose, oid = experience
    with pytest.raises(ValueError, match='unknown abstraction'):
        m.disconnect_many('observation', [oid, 'missing'], reason='오연결', reviewer='tester')
    assert m.catalogue()[0]['id'] == purpose
    assert m.db.execute('SELECT count(*) FROM abstraction_state').fetchone()[0] == 0


def test_existing_nightly_builder_exports_without_extra_model_calls(experience):
    from pathlib import Path
    from lawrag.pipeline.action_memory import build
    m, directory, *_ = experience

    class NoCalls:
        def eligible(self, episode):
            raise AssertionError('already built episode must not be processed')
        def generate(self, *args):
            raise AssertionError('wiki projection must not call a model')

    result = build(Path(__file__).resolve().parents[2], runtime=directory.parent,
                   manual=True, model=NoCalls())
    assert result['state'] == 'COMPLETED'
    assert result['counts']['model_calls'] == 0
    assert result['legal_llm_wiki']['concepts'] == 1
    assert check_wiki(directory / 'legal_llm_wiki')['ok']
