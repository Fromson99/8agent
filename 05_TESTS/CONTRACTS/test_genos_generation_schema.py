"""GENOS binding accepts legacy/compact sources and preserves validation."""
from contextlib import closing
import json

import pytest

from semantic_runtime.storage import Store, publish
from semantic_runtime.compact_storage import source as compact_source
from test_document_release import source


@pytest.fixture
def entry(monkeypatch, tmp_path):
    import service
    monkeypatch.setattr(service, '_APP', None)
    monkeypatch.setattr(service, '_BINDING', None)
    monkeypatch.setattr(service, '_provider', lambda *args: object())
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path / 'runtime'))
    for key in ('GENOS_RAG_IMPLEMENTATION', 'LEGAL_AGENT_PROFILE',
                'LEGAL_AGENT_PROFILE_SHA256', 'GENOS_LLM_URL',
                'GENOS_LLM_SERVING_ID', 'GENOS_LLM_KEY', 'GENOS_LLM_MODEL'):
        monkeypatch.delenv(key, raising=False)
    yield service
    service.request_report._FINALIZER_QUEUE.join()
    if service._APP is not None:
        service._APP.state.pipeline.store.close()


@pytest.mark.parametrize('profile,version', [
    ('legacy', 'term-source-generation-v1'),
    ('compact-v2', 'term-source-generation-v2'),
])
@pytest.mark.parametrize('tampered', [False, True])
def test_generation_binding_and_original_read(entry, tmp_path,
                                              monkeypatch, profile, version, tampered):
    text = '영업일은 은행이 영업하는 날을 말한다.'
    raw = source(tmp_path / 'source.sqlite', [('fixture', '모의규정', [text])])
    generation = tmp_path / 'built/generation'
    manifest = publish(entry._ROOT, raw, generation)
    if profile == 'compact-v2':
        manifest = compact_source(generation, tmp_path / 'built/audit/source', manifest)
        (generation / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert json.loads((generation / 'manifest.json').read_text())['schema_version'] == version
    before = (generation / 'manifest.json').read_bytes()
    monkeypatch.setenv('GENOS_GENERATION', str(generation))
    if tampered:
        with (generation / 'store.sqlite').open('ab') as stream:
            stream.write(b'corrupted-after-publication')
    code_root, selected, binding = entry._resolve_binding()
    assert code_root == entry._ROOT
    assert selected == generation.resolve()
    assert binding['mode'] == 'genos-generation'
    if tampered:
        with pytest.raises(ValueError, match='generation artifact hash mismatch'):
            Store(selected)
    else:
        with closing(Store(selected)) as store:
            assert store.source('fixture', '0')['text'] == text
    assert (generation / 'manifest.json').read_bytes() == before


@pytest.mark.parametrize('version', [None, 'term-source-generation-v3',
                                   'term-navigation-index-v7', 'semantic-fulltext-v2'])
def test_non_generation_manifest_rejected(entry, tmp_path, monkeypatch, version):
    generation = tmp_path / 'wrong-generation'
    generation.mkdir()
    (generation / 'manifest.json').write_text(json.dumps({'schema_version': version}))
    monkeypatch.setenv('GENOS_GENERATION', str(generation))
    with pytest.raises(RuntimeError, match='unsupported manifest'):
        entry._explicit_generation()
    assert entry._APP is None
