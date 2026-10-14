"""R13 source names and roles identify individual documents, never parent folders."""
import json
from pathlib import Path
import unicodedata
from copy import deepcopy
from unittest.mock import patch

import pytest

from test_genos_cm_target_binding import target, package, document, TITLE
from lawrag.pipeline import shortcut_package as cm
from lawrag.pipeline.document_representations import metadata
from semantic_runtime.legal_agent.corrected_memory import MemoryError
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository

ROOT = Path(__file__).resolve().parents[2]


def test_replay_rejects_new_resolution_that_differs_from_stored_registration(target, package, tmp_path):
    store = target([document()]);principal = cm.common_principal(store=store)
    repo = ShortcutRepository(tmp_path/'cases.sqlite')
    try:
        receipt = cm.import_package(repo, principal, package, store)
        before = list(repo.db.execute('SELECT id,payload FROM sw_import'))
        binding, cases = cm.resolve(package, store, principal)
        changed = deepcopy(cases);changed[0]['targets'][0]['document_id'] = 'different-document'
        with patch.object(cm, 'resolve', return_value=(binding, changed)):
            with pytest.raises(MemoryError, match='existing import source resolution differs'):
                cm.import_package(repo, principal, package, store)
        assert list(repo.db.execute('SELECT id,payload FROM sw_import')) == before
        assert repo.db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0] == 1
        assert cm.import_package(repo, principal, package, store)['already_imported']
    finally:
        repo.close()


@pytest.mark.parametrize('title', ['기업공시서식 작성기준(2026.8.3 시행)', '별지서식(2026.7.28 시행)'])
def test_registered_body_titles_containing_form_words_are_not_attachments(target, package, title):
    entry = package['cases'][0]['entries'][0];entry['document_name'] = title;entry['document_name_aliases'] = []
    d = document();d['name'] = title
    d['meta'] = {'document_title': title, 'file_name': title+'.pdf', 'document_role': 'body'}
    store = target([d])
    assert cm.resolve(package, store, cm.common_principal(store=store))[1][0]['targets'][0]['document_id'] == 'onsite'


@pytest.mark.parametrize('suffix', [' 시행령 본문.xml', ' 시행규칙_전문.hwpx', ' 시행세칙 조문.html'])
@pytest.mark.parametrize('role', [None, 'body'])
def test_parent_title_does_not_identify_another_law(target, package, suffix, role):
    d = document();filename = TITLE+suffix
    d['name'] = 'external > '+TITLE+' > '+Path(filename).stem
    d['meta'] = {'document_title': Path(filename).stem, 'file_name': filename,
                 'folder_names': ['external', TITLE]}
    if role:d['meta']['document_role'] = role
    store = target([d])
    with pytest.raises(MemoryError, match='target body document missing'):
        cm.resolve(package, store, cm.common_principal(store=store))


@pytest.mark.parametrize('suffix', ['_신·구조문대비표.pdf', '_신_구조문대비표.pdf', '_제정안.pdf',
    '_요약.pdf', '_참고.pdf', '_개정(202609).pdf', '_[별첨].pdf', '_부록.pdf', '_개정문.pdf'])
@pytest.mark.parametrize('nfd', [False, True])
def test_nonbody_markers_cannot_be_hidden_by_canonical_metadata(target, package, suffix, nfd):
    d = document();filename = TITLE+suffix
    if nfd:filename = unicodedata.normalize('NFD', filename)
    d['meta'].update(document_title=TITLE, file_name=filename)
    store = target([d])
    with pytest.raises(MemoryError, match='target body document missing'):
        cm.resolve(package, store, cm.common_principal(store=store))


@pytest.mark.parametrize('suffix', [' 시행령 본문.xml', ' 시행세칙_전문.hwpx'])
def test_canonical_title_does_not_override_contradictory_physical_law(target, package, suffix):
    d = document();d['meta'].update(document_title=TITLE, file_name=TITLE+suffix)
    store = target([d])
    with pytest.raises(MemoryError, match='target body document missing'):
        cm.resolve(package, store, cm.common_principal(store=store))


@pytest.mark.parametrize('title', ['규정 (2)', '규정(2025)', 'A·B 규정', '서식 작성기준'])
def test_actual_titles_keep_numbers_dates_and_punctuation(title):
    entry = {'document_name': title}
    doc = {'name': 'external > '+title, 'json': json.dumps({'document_metadata': {
        'document_title': title, 'file_name': 'server-download.pdf', 'document_role': 'body'}})}
    assert cm.body_name_match(doc, entry)
    doc['json'] = '{}';doc['name'] = title+' 별첨.pdf'
    assert not cm.body_name_match(doc, entry)


def test_original_filename_and_same_source_alias_identify_a_sanitized_physical_name():
    entry = {'document_name': 'A·B 규정'}
    doc = {'name': 'sha16__A_B 규정', 'json': json.dumps({'document_metadata': {
        'file_name': 'sha16__A_B 규정.pdf', 'orig_filename': 'A·B 규정.pdf', 'document_role': 'body'}})}
    assert cm.body_name_match(doc, entry)
    doc['json'] = '{}'
    assert not cm.body_name_match(doc, entry)


@pytest.mark.parametrize('folder', ['별표서식', '별표', '별지', '서식', '별지서식', '별표·서식'])
def test_annex_folder_cannot_override_body_title(folder):
    doc = {'name': TITLE, 'json': json.dumps({'document_metadata': {
        'document_title': TITLE, 'file_name': TITLE+'.pdf', 'folder_path': 'external > '+folder}})}
    assert not cm.body_name_match(doc, {'document_name': TITLE})


def test_real_registered_external_bodies_and_cm_cross_title_matrix():
    layout = json.loads((ROOT/'01_DATA/CATALOG/TEAM_LAYOUT.json').read_text())
    cm_names = {a['law'] for c in json.loads((ROOT/'01_DATA/review/cm_core_e2e_v3.json').read_text())['cases']
                for a in c['evidence_articles']}
    count = 0
    for path, item in layout['files'].items():
        if item.get('source') != 'external' or item.get('role') != 'body':continue
        title = item.get('scope_document') or item.get('name')
        meta = {**metadata({'relative': path.removeprefix('RAW/'), 'name': title,
                           'source': 'external', 'team': item['team']}), 'document_role': 'body'}
        doc = {'name': meta['display_name'], 'json': json.dumps({'document_metadata': meta})}
        assert cm.body_name_match(doc, {'document_name': title}),path
        if title in cm_names:
            assert all(not cm.body_name_match(doc, {'document_name': other}) for other in cm_names-{title})
        count += 1
    assert count == 114
