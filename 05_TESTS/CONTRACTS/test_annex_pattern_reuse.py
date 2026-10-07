"""Bound regex work for legacy annex linking, without timing assertions."""
import json
import re
import sqlite3

import pytest

from semantic_runtime import term_references, term_references_legacy
from test_annex_linking import source_rows


def database(title='대상준칙', mentions=('적용은 대상준칙 별표 1에 따른다.',), documents=1):
    db = sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
      CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
      CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));''')
    rows = [('caller', 'own', '호출준칙', '문서 개요', ['본문.', *mentions]),
            ('target', 'external', title, '별표 1 기준', ['표 본문.'])]
    rows += [(f'dummy-{n}', f'dummy-{n}', f'RAW > law > 보조준칙{n}', '문서 개요', ['본문.'])
             for n in range(documents-1)]
    source_rows(db, rows)
    return db


@pytest.fixture
def patterns(monkeypatch):
    found = []
    class RegexSpy:
        def __getattr__(self, name):
            return getattr(re, name)
        def compile(self, pattern, *args, **kwargs):
            if pattern.startswith(r'(?<![가-힣A-Za-z0-9])'):
                found.append(pattern)
            return re.compile(pattern, *args, **kwargs)
    monkeypatch.setattr(term_references_legacy, 're', RegexSpy())
    return found


def references(db):
    return [json.loads(row[0]) for row in db.execute('SELECT json FROM reference ORDER BY id')]


def test_more_titles_than_regex_cache_still_compile_once(patterns):
    # 600 distinct names exceed the shared regex cache; 64 citations reuse them.
    with database(documents=300, mentions=('적용은 대상준칙 별표 1에 따른다.',)*64) as db:
        assert term_references.compile_references(db) == (64, 0)
        assert all(row['target_source_ids']==['target'] for row in references(db))
        assert db.execute('SELECT count(*) FROM reference_end WHERE source_id=?',
                          ('target',)).fetchone()[0]==64
    assert len(patterns)==600
    assert len(set(patterns))==len(patterns)


@pytest.mark.parametrize('mentions', [(), ('인용 없는 문장.',), ('적용은 「대상준칙」 별표 1에 따른다.',)])
def test_unused_fallback_does_not_compile_titles(patterns, mentions):
    with database(mentions=mentions) as db:
        term_references.compile_references(db)
        if mentions and '「' in mentions[0]:
            assert references(db)[0]['target_source_ids']==['target']
    assert patterns==[]


def test_patterns_are_scoped_to_each_selected_build(patterns):
    with database(title='이전준칙', mentions=('적용은 이전준칙 별표 1에 따른다.',)) as db:
        assert term_references.compile_references(db)==(1,0)
    patterns.clear()
    with database(title='새준칙', mentions=('적용은 이전준칙 별표 1에 따른다.',)) as db:
        assert term_references.compile_references(db)==(1,1)
        assert references(db)[0]['target_source_ids']==[]
        assert references(db)[0]['reason']=='ANNEX_BODY_NOT_IN_SELECTION'
    assert len(patterns)==2
    assert all('이전준칙' not in pattern for pattern in patterns)
