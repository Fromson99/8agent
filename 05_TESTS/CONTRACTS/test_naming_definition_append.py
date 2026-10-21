"""Data maintenance contracts; no model or retrieval quality comparison."""
from contextlib import closing
import json
import sqlite3
import pytest
from lawrag.pipeline import naming_definition_append as patch
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.contracts import sha
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from semantic_runtime import unit_fulltext
from test_document_release import source


def refs_for(text, locators):
    return [dict(id='r'+str(i), mention_start=text.index(s), mention_end=text.index(s)+len(s),
                 resolution='EXACT_NAMED_DOCUMENT_ARTICLE', targets=[{'source_id':'s'+str(i)}])
            for i, s in enumerate(locators)]


def test_each_name_binds_only_its_own_reference():
    text = ('규정 제1조제2항에 따른 비율(이하 유동성비율이라 한다), '
            '규정 제2조제6항에 따른 비율(이하 단기금융업무 유동성비율이라 한다), '
            '규정 제3조제1항에서 정하는 비율(이하 “계좌비율”이라 한다)은 산정한다.')
    rows = list(patch.candidates(text, refs_for(text, ['제1조제2항', '제2조제6항', '제3조제1항'])))
    assert [(r['term'],r['reference']['id']) for r in rows] == [
        ('유동성비율','r0'), ('단기금융업무 유동성비율','r1'), ('계좌비율','r2')]
    assert not any(r['hold_reason'] for r in rows)
    assert all(text[r['term_start']:r['term_end']] == r['term'] for r in rows)


def test_multiple_references_and_unresolved_are_held():
    text = '제1조 및 제2조에 따른 비율(이하 비교비율이라 한다)'
    rows = list(patch.candidates(text, refs_for(text, ['제1조','제2조'])))
    assert rows[0]['hold_reason'] == 'MULTIPLE_REFERENCES_IN_NAMING_CLAUSE'
    text = '제1조에 따른 비율(이하 비율이라 한다)'
    refs = refs_for(text, ['제1조']); refs[0]['targets'] = []
    assert next(patch.candidates(text, refs))['hold_reason'] == 'REFERENCE_NOT_UNIQUELY_RESOLVED'
    assert not list(patch.candidates('금융규정(이하 “규정”이라 한다)', []))


def test_explicit_scope_is_not_part_of_the_term():
    text='제1조에 따른 자산(이하 이 조에서 "해당자산"이라 한다)'
    result=next(patch.candidates(text,refs_for(text,['제1조'])))
    assert result['term']=='해당자산' and result['hold_reason'] is None
    assert result['scope_hint'][0]['text']=='이 조에서'
    text='제1조에 따른 자산(이하 이 조 및 제3조에서 "해당자산"이라 한다)'
    result=next(patch.candidates(text,refs_for(text,['제1조','제3조'])))
    assert result['hold_reason']=='COMPLEX_NAME_OR_SCOPE_REQUIRES_REVIEW'


@pytest.fixture
def base(tmp_path, term_glossary):
    raw = source(tmp_path / 'source.sqlite', [
        ('law', '가상규정', ['비율은 100분의 100 이상이어야 한다.', '다른 비율 기준.']),
        ('rule', '가상시행세칙', ['「가상규정」 제1조에 따른 비율(이하 가상비율이라 한다), '
                            '「가상규정」 제2조에 따른 비율(이하 별도비율이라 한다)을 계산한다.'])])
    build_generation(raw, term_glossary, tmp_path / 'base', serving=True,
                     storage_profile='compact-v2', audit_profile='factorized-v1',
                     fulltext_granularity='unit', fulltext_workers=1)
    return tmp_path / 'base/generation'


