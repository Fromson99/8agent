"""Filename version selection: deterministic synthetic contracts, no model calls."""
import copy
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest
from semantic_runtime.contracts import digest, sha, write
from lawrag.pipeline import document_representations as reps
from lawrag.pipeline import genos_corpus, genos_stages, team_raw, document_release

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / '06_TOOLS/COMMANDS' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def row(path, body=None, **kw):
    import hashlib
    h = hashlib.sha256((body or path).encode()).hexdigest()
    return {'path': path, 'relative': path, 'source': 'internal', 'name': Path(path).stem,
            'sha256': h, 'document_id': h[:16], 'doc_type': None, 'engine': '', **kw}


def put(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def docx(path, text):
    from docx import Document
    path.parent.mkdir(parents=True, exist_ok=True)
    d = Document(); d.add_heading('제1조(목적)', level=1); d.add_paragraph(text); d.save(path)
    return path


def test_latest_precedes_format_and_preserves_raw_and_audit(tmp_path):
    base = tmp_path / 'RAW/internal/리스크/위험관리'
    for name in ['위험관리(20190710).docx', '위험관리(20220331).pdf', '위험관리(20220331).docx']:
        put(base / name, name)
    before = {p: sha(p) for p in base.iterdir()}
    plan, report = genos_corpus.collect(tmp_path / 'RAW', only_internal=True, skip_invalid=True,
                                        latest_internal_versions=True, emit=lambda _: None)
    assert report['ok'] and len(plan['files']) == 1
    chosen = plan['files'][0]
    assert Path(chosen['path']).name == '위험관리(20220331).docx'
    assert chosen['filename_version']['date'] == '20220331'
    assert all('20190710' not in r['path'] for r in chosen['representations'])
    assert all('20190710' not in r['file_name'] for r in chosen['aliases'])
    excluded = [r for r in report['excluded'] if r['reason'] == 'superseded_filename_version']
    assert len(excluded) == 1 and excluded[0]['sha256'] == sha(base / '위험관리(20190710).docx')
    assert before == {p: sha(p) for p in base.iterdir()}


def test_new_pdf_wins_over_old_docx():
    rows = [row('/a/규정(20190101).docx'), row('/a/규정(20220101).pdf')]
    before = copy.deepcopy(rows)
    selected, excluded = reps.select_latest_internal(rows)
    selected, _ = reps.select(selected)
    assert len(selected) == 1 and selected[0]['path'].endswith('.pdf')
    assert rows == before and excluded[0]['original_preserved']


def test_scope_does_not_mix_folders_roles_or_external_dates():
    rows = [row('/a/규정(20190101).docx'), row('/b/규정(20220101).docx'),
            row('/a/규정(20230101).docx', raw_role='attachment'),
            row('/a/규정(20240101).docx', source='external')]
    selected, excluded = reps.select_latest_internal(rows)
    assert len(selected) == 4 and not excluded
    assert 'filename_version' not in selected[-1]


@pytest.mark.parametrize('date', ['20190229', '20221301', '00000101'])
def test_invalid_date_stops_selection(date):
    with pytest.raises(ValueError, match='Invalid filename'):
        reps.select_latest_internal([row('/a/규정(' + date + ').docx')])


def test_undated_family_and_same_date_conflicts_are_not_guessed():
    with pytest.raises(ValueError, match='Dated and undated'):
        reps.select_latest_internal([row('/a/규정.docx'), row('/a/규정(20200101).docx')])
    with pytest.raises(ValueError, match='Conflicting latest'):
        reps.select_latest_internal([row('/a/규정(20200101).docx'), row('/a/규정(20200101)(2).docx')])
    selected, _ = reps.select_latest_internal([row('/a/규정(20200101).docx', 'same'),
                                               row('/a/규정(20200101)(2).docx', 'same')])
    selected, _ = reps.select(selected)
    assert len(selected) == 1


def test_undated_other_titles_and_six_digit_names_are_retained():
    rows = [row('/a/별도규정(170817).docx'), row('/a/별표.docx'), row('/a/규정(20240229).docx')]
    selected, excluded = reps.select_latest_internal(rows)
    assert len(selected) == 3 and not excluded
    with pytest.raises(ValueError, match='Dated and undated'):
        reps.select_latest_internal([row('/a/규정(170817).docx'), row('/a/규정(20240229).docx')])


def test_team_selection_before_explicit_representation_group(tmp_path):
    files = {}
    for date in ['20190710', '20220331']:
        path = put(tmp_path / ('RAW/internal/risk_team/규정/규정(' + date + ').docx'), date)
        files[str(path.relative_to(tmp_path))] = {'sha256': sha(path), 'scope_document': '규정', 'name': '규정'}
    write(tmp_path / 'CATALOG/TEAM_LAYOUT.json', {'schema_version': team_raw.VERSION, 'files': files})
    plan, report = team_raw.collect(tmp_path, latest_internal_versions=True, emit=lambda _: None)
    assert report['ok'] and len(plan['files']) == 1
    assert '20220331' in plan['files'][0]['path']
    assert all('20190710' not in p['path'] for p in plan['files'][0]['representations'])


def test_default_preserves_historical_versions(tmp_path):
    for date in ['20190710', '20220331']:
        put(tmp_path / ('internal/규정(' + date + ').docx'), date)
    plan, report = genos_corpus.collect(tmp_path, only_internal=True, skip_invalid=True, emit=lambda _: None)
    assert report['ok'] and len(plan['files']) == 2
    assert 'internal_version_policy' not in plan


def test_cli_inventory_and_changed_selection_resume_rejected(tmp_path, monkeypatch):
    cli = module('genos_data_stages')
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda _: tmp_path)
    monkeypatch.setattr(genos_stages, 'execute', lambda *a, **kw: pytest.fail('check-only called structure'))
    for date in ['20190710', '20220331']:
        put(tmp_path / ('RAW/internal/규정(' + date + ').docx'), date)
    args = ['--only-internal', '--latest-internal-versions', '--run-id', 'latest', '--check-only']
    assert cli.main(args) == 0
    assert cli.main(args) == 0
    logs = tmp_path / 'LOGS/latest'
    binding = (logs / 'filename-version-selection.json').read_bytes()
    inventories = sorted(logs.glob('inventory-*.json'))
    assert len(json.loads(inventories[-1].read_text())['files']) == 1
    put(tmp_path / 'RAW/internal/규정(20250101).docx', 'new')
    assert cli.main(args) == 1
    assert (logs / 'filename-version-selection.json').read_bytes() == binding
    assert cli.main([a for a in args if a != '--latest-internal-versions']) == 1
    assert not (tmp_path / 'STRUCTURE').exists()


