"""A diagnosis distinguishes identity failures without rewriting source pins."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cm_source_diagnose', ROOT/'06_TOOLS/COMMANDS/genos_cm_source_diagnose.py')
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)
PACKAGE = ROOT/'08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_common_20261007_r6/CM51_SOURCE_PACKAGE.json'


@pytest.fixture
def field(tmp_path):
    transfer = tmp_path/'DEV/TRANSFER'
    artifacts = transfer/'cm-oneclick-r8'
    artifacts.mkdir(parents=True)
    generation = tmp_path/'generation'
    generation.mkdir()
    raw = PACKAGE.read_bytes()
    package = json.loads(raw)
    entries = {(e['document_name'], e['source_artifact_sha256'])
               for c in package['cases'] for e in c['entries']}
    with sqlite3.connect(generation/'store.sqlite') as db:
        db.execute('CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT)')
        db.executemany('INSERT INTO document VALUES(?,?,?)',
                       [(str(i), name, pin) for i, (name, pin) in enumerate(sorted(entries))])
    manifest = {'generation_id': 'synthetic-selected', 'store_sha256': diag.sha((generation/'store.sqlite').read_bytes())}
    (generation/'manifest.json').write_text(json.dumps(manifest))
    config = {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
              'generation': str(generation), 'generation_manifest_sha256': diag.sha((generation/'manifest.json').read_bytes())}
    path = transfer.parent/'00_SYSTEM'
    path.mkdir()
    (path/'GENOS_SERVING_PATHS.json').write_text(json.dumps(config))
    (artifacts/'STATUS.json').write_text(json.dumps(config))
    (artifacts/'CM51_SOURCE_PACKAGE.json').write_bytes(raw)
    return transfer, generation


def test_selected_source_is_read_without_any_input_changes(field):
    transfer, generation = field
    paths = [p for p in transfer.parent.rglob('*') if p.is_file()]+list(generation.iterdir())
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    report = diag.inspect(transfer)
    assert report['counts'] == {'EXACT': 21}
    assert report['registration_performed'] is False
    assert report['store_hash_reverified_by_this_diagnosis'] is True
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def refresh_binding(transfer, generation):
    path = generation/'manifest.json'
    manifest = json.loads(path.read_bytes())
    manifest['store_sha256'] = diag.sha((generation/'store.sqlite').read_bytes())
    path.write_text(json.dumps(manifest))
    for path in (transfer.parent/'00_SYSTEM/GENOS_SERVING_PATHS.json', transfer/'cm-oneclick-r8/STATUS.json'):
        config = json.loads(path.read_bytes())
        config['generation_manifest_sha256'] = diag.sha((generation/'manifest.json').read_bytes())
        path.write_text(json.dumps(config))


@pytest.mark.parametrize('failure', ['NAME_MISSING', 'ARTIFACT_HASH_DIFFERS', 'EXACT_AMBIGUOUS'])
def test_the_three_possible_photo_causes_are_distinguished(field, failure):
    transfer, generation = field
    name = '코스닥시장 상장규정'
    with sqlite3.connect(generation/'store.sqlite') as db:
        if failure == 'NAME_MISSING':
            db.execute('DELETE FROM document WHERE name=?', (name,))
        elif failure == 'ARTIFACT_HASH_DIFFERS':
            db.execute('UPDATE document SET source_artifact_sha256=? WHERE name=?', ('changed', name))
        else:
            db.execute('INSERT INTO document SELECT document_id||?,name,source_artifact_sha256 FROM document WHERE name=?', ('-duplicate', name))
    refresh_binding(transfer, generation)
    before = (generation/'store.sqlite').read_bytes()
    row = next(r for r in diag.inspect(transfer)['documents'] if r['document_name'] == name)
    assert row['classification'] == failure
    assert (generation/'store.sqlite').read_bytes() == before


def test_spacing_suggestion_is_not_accepted_as_a_match(field):
    transfer, generation = field
    with sqlite3.connect(generation/'store.sqlite') as db:
        db.execute('UPDATE document SET name=? WHERE name=?', ('코스닥시장상장규정', '코스닥시장 상장규정'))
    refresh_binding(transfer, generation)
    row = next(r for r in diag.inspect(transfer)['documents'] if r['document_name'] == '코스닥시장 상장규정')
    assert row['classification'] == 'NAME_MISSING'
    assert row['spacing_name_suggestions_only'][0]['name'] == '코스닥시장상장규정'
    assert row['identity_classification'] == 'HASH_MATCH_DIFFERENT_NAME'


@pytest.mark.parametrize('target', ['package', 'binding'])
def test_changed_original_package_or_generation_binding_is_rejected(field, target):
    transfer, generation = field
    if target == 'package':
        path = transfer/'cm-oneclick-r8/CM51_SOURCE_PACKAGE.json'
        package = deepcopy(json.loads(path.read_bytes()))
        package['cases'][0]['entries'][0]['source_artifact_sha256'] = 'replacement'
        path.write_text(json.dumps(package))
    else:
        (generation/'manifest.json').write_text('{"generation_id":"changed"}')
    with pytest.raises(ValueError):
        diag.inspect(transfer)


def test_global_hash_search_finds_renamed_original_even_when_wrong_same_name_exists():
    expected = [{'document_id': 'old', 'name': '원래 문서명', 'source_artifact_sha256': 'original'}]
    actual = [{'document_id': 'different', 'name': '원래 문서명', 'source_artifact_sha256': 'wrong'},
              {'document_id': 'right', 'name': '바뀐 표시명', 'source_artifact_sha256': 'original'}]
    row = diag.identities(expected, actual)[0]
    assert row['classification'] == 'ARTIFACT_HASH_DIFFERS'
    assert row['identity_classification'] == 'HASH_MATCH_DIFFERENT_NAME'
    assert row['hash_matches_without_name'][0]['document_id'] == 'right'


def test_whole_inventory_is_bidirectional_and_name_change_is_separate():
    expected = [{'document_id': 'one', 'name': 'A', 'source_artifact_sha256': 'a'},
                {'document_id': 'two', 'name': 'B', 'source_artifact_sha256': 'b'}]
    actual = deepcopy(expected)
    actual[0]['name'] = 'new A'
    result = diag.compare_all({'documents': expected}, actual)
    assert result['hash_inventory_equal_without_name']
    assert not result['name_and_hash_inventory_equal']
    assert result['hash_counts_without_name'] == {'HASH_MATCH_DIFFERENT_NAME': 1, 'HASH_MATCH_SAME_NAME': 1}
    actual.append({'document_id': 'three', 'name': 'C', 'source_artifact_sha256': 'extra'})
    result = diag.compare_all({'documents': expected}, actual)
    assert not result['hash_inventory_equal_without_name']
    assert len(result['selected_only_hash_documents']) == 1


def test_renamed_duplicate_cannot_be_treated_as_a_unique_original():
    expected = [{'document_id': 'one', 'name': 'A', 'source_artifact_sha256': 'a'}]
    actual = [*expected, {'document_id': 'two', 'name': 'other A', 'source_artifact_sha256': 'a'}]
    result = diag.compare_all({'documents': expected}, actual)
    assert result['hash_counts_without_name'] == {'HASH_AMBIGUOUS': 1}
    assert not result['hash_inventory_equal_without_name']
    assert len(result['selected_duplicate_hash_groups']) == 1


def test_database_hash_change_without_new_manifest_is_rejected(field):
    transfer, generation = field
    with sqlite3.connect(generation/'store.sqlite') as db:
        db.execute('UPDATE document SET name=?', ('unrecorded change',))
    with pytest.raises(ValueError, match='store_sha256'):
        diag.inspect(transfer)
