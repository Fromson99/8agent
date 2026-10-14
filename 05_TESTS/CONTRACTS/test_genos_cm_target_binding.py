"""Onsite names/representations bind fresh evidence without weakening old imports."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from lawrag.pipeline import shortcut_package as packages
from semantic_runtime.storage import Store
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.corrected_memory import MemoryError


TITLE = '코스닥시장 상장규정'


def document(ident='onsite', suffix='.hwpx', role='body'):
    name = TITLE + ('_전문' if role == 'body' else '_개정문') + suffix
    return {'id': ident, 'name': 'external > financial_team > krx > '+TITLE+' > '+Path(name).stem,
            'meta': {'document_title': Path(name).stem, 'file_name': name,
                     'folder_names': ['external', 'financial_team', 'krx', TITLE],
                     'relative_path': 'external/financial_team/krx/'+TITLE+'/'+name,
                     'document_role': role}, 'text': '현장 구조화된 제26조 본문\n현재 적용·예외는 다시 판단한다.'}


@pytest.fixture
def target(tmp_path):
    stores = []
    def build(docs, *, coordinate='body:제26조', bad_provenance=False):
        root = tmp_path/('generation-'+str(len(stores))); root.mkdir()
        db = sqlite3.connect(root/'store.sqlite')
        db.executescript('CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);'
                         'CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);'
                         'CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);')
        for doc in docs:
            fingerprint = hashlib.sha256(('onsite input '+doc['id']).encode()).hexdigest()
            db.execute('INSERT INTO document VALUES(?,?,?,?)', (doc['id'], doc['name'], fingerprint,
                       json.dumps({'document_metadata': doc['meta']}, ensure_ascii=False)))
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', (doc['id'], 'target-article', None,
                       json.dumps({'coordinate_key': coordinate, 'span': [1, 2], 'family': 'kr_article'})))
            db.execute('INSERT INTO source_block VALUES(?,?,?,?,?,?)', (doc['id'], '1', 'target-article', doc['text'],
                       'wrong' if bad_provenance else fingerprint, '{}'))
        db.commit(); db.close()
        pin = hashlib.sha256((root/'store.sqlite').read_bytes()).hexdigest()
        manifest = {'schema_version': 'term-source-generation-v1', 'generation_id': root.name,
                    'store_sha256': pin, 'scope': {'document_version_ids': [d['id'] for d in docs]}}
        (root/'manifest.json').write_text(json.dumps(manifest))
        for folder, extra in [('navigation', {'index_sha256': 'target-nav'}),
                              ('fulltext', {'navigation_index_sha256': 'target-nav', 'index_sha256': 'target-fulltext'})]:
            (root/folder).mkdir()
            (root/folder/'manifest.json').write_text(json.dumps({'generation_id': root.name, 'source_store_sha256': pin, **extra}))
        store = Store(root); stores.append(store)
        return store
    yield build
    for store in stores:
        store.close()


@pytest.fixture
def package():
    return {'schema_version': packages.SCHEMA, 'package_id': 'onsite-seeds',
            'visibility': packages.COMMON_VISIBILITY, 'legal_claim_reuse': False,
            'source_binding_policy': packages.TARGET_BINDING,
            'target_source_interpretation': 'CURRENT_SOURCE_REQUIRES_ASSESSMENT',
            'cases': [{'case_id': 'cm-001', 'question': '등록된 규정의 적용은?', 'topic': '상장',
                       'reference_answer': '검토 대상 업무 답변', 'reference_provenance': {},
                       'entries': [{'document_name': TITLE, 'document_name_aliases': [TITLE+'_전문.hwpx'],
                                    'coordinate_key': 'body:제26조', 'source_artifact_sha256': 'local-input-pin',
                                    'section_text_sha256': 'local-structure-pin', 'evidence_role': 'MAIN'}]}]}


def test_portable_registration_uses_target_names_hashes_article_and_idempotent_receipt(target, package, tmp_path):
    store = target([document()]); principal = packages.common_principal(store=store)
    repo = ShortcutRepository(tmp_path/'cases.sqlite')
    try:
        receipt = packages.import_package(repo, principal, package, store)
        page = repo.current(receipt['records'][0]['unit_id'], 1, principal)
        evidence = page['core_evidence_route']['targets'][0]
        assert evidence['document_name'] == document()['name']
        assert evidence['canonical_document_name'] == TITLE
        assert evidence['document_id'] == 'onsite' and evidence['article_unit_id'] == 'target-article'
        assert evidence['source_artifact_sha256'] != 'local-input-pin'
        assert evidence['section_text_sha256'] == packages.text_sha(document()['text'])
        assert receipt['source_binding']['store_sha256'] == store.manifest['store_sha256']
        assert packages.import_package(repo, principal, package, store)['already_imported']
        assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0] == 1
        assert page['claims'] == page['procedures'] == []
    finally:
        repo.close()


def test_strict_import_still_rejects_different_names_and_hashes(target, package):
    store = target([document()]); strict = deepcopy(package); strict.pop('source_binding_policy')
    with pytest.raises(MemoryError, match='source document version'):
        packages.resolve(strict, store, packages.common_principal(store=store))


def test_body_selection_prefers_html_and_does_not_select_amendment(target, package):
    store = target([document('native'), document('html', '.html'), document('revision', '.html', 'amendment')])
    _, records = packages.resolve(package, store, packages.common_principal(store=store))
    assert records[0]['targets'][0]['document_id'] == 'html'


def test_path_display_without_metadata_still_matches_exact_body_suffix(target, package):
    doc = document(); doc['meta'] = {}
    store = target([doc])
    assert packages.resolve(package, store, packages.common_principal(store=store))[1][0]['targets'][0]['document_id'] == 'onsite'


@pytest.mark.parametrize('suffix', [' 본문.xml', '_본문.xml', '-본문.xml'])
def test_xml_body_suffix_without_canonical_folder_binds_current_article(target, package, suffix):
    doc=document();doc['name']=TITLE+suffix;doc['meta']={}
    store=target([doc])
    _,records=packages.resolve(package,store,packages.common_principal(store=store))
    assert records[0]['targets'][0]['document_id']=='onsite'
    assert records[0]['targets'][0]['source_artifact_sha256']!='local-input-pin'


@pytest.mark.parametrize('variant', [' 시행령 본문.xml', ' 시행규칙 본문.xml', ' 개정문 본문.xml'])
def test_body_suffix_does_not_merge_other_laws_or_revision_documents(target, package, variant):
    doc=document();doc['name']=TITLE+variant;doc['meta']={}
    store=target([doc])
    with pytest.raises(MemoryError,match='target body document missing'):
        packages.resolve(package,store,packages.common_principal(store=store))


@pytest.mark.parametrize('variant', ['시행세칙', '개정문', '신구조문대비표'])
def test_similar_title_and_revision_are_not_body_fallbacks(target, package, variant):
    doc = document()
    if variant == '시행세칙':
        doc['name'] = TITLE+' 시행세칙_전문'; doc['meta'] = {'document_title': doc['name']}
    else:
        doc['meta']['file_name'] = TITLE+'_'+variant+'.hwpx'
    store = target([doc])
    with pytest.raises(MemoryError, match='target body document missing'):
        packages.resolve(package, store, packages.common_principal(store=store))


def test_multiple_body_versions_are_atomic_and_diagnostic(target, package, tmp_path):
    store = target([document('version-a'), document('version-b')])
    repo = ShortcutRepository(tmp_path/'cases.sqlite')
    try:
        with pytest.raises(MemoryError, match='target body document ambiguous'):
            packages.import_package(repo, packages.common_principal(store=store), package, store)
        assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0] == 0
    finally:
        repo.close()


@pytest.mark.parametrize('variant', ['missing_article', 'provenance', 'permission', 'interpretation'])
def test_portable_binding_keeps_article_source_and_authority_checks(target, package, variant):
    store = target([document()], coordinate='body:제99조' if variant == 'missing_article' else 'body:제26조',
                   bad_provenance=variant == 'provenance')
    principal = packages.common_principal(store=store)
    if variant == 'permission':
        principal['document_ids'] = []
    if variant == 'interpretation':
        package['target_source_interpretation'] = 'APPROVED'
    with pytest.raises(MemoryError):
        packages.resolve(package, store, principal)