@pytest.mark.parametrize('option', ['--only-internal-pdf', '--exclude-internal'])
def test_conflicting_cli_scope_rejected(tmp_path, monkeypatch, option):
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda _: tmp_path)
    with pytest.raises(SystemExit):
        module('genos_data_stages').main(['--latest-internal-versions', option, '--check-only'])


def test_composed_passes_policy_and_refuses_base_before_calls():
    cli = module('composed_build')
    calls = []
    assert cli.run(['--run-id', 'latest', '--latest-internal-versions', '--no-models', '--check-only'],
                   call=lambda cmd: calls.append(cmd) or 0) == 0
    assert '--latest-internal-versions' in calls[0]
    calls.clear()
    with pytest.raises(SystemExit):
        cli.run(['--run-id', 'latest', '--latest-internal-versions', '--base-generation', '/old'],
                call=lambda cmd: calls.append(cmd) or 0)
    assert not calls


@pytest.mark.parametrize('index_mode', ['legacy', 'compact-v2'])
def test_latest_structure_merge_index_and_search_consumer(tmp_path, monkeypatch, term_glossary, index_mode):
    from lawrag.pipeline.term_generation import build_generation
    from lawrag.pipeline.term_serving_bundle import verify_assets
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM', 'off')
    raw = tmp_path / 'RAW'
    old = docx(raw / 'internal/모의규정(20190710).docx', '폐기예시옛본문 고유문자열')
    new = docx(raw / 'internal/모의규정(20220331).docx', '영업일은 은행이 영업하는 날을 말한다. 최신예시본문')
    plan, report = genos_corpus.collect(raw, only_internal=True, skip_invalid=True,
                                       latest_internal_versions=True, emit=lambda _: None)
    assert report['ok'] and len(plan['files']) == 1
    r = plan['files'][0]
    folder, _ = genos_stages.structure(r, plan, tmp_path, {'synthetic': 'no-model'}, 30, lambda _: None)
    genos_stages.verify_structure(folder)
    # Same selected bytes resume, a changed input is refused before cache reuse.
    assert genos_stages.structure(r, plan, tmp_path, {'synthetic': 'no-model'}, 30, lambda _: None)[0] == folder
    write(tmp_path / 'LOGS/latest/structure-selection.json', {
        'schema_version': 'structure-selection-v1', 'inputs_sha256': digest(plan), 'completed': True,
        'expected_document_ids': [r['document_id']],
        'documents': {r['document_id']: {'key': folder.name, 'receipt_sha256': sha(folder / 'structure-receipt.json')}}})
    with pytest.raises(ValueError, match='cannot merge base'):
        document_release.selected_sources(tmp_path, 'latest', [tmp_path / 'old-generation'])
    sources, _ = document_release.selected_sources(tmp_path, 'latest', [])
    merged = document_release.merge_sources(sources, tmp_path / 'merged')
    settings = ({'storage_profile': 'compact-v2', 'fulltext_granularity': 'unit',
                 'audit_profile': 'factorized-v1'} if index_mode == 'compact-v2' else {})
    build_generation(merged, term_glossary, tmp_path / 'built', serving=True, **settings)
    generation = tmp_path / 'built/generation'
    assert verify_assets(generation)['verified']
    with closing(Store(generation)) as store:
        ids = [v[0] for v in store.db.execute('SELECT document_id FROM document')]
        assert ids == [sha(new)[:16]] and sha(old)[:16] not in ids
        texts = ' '.join(v[0] for v in store.db.execute('SELECT text FROM source_block'))
        assert '최신예시본문' in texts and '폐기예시옛본문' not in texts
        payload = json.loads(store.db.execute('SELECT json FROM document').fetchone()[0])
        assert payload['document_metadata']['filename_version']['date'] == '20220331'
        index = TermIndex(generation / 'navigation', store)
        tools = index.tools(ids)
        try:
            assert tools.search(['fixture:day'], ids)
        finally:
            tools.db.close()
    assert old.exists() and new.exists() and not (tmp_path / 'generations/CURRENT.json').exists()
    from fastapi.testclient import TestClient
    from test_legal_agent_v5 import app_for
    with TestClient(app_for(tmp_path / 'api', generation)) as client:
        listed = client.get('/v1/rag/documents')
        assert listed.status_code == 200
        assert {d['id'] for d in listed.json()['documents']} == {sha(new)[:16]}
        found = client.get('/v1/rag/search', params={'q': '영업일'})
        assert found.status_code == 200 and sha(old)[:16] not in found.text
        assert client.get('/v1/rag/document/read', params={'doc_id': sha(new)[:16]}).status_code == 200
        assert client.get('/v1/rag/document/read', params={'doc_id': sha(old)[:16]}).status_code == 404
    new.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='changed'):
        genos_stages.structure(r, plan, tmp_path, {'synthetic': 'no-model'}, 30, lambda _: None)
