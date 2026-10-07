"""Abbreviation links: deterministic standalone check, GENOS sense choice, new generation."""
import hashlib
import json
import sqlite3

import pytest

from lawrag.pipeline import glossary_abbreviation as abbr
from lawrag.pipeline.glossary_v1 import label_parts

CB_CREDIT = 'econedu:row:cb'
CB_BOND = 'moleg:knowledge_terms:cb'
LP = 'econedu:row:lp'
ARTICLES = {
    'a-credit': '개인신용평가회사(CB)는 신용정보를 수집한다.',
    'a-bond': '최근 3년간 CB·BW를 발행한 적이 있는가? 전환사채 발행 내역을 적는다.',
    'a-unclear': '별표 CB 항목을 참고한다.',
    'a-full': '크레딧뷰로(Credit Bureau) 제도와 CB의 역할',
    'a-lpg': '연료는 L P G 를 사용한다.',
}
LINKS = [(CB_CREDIT, 'a-credit'), (CB_CREDIT, 'a-bond'), (CB_CREDIT, 'a-unclear'), (CB_CREDIT, 'a-full'),
         (CB_BOND, 'a-credit'), (CB_BOND, 'a-bond'), (LP, 'a-lpg')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def generation(tmp_path):
    root = tmp_path / 'gen'
    (root / 'navigation').mkdir(parents=True)
    (root / 'glossary').mkdir()
    (root / 'store.sqlite').write_bytes(b'store')
    db = sqlite3.connect(root / 'navigation/navigation.sqlite')
    db.executescript('''CREATE TABLE term(id TEXT PRIMARY KEY,json TEXT);
        CREATE TABLE term_surface(term_id,key,text,kind);
        CREATE TABLE source(id TEXT PRIMARY KEY,document_id,article,json);
        CREATE TABLE occurrence(term_id,source_id);
        CREATE TABLE occurrence_origin(term_id,source_id,origin);
        CREATE TABLE term_stats(term_id,n);''')
    for tid, label in ((CB_CREDIT, 'CB(Credit Bureau)'), (CB_BOND, '전환사채'), (LP, 'LP(limited partner)')):
        db.execute('INSERT INTO term VALUES (?,?)', (tid, json.dumps({'id': tid, 'label': label})))
    db.executemany('INSERT INTO term_surface VALUES (?,?,?,?)', [
        (CB_CREDIT, 'cb', 'CB', 'SOURCE_LABEL_PART'), (CB_CREDIT, 'creditbureau', 'Credit Bureau', 'SOURCE_ENGLISH'),
        (CB_BOND, 'cb', 'CB', 'ALIAS'), (LP, 'lp', 'LP', 'SOURCE_LABEL_PART')])
    for sid, text in ARTICLES.items():
        db.execute('INSERT INTO source VALUES (?,?,?,?)', (sid, 'doc', sid, json.dumps(
            {'text': text, 'document_name': '규정', 'heading': sid}, ensure_ascii=False)))
    db.executemany('INSERT INTO occurrence VALUES (?,?)', LINKS)
    db.executemany("INSERT INTO occurrence_origin VALUES (?,?,'x')", LINKS)
    db.commit(); db.close()
    words = sqlite3.connect(root / 'glossary/dictionary.sqlite')
    words.execute('CREATE TABLE entry(id,source,label,key,definition,english,hanja,provenance)')
    words.execute("INSERT INTO entry VALUES (?,'econedu','CB(Credit Bureau)','','개인의 신용정보를 모아 신용평점을 매기는 회사','','','{}')", (CB_CREDIT,))
    words.commit(); words.close()
    (root / 'navigation/manifest.json').write_text(json.dumps({'counts': {'occurrence': len(LINKS)},
                                                              'index_sha256': sha(root / 'navigation/navigation.sqlite')}))
    (root / 'manifest.json').write_text(json.dumps({'navigation': {'path': 'navigation',
                                                                   'manifest_sha256': sha(root / 'navigation/manifest.json')}}))
    return root


class FakeGenos:
    def __init__(self):
        self.calls = []

    def prepare(self):
        return {'backend': 'fake'}

    def call(self, role, task, data, schema):
        self.calls.append(data)
        decisions = []
        for c in data['contexts']:
            text = ' '.join(c['text'])
            if '신용정보' in text:
                d = ('MATCHED', [CB_CREDIT], '개인신용평가회사')
            elif '전환사채' in text or 'BW' in text:
                d = ('MATCHED', [CB_BOND], '전환사채')
            else:
                d = ('UNKNOWN', [], '')
            decisions.append({'context_id': c['context_id'], 'sense': d[0], 'candidate_ids': d[1], 'context_meaning': d[2]})
        return {'job_id': data['job_id'], 'input_sha256': data['input_sha256'], 'decisions': decisions, 'rationale': '합성'}, {'fake': True}


def test_abbreviation_review_drops_only_other_senses(generation, tmp_path):
    before = sha(generation / 'navigation/navigation.sqlite')
    plan = abbr.prepare(generation, tmp_path / 'state')
    # a-full names Credit Bureau and a-bond names 전환사채: not abbreviation-only links.
    # LP inside 'L P G' is no word of its own.
    assert plan['links'] == {'NO_STANDALONE': 1, 'PENDING': 4} and plan['jobs'] == {'pending': 1}
    provider = FakeGenos()
    result = abbr.run(tmp_path / 'state', provider=provider)
    assert result['jobs'] == {'complete': 1}
    assert {c['id'] for c in provider.calls[0]['candidates']} == {CB_CREDIT, CB_BOND}
    assert result['links'] == {'SAME': 1, 'DIFFERENT': 2, 'UNKNOWN': 1, 'NO_STANDALONE': 1}
    out = abbr.apply(tmp_path / 'state', tmp_path / 'new')
    db = sqlite3.connect(tmp_path / 'new/navigation/navigation.sqlite')
    kept = set(db.execute('SELECT term_id,source_id FROM occurrence'))
    assert kept == {(CB_CREDIT, 'a-credit'), (CB_CREDIT, 'a-unclear'), (CB_CREDIT, 'a-full'), (CB_BOND, 'a-bond')}
    assert set(db.execute('SELECT term_id,source_id FROM occurrence_origin')) == kept
    assert db.execute("SELECT context_meaning FROM abbreviation_review WHERE term_id=? AND source_id='a-bond'",
                      (CB_CREDIT,)).fetchone()[0] == '전환사채'
    assert out['occurrence_before'] == 7 and out['occurrence_after'] == 4 and not out['canonical_approval']
    # The source generation is untouched and the new manifests bind the new index.
    assert sha(generation / 'navigation/navigation.sqlite') == before
    manifest = json.loads((tmp_path / 'new/manifest.json').read_text())
    assert manifest['navigation']['manifest_sha256'] == sha(tmp_path / 'new/navigation/manifest.json')
    nav = json.loads((tmp_path / 'new/navigation/manifest.json').read_text())
    assert nav['index_sha256'] == sha(tmp_path / 'new/navigation/navigation.sqlite')


def test_apply_refuses_pending_jobs_and_invalid_answers_fail(generation, tmp_path):
    abbr.prepare(generation, tmp_path / 'state')
    with pytest.raises(ValueError, match='not run yet'):
        abbr.apply(tmp_path / 'state', tmp_path / 'new')

    class Liar(FakeGenos):
        def call(self, role, task, data, schema):
            value, receipt = super().call(role, task, data, schema)
            value['decisions'][0]['candidate_ids'] = ['invented']
            return value, receipt
    result = abbr.run(tmp_path / 'state', provider=Liar())
    assert result['jobs'] == {'failed': 1} and result['links'].get('PENDING') == 4


def test_public_label_parts():
    assert label_parts('CB(Credit Bureau)') == [('CB', 'SOURCE_LABEL_PART'), ('Credit Bureau', 'SOURCE_ENGLISH')]
    assert label_parts('관리(대상)종목') == [('관리종목', 'SOURCE_LABEL_PART')]
    assert label_parts('접대비→ 기업업무추진비(용어변경)') == [('접대비', 'SOURCE_LABEL_PART'), ('기업업무추진비', 'SOURCE_LABEL_PART')]
    assert label_parts('사모펀드(私募─, Private Equity Fund(PEF))') == [
        ('사모펀드', 'SOURCE_LABEL_PART'), ('Private Equity Fund', 'SOURCE_ENGLISH'), ('PEF', 'SOURCE_LABEL_PART')]
    assert label_parts('수재(受再)') == [('수재', 'SOURCE_LABEL_PART')] and label_parts('0.5인 가구') == []
