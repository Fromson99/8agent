"""Document roles and the revision-history query scope. Real collector names; no models."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import pytest
from semantic_runtime.contracts import Contracts
from semantic_runtime.document_roles import classify, role_of_metadata, role_of_row, in_scope
from semantic_runtime.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('raw_role,title,path,expected', [
    # collector body slots stay body whatever the file is called
    ('body', '', 'krx/유가증권시장 상장규정/유가증권시장 상장규정 조문.html', 'body'),
    ('body', '', 'kofia/신용평가회사 표준내부통제기준/260115 신용평가회사 표준내부통제기준_개정 전문.hwp', 'body'),
    (None, '', 'internal/인사규정.docx', 'body'),
    # KRX revision slot and comparison slot
    ('attachment', '유가증권시장 상장규정 개정문', 'krx/유가증권시장 상장규정/유가증권시장 상장규정_개정문.hwp', 'amendment'),
    ('comparison_table', '유가증권시장 공시규정 신구조문대비표', 'krx/유가증권시장 공시규정/신구조문대비표/210235940_sin.hwp', 'comparison_table'),
    # KOFIA revision slot: the file behind the "개정문" button varies
    ('attachment', '증권 인수업무 등에 관한 규정 개정문',
     'kofia/증권 인수업무 등에 관한 규정/증권 인수업무 등에 관한 규정 개정 주요내용_260312 (최종).hwp', 'amendment_summary'),
    ('attachment', '매매거래계좌설정약관 개정문', 'kofia/매매거래계좌설정약관/매매거래계좌설정약관 신구조문대비표(시행 20260318).hwp', 'comparison_table'),
    ('attachment', '금융투자회사의 혁신금융업무 등에 대한 면책특례 모범규준 개정문',
     'kofia/금융투자회사의 혁신금융업무 등에 대한 면책특례 모범규준/개정문.hwp', 'amendment'),
    # annex folder: 별표 / 별지 서식 / 참고
    ('attachment', '1. 0000_(별표 1).hwp', 'kofia/증권 인수업무 등에 관한 규정/별표서식/0000_(별표 1).hwp', 'annex'),
    ('attachment', '3. 0002_(별지 제1호 서식).hwp', 'kofia/증권 인수업무 등에 관한 규정/별표서식/0002_(별지 제1호 서식).hwp', 'form'),
    ('attachment', '2. 0001_[참고 2].hwp', 'kofia/표준투자권유준칙/별표서식/0001_[참고 2].hwp', 'reference'),
    # an annex whose own title mentions an amending decree is still an annex
    ('attachment', '', 'law/법인세법 시행령/별표서식/[별표 2의2] 과태료의 부과기준(대통령령 제29529호 법인세법 시행령 일부개정령 부칙 제13조 관련)(법인세법 시행령).hwp', 'annex'),
    ('attachment', '[별지 제43호 서식] 금융상품 관련 평가손실 확인서.hwp', 'krx/코스닥시장 상장규정 시행세칙/[별지 제43호 서식] 금융상품 관련 평가손실 확인서.hwp', 'form'),
])
def test_collector_names_classify(raw_role, title, path, expected):
    assert classify(raw_role, title, path) == expected


def test_old_store_metadata_falls_back_to_file_name():
    # Stores built before document_role was persisted: no collector title.
    old = {'raw_role': 'attachment', 'relative_path': 'kofia/무보증사채 수요예측 모범규준/무보증사채 수요예측 모범규준 개정(200701).hwp'}
    assert role_of_metadata(old) == 'amendment'
    assert role_of_metadata({'raw_role': 'body', 'relative_path': 'krx/a/a 조문.html'}) == 'body'
    assert role_of_metadata({}) == 'body'
    assert role_of_metadata({'document_role': 'form', 'raw_role': 'body'}) == 'form'


def test_inventory_row_uses_collector_title():
    row = {'raw_role': 'attachment', 'name': '표준투자권유준칙',  # corpus path names attachments by label
           'source_title': '표준투자권유준칙 개정문',
           'relative': 'kofia/표준투자권유준칙/표준투자권유준칙(20260409 개정) 개정문신구조문대비표.hwp'}
    assert role_of_row(row) == 'comparison_table'
    # team/scope paths name attachment rows by their collector title
    assert role_of_row({'raw_role': 'attachment', 'name': '코넥스시장 상장규정 개정문',
                        'relative': 'external/financial_team/krx/코넥스시장 상장규정/코넥스시장 상장규정_개정문.hwpx'}) == 'amendment'


def test_scope_membership():
    assert in_scope('body', '기본') and in_scope('form', '기본') and not in_scope('amendment', '기본')
    assert in_scope('amendment_summary', '개정이력') and not in_scope('annex', '개정이력')
    assert in_scope('comparison_table', '전체')
    with pytest.raises(ValueError, match='unknown document scope'):
        in_scope('body', '현행')


def pipeline_with(documents):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE document(document_id TEXT, name TEXT, json TEXT)')
    for did, metadata in documents.items():
        db.execute('INSERT INTO document VALUES (?,?,?)', (did, did, json.dumps({'document_metadata': metadata})))
    p = Pipeline.__new__(Pipeline)
    p.store = SimpleNamespace(db=db, manifest={'generation_id': 'g1'})
    p.contracts = Contracts(ROOT)
    return p


def test_default_query_scope_excludes_revision_history():
    p = pipeline_with({
        'body': {'raw_role': 'body', 'relative_path': 'krx/a/a 조문.html'},
        'annex': {'document_role': 'annex'},
        'amend': {'document_role': 'amendment'},
        'summary': {'raw_role': 'attachment', 'relative_path': 'kofia/b/b 개정 주요내용.hwp'},
    })
    assert p.plan('질문')['scope']['document_version_ids'] == ['annex', 'body']
    assert p.plan('질문', scope='개정이력')['scope']['document_version_ids'] == ['amend', 'summary']
    assert len(p.plan('질문', scope='전체')['scope']['document_version_ids']) == 4
    # explicit IDs are honoured as given, including history documents
    assert p.plan('질문', ['amend'])['scope']['document_version_ids'] == ['amend']
    with pytest.raises(ValueError, match='not both'):
        p.plan('질문', ['amend'], '개정이력')


def test_empty_history_scope_is_reported_not_silently_widened():
    p = pipeline_with({'body': {'raw_role': 'body'}})
    with pytest.raises(ValueError, match='no documents'):
        p.plan('질문', scope='개정이력')


def test_request_contract_accepts_scope_names_only():
    c = Contracts(ROOT)
    c.validate({'question': 'q', 'scope': '개정이력'}, 'urn:8-agent:term-runtime-v1', 'Request')
    with pytest.raises(Exception):
        c.validate({'question': 'q', 'scope': '현행'}, 'urn:8-agent:term-runtime-v1', 'Request')