def test_incremental_patch_is_readable_preserves_rows_and_reuses_fulltext(base, tmp_path, monkeypatch):
    monkeypatch.setattr(unit_fulltext, 'build', lambda *a, **k: pytest.fail('must not rebuild fulltext'))
    pins = patch.input_pins(base)
    out = tmp_path / 'augmented'
    result = patch.augment(base, out)
    assert result['definitions_added'] == result['links_added'] == 2
    assert result['documents_retokenized'] == result['model_calls'] == 0
    assert patch.input_pins(base) == pins
    assert sha(out/'generation/fulltext/units.sqlite') == sha(base/'fulltext/units.sqlite')
    assert patch.augment(base,out) == result
    with closing(Store(out/'generation')) as store:
        index = TermIndex(out/'generation/navigation',store)
        tools = index.tools(['rule'])
        try:
            assert {d['key'] for d in tools.definitions.values()} == {'가상비율','별도비율'}
            assert all(not d['canonical_approval'] for d in tools.definitions.values())
        finally:
            tools.db.close()
        denied = index.tools(['law'])
        try:
            assert not denied.definitions
        finally:
            denied.db.close()


def test_scope_invalid_inputs_and_output_drift(base, tmp_path):
    with pytest.raises(ValueError, match='scope'):
        patch.augment(base,tmp_path/'unknown',document_ids=['missing'])
    out = tmp_path/'scoped'
    assert patch.augment(base,out,document_ids=['law'])['definitions_added'] == 0
    with pytest.raises(ValueError, match='identity changed'):
        patch.augment(base,out,document_ids=['rule'])
    with (out/'generation/navigation/navigation.sqlite').open('ab') as f:
        f.write(b'tamper')
    with pytest.raises(ValueError, match='output drift'):
        patch.verify(out)


def test_failed_attempt_preserved_then_retry(base,tmp_path,monkeypatch):
    original = patch.append_rows
    def fail(*args,**kwargs):
        raise OSError('injected disk failure')
    monkeypatch.setattr(patch,'append_rows',fail)
    out=tmp_path/'recovered'
    with pytest.raises(OSError,match='disk failure'):
        patch.augment(base,out)
    failures=list(tmp_path.glob('.recovered.attempt-*/failure.json'))
    assert len(failures)==1 and not out.exists()
    assert json.loads(failures[0].read_text())['published'] is False
    monkeypatch.setattr(patch,'append_rows',original)
    assert patch.augment(base,out)['definitions_added']==2
    assert failures[0].exists()


def test_corrupt_reference_witness_never_added(base):
    with closing(Store(base)) as store, closing(sqlite3.connect(':memory:')) as db:
        with closing(patch.ro(base/'navigation/navigation.sqlite')) as source_db:
            source_db.backup(db)
        db.execute("UPDATE reference_payload SET json=json_set(json,'$.mention_start',9999)")
        before=db.execute('SELECT count(*) FROM definition').fetchone()[0]
        with pytest.raises(ValueError,match='witness/span/hash'):
            with db:
                patch.append_rows(db,store)
        assert db.execute('SELECT count(*) FROM definition').fetchone()[0]==before


def test_official_delegation_metadata_is_not_an_inline_naming_witness(base):
    with closing(Store(base)) as store, closing(sqlite3.connect(':memory:')) as db:
        with closing(patch.ro(base/'navigation/navigation.sqlite')) as source_db:
            source_db.backup(db)
        raw = json.loads(db.execute('SELECT json FROM reference_payload LIMIT 1').fetchone()[0])
        raw.update(id='official-test', mention_start=0, mention_end=0, mention_text='',
                   resolution='OFFICIAL_DELEGATION', origins=['official_delegation_lawgokr'])
        columns=[r[1] for r in db.execute('PRAGMA table_info(reference_payload)')]
        assert columns == ['id','document_id','json']
        db.execute('INSERT INTO reference_payload VALUES (?,?,?)',('official-test',raw['document_id'],json.dumps(raw)))
        result=patch.append_rows(db,store)
        assert result['excluded_official_delegations']==1 and result['definitions_added']==2
