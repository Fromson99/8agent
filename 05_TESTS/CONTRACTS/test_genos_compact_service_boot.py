"""Exercise the actual service bootstrap on compact data; synthetic only."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from test_compact_v2_rag import structured_generation
from test_bounded_source_main import settings
from test_unified_legal_agent import ScriptedTransport

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def entry(monkeypatch, tmp_path):
    monkeypatch.setenv('GENOS_AUTO_WARMUP', '0')
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path / 'runtime'))
    for name in ('GENOS_GENERATION', 'GENOS_DATA_ROOT', 'LEGAL_AGENT_PROFILE',
                 'LEGAL_AGENT_PROFILE_SHA256'):
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location('compact_boot_fixture', ROOT / 'service.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_provider', lambda *args: object())
    monkeypatch.setattr(module, '_genos_v5_environment_binding',
                        lambda *args: ({**settings(), 'max_model_attempts': 40}, ScriptedTransport()))
    yield module
    if module._APP is not None:
        module._APP.state.pipeline.store.close()
    module.request_report._FINALIZER_QUEUE.join()


@pytest.mark.parametrize('schema', ['term-source-generation-v1', 'term-source-generation-v2'])
def test_explicit_loader_accepts_supported_versions(entry, tmp_path, monkeypatch, schema):
    generation = tmp_path / 'selected'; generation.mkdir()
    (generation / 'manifest.json').write_text(json.dumps({'schema_version': schema, 'generation_id': 'selected'}))
    monkeypatch.setenv('GENOS_GENERATION', str(generation))
    assert entry._resolve_binding()[1] == generation


@pytest.mark.parametrize('schema', ['term-source-generation-v3', 'semantic-generation-v1'])
def test_unsupported_version_never_falls_back(entry, tmp_path, monkeypatch, schema):
    generation = tmp_path / 'selected'; generation.mkdir()
    (generation / 'manifest.json').write_text(json.dumps({'schema_version': schema}))
    monkeypatch.setenv('GENOS_GENERATION', str(generation))
    monkeypatch.setattr(entry, '_local_release', lambda: pytest.fail('unexpected fallback'))
    with pytest.raises(RuntimeError, match='unsupported manifest'):
        entry._resolve_binding()


@pytest.mark.parametrize('schema', ['semantic-fulltext-v2', 'semantic-unit-fulltext-v1'])
def test_tokenizer_guard_accepts_both_index_contracts(entry, tmp_path, schema):
    generation = tmp_path / 'selected'; (generation / 'fulltext').mkdir(parents=True)
    (generation / 'manifest.json').write_text(json.dumps({'fulltext': {'path': 'fulltext'}}))
    (generation / 'fulltext/manifest.json').write_text(json.dumps({
        'schema_version': schema, 'tokenizer': {'name': 'pecab', 'version': '1.0.8'}}))
    entry._require_pecab_generation(generation)


@pytest.mark.parametrize('schema,version', [('semantic-unit-fulltext-v1', 'unknown'),
                                           ('semantic-fulltext-v1', '1.0.8')])
def test_tokenizer_guard_still_rejects_unknown_contracts(entry, tmp_path, schema, version):
    generation = tmp_path / 'selected'; (generation / 'fulltext').mkdir(parents=True)
    (generation / 'manifest.json').write_text(json.dumps({'fulltext': {'path': 'fulltext'}}))
    (generation / 'fulltext/manifest.json').write_text(json.dumps({
        'schema_version': schema, 'tokenizer': {'name': 'pecab', 'version': version}}))
    with pytest.raises(RuntimeError, match='PeCab 1.0.8'):
        entry._require_pecab_generation(generation)


def test_real_compact_service_boot_search_and_tamper_rejection(entry, structured_generation, monkeypatch):
    generation = structured_generation
    manifest = json.loads((generation / 'manifest.json').read_text())
    assert manifest['schema_version'] == 'term-source-generation-v2'
    fulltext = generation / manifest['fulltext']['path']
    assert json.loads((fulltext / 'manifest.json').read_text())['schema_version'] == 'semantic-unit-fulltext-v1'
    monkeypatch.setenv('GENOS_GENERATION', str(generation))
    monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION', 'legal-agent-unified-v6')
    monkeypatch.setenv('GENOS_DEFER_PUBLICATION', '1')
    health = asyncio.run(entry.service({}, {'API_TYPE': 'HEALTH'}))
    assert health['status'] == 200, health
    assert entry._APP.state.pipeline.profile_id == 'legal-agent-rag-v6'
    out = asyncio.run(entry.service({}, {'API_TYPE': 'RAG_SEARCH', 'q': '승인', 'document_ids': ['d']}))
    assert out['status'] == 200, out
    entry._APP.state.pipeline.store.close()
    entry._APP = None
    with (generation / 'store.sqlite').open('ab') as stream:
        stream.write(b'tampered')
    bad = asyncio.run(entry.service({}, {'API_TYPE': 'HEALTH'}))
    assert bad['status'] == 503, bad
    assert entry._APP is None
