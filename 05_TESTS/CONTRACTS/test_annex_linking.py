"""별표·서식 연결 계약 — 첨부 본문 적재와 조문→별표 참조. 합성 입력만 쓴다."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from lawrag.core import ingest
from lawrag.core.structure import rulehtml
from lawrag.platform.paths import manifest_asset_path
from semantic_runtime.term_references import compile_references

HTML = """<html><body><div id="lawcontent">
<div class="JO"><div class="article">제1조(목적) 이 준칙은 [별지 제1호]의 서식에 따른다.</div></div>
<div class="JO"><div class="article">제2조(기준) 적합성은 [참고 4]의 기준에 따라 판단한다.</div></div>
<div class="JO"><div class="article">제3조(미수록) 세부사항은 [별표 9]에 따른다.</div></div>
<div class="JO"><div class="article">별표/서식 파일</div></div>
</div></body></html>"""

SIDECAR = """# title: 1. 0000_(별지 제1호).hwp
# converted: hwp5(ole) -> md(xml)

| 구분 | 기준 |
| --- | --- |
| 안정형 | 원금보장 |
"""


def corpus(tmp_path, titles=('1. 0000_(별지 제1호).hwp', '2. 0001_[참고 4].hwp')):
    root = tmp_path / 'RAW' / 'kofia'
    annex = root / '표준준칙' / '별표서식'
    annex.mkdir(parents=True)
    attachments = []
    for index, title in enumerate(titles):
        name = title.split('. ', 1)[1]
        (annex / name).write_bytes(b'hwp')
        (annex / (name + '.md')).write_text(SIDECAR, encoding='utf-8')
        attachments.append({'title': title, 'role': 'attachment',
                            'file': f'표준준칙/별표서식/{name}',
                            'sha256': hashlib.sha256(b'hwp').hexdigest()})
    body = root / '표준준칙' / '표준준칙 조문.html'
    body.write_text(HTML, encoding='utf-8')
    (root / 'manifest.json').write_text(json.dumps({'source': 'kofia', 'items': [
        {'label': '표준준칙', 'name': '표준준칙', 'kind': 'kofia-rule',
         'body_html_file': '표준준칙/표준준칙 조문.html',
         'body_html_sha256': hashlib.sha256(body.read_bytes()).hexdigest(),
         'attachments': attachments}]}, ensure_ascii=False), encoding='utf-8')
    return body


def test_manifest_paths_resolve_for_both_layouts(tmp_path):
    manifest = tmp_path / 'RAW/kofia/manifest.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{}')
    assert manifest_asset_path(manifest, '표준준칙/별표서식/x.hwp') == manifest.parent / '표준준칙/별표서식/x.hwp'
    assert manifest_asset_path(manifest, 'data/corpus/law/x.hwp').name == 'x.hwp'
    with pytest.raises(ValueError):
        manifest_asset_path(manifest, '../escape.hwp')


@pytest.mark.parametrize('title,expected', [
    ('[별표 14의1] 외환파생상품거래 위험관리기준', '별표 14의1'),
    ('1. 0000_(별지 제1호).hwp', '별지 제1호'),
    ('2. 0001_[참고 4-1].hwp', '참고 4-1'),
    ('설명 없는 이름', '설명 없는 이름'),
])
def test_annex_label_reads_the_name_the_article_uses(title, expected):
    assert ingest.annex_label(title, title) == expected


def test_rule_html_carries_attachment_bodies_without_rewriting_the_original(tmp_path):
    body = corpus(tmp_path)
    raw = body.read_bytes()
    item, manifest = ingest.manifest_item_for(body, raw)
    assert item is not None and manifest == tmp_path / 'RAW/kofia/manifest.json'
    result = ingest.ingest_rulehtml_bytes(raw, '표준준칙', tmp_path / 'structure', 'kofia',
                                          extra_meta={'kind': 'kofia-rule'}, site='kofia',
                                          manifest_item=item, manifest=manifest)
    assert result['annex_md'] == 2 and result['annex_have'] == 2
    data = json.loads((tmp_path / 'structure' / result['doc_id'] / 'result.json').read_text())
    surfaces = [n.get('surface') for n in data['nodes']]
    assert '별지 제1호' in surfaces and '참고 4' in surfaces
    texts = [b['text'] for b in data['blocks']]
    assert '| 안정형 | 원금보장 |' in texts          # 표가 표로 남는다
    assert any('별표/서식 파일' in t for t in texts)  # 원문 목록은 지우지 않는다
    assert not any(t.startswith('# converted:') for t in texts)


def test_revision_text_is_not_spliced_into_the_body_as_an_annex(tmp_path):
    body = corpus(tmp_path)
    manifest = tmp_path / 'RAW/kofia/manifest.json'
    value = json.loads(manifest.read_text())
    revision = tmp_path / 'RAW/kofia/표준준칙/20200916 개정문.hwp'
    revision.write_bytes(b'hwp')
    (revision.parent / (revision.name + '.md')).write_text(SIDECAR, encoding='utf-8')
    value['items'][0]['attachments'] += [
        {'title': '표준준칙 개정문', 'role': 'attachment', 'file': '표준준칙/20200916 개정문.hwp'},
        {'title': '신구조문대비표', 'role': 'comparison_table',
         'file': '표준준칙/별표서식/대비표.hwp'}]
    manifest.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    item, path = ingest.manifest_item_for(body, body.read_bytes())
    labels = [s['label'] for s in ingest.annex_sections(item, path)]
    assert labels == ['별지 제1호', '참고 4']
    assert len(ingest.annex_attachments(item)) == 2


def test_missing_sidecar_is_a_visible_count_not_a_silent_drop(tmp_path):
    body = corpus(tmp_path)
    manifest = tmp_path / 'RAW/kofia/manifest.json'
    value = json.loads(manifest.read_text())
    value['items'][0]['attachments'].append(
        {'title': '3. 0002_[참고 9].hwp', 'role': 'attachment',
         'file': '표준준칙/별표서식/없는파일.hwp', 'sha256': ''})   # 별표서식 폴더 = 별표
    manifest.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    item, path = ingest.manifest_item_for(body, body.read_bytes())
    result = ingest.ingest_rulehtml_bytes(body.read_bytes(), '표준준칙', tmp_path / 'structure',
                                          'kofia', extra_meta={'kind': 'kofia-rule'}, site='kofia',
                                          manifest_item=item, manifest=path)
    assert (result['annex_md'], result['annex_have']) == (2, 3)


def source_rows(db, rows):
    for ident, document, name, heading, blocks in rows:
        value = {'id': ident, 'document_id': document, 'document_name': name, 'heading': heading,
                 'blocks': [{'block_id': str(n), 'text': t} for n, t in enumerate(blocks)]}
        db.execute('INSERT INTO source VALUES (?,?,?,?)',
                   (ident, document, heading, json.dumps(value, ensure_ascii=False)))


def test_article_reaches_the_annex_it_cites(tmp_path):
    db = sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
      CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
      CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));''')
    source_rows(db, [
        ('a1', 'd1', '표준준칙', '제2조(기준)', ['제2조(기준) 적합성은 [참고 4]의 기준에 따라 판단한다.']),
        ('a2', 'd1', '표준준칙', '제4조(서식)', ['제4조(서식) 신고는 별지 제1호 서식으로 한다.']),
        ('a3', 'd1', '표준준칙', '제3조(미수록)', ['제3조(미수록) 세부사항은 별표 9에 따른다.']),
        ('x1', 'd1', '표준준칙', '참고 4 적합성 판단 기준', ['| 구분 | 기준 |']),
        ('x2', 'd1', '표준준칙', '별지 제1호 신고서', ['| 항목 | 값 |']),
        ('b1', 'd2', '시행세칙', '제2-4조(위험액)', ['제2-4조(위험액) 「표준준칙」 참고 4에 따른다.']),
    ])
    total, unresolved = compile_references(db)
    found = {}
    for (payload,) in db.execute('SELECT json FROM reference'):
        value = json.loads(payload)
        if value['origins'] == ['raw_explicit_annex_hint']:
            found[value['source_id']] = value
    assert found['a1']['target_source_ids'] == ['x1']
    assert found['a1']['resolution'] == 'EXACT_SAME_DOCUMENT_ANNEX'
    assert found['a2']['target_source_ids'] == ['x2']       # 별지 제1호 == 별지1
    assert found['b1']['target_source_ids'] == ['x1']       # 문서명을 밝힌 타 문서 별표
    assert found['b1']['resolution'] == 'EXACT_NAMED_DOCUMENT_ANNEX'
    assert found['a3']['target_source_ids'] == []           # 본문 없는 별표는 숨기지 않는다
    assert found['a3']['reason'] == 'ANNEX_BODY_NOT_IN_SELECTION'
    assert db.execute('SELECT count(*) FROM reference_end WHERE source_id=?', ('x1',)).fetchone()[0] == 2


def test_folder_prefixed_names_still_resolve_named_citations(tmp_path):
    db = sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
      CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
      CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));''')
    source_rows(db, [
        ('a1', 'd1', 'RAW > law > 자본시장법 시행령', '제1조(목적)', ['제1조(목적) 「상법」 제5조와 「상법」 별표 1에 따른다.']),
        ('b1', 'd2', 'RAW > law > 상법', '제5조(정의)', ['제5조(정의) 정의한다.']),
        ('b2', 'd2', 'RAW > law > 상법', '별표 1 기준', ['| 구분 |']),
    ])
    compile_references(db)
    hits = {tuple(json.loads(p)['target_source_ids']) for (p,) in db.execute('SELECT json FROM reference')}
    assert ('b1',) in hits and ('b2',) in hits
