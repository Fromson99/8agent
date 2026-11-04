"""Document role and role-based query scopes. Deterministic; no model, no body text.

Authority order: the collector's role (manifest `role`), the collector's slot title
("<규정명> 개정문" is the revision slot of KRX/KOFIA), the annex folder, then the
file name. File-name patterns only refine a slot the collector already opened, or
stand in for stores written before `document_role` was persisted.

Revision history (개정문 · 개정 주요내용 · 신구조문대비표) describes a change, not the
rule in force, so the default query scope leaves it out; `개정이력` opens it.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

ROLES = ('body', 'annex', 'form', 'reference', 'amendment', 'amendment_summary',
         'comparison_table', 'attachment')
HISTORY_ROLES = frozenset({'amendment', 'amendment_summary', 'comparison_table'})
DEFAULT_SCOPE = '기본'
SCOPES = {
    '기본': '개정이력(개정문·개정 주요내용·신구조문대비표)을 뺀 전체',
    '개정이력': '개정문·개정 주요내용·신구조문대비표만',
    '전체': '모든 문서',
}

ANNEX_FOLDERS = frozenset({'별표서식', '별표', '별지', '서식', '별지서식', '별표·서식'})
_LABEL = re.compile(r'[\[(（［]\s*(별표|별지|서식|별첨|참고|부록|첨부)')
_SUMMARY = re.compile(r'주요\s*(개정\s*)?내용|개정\s*내용|변경\s*내용|요약')
_COMPARISON = re.compile(r'신\s*[_·ㆍ.\-]?\s*구\s*조문|신구\s*대비')
_HISTORY_SLOT = re.compile(r'\s(개정문)$')
_HISTORY_NAME = re.compile(r'개정문|제정문|개정안|제정안|(개정|제정)\s*[(（]\s*(안\s*[)）]|\d{6})')


def _nfc(value):
    return unicodedata.normalize('NFC', value or '')


def _annex_kind(name):
    match = _LABEL.search(name)
    word = match.group(1) if match else ''
    if word in ('별지', '서식'):
        return 'form'
    if word in ('별첨', '참고', '부록', '첨부'):
        return 'reference'
    return 'annex'


def _history_kind(name):
    if _SUMMARY.search(name):
        return 'amendment_summary'
    if _COMPARISON.search(name):
        return 'comparison_table'
    return 'amendment'


def classify(raw_role=None, title='', relative_path=''):
    """(collector role, collector title, RAW-relative path) -> one of ROLES."""
    raw_role = raw_role or 'body'
    if raw_role == 'body':
        return 'body'
    if raw_role == 'comparison_table':
        return 'comparison_table'
    path = PurePosixPath(_nfc(relative_path))
    name, title = path.name, _nfc(title).strip()
    if any(part in ANNEX_FOLDERS for part in path.parts[:-1]):
        return _annex_kind(name)
    if _HISTORY_SLOT.search(title):
        return _history_kind(name)
    if _LABEL.search(name) or _LABEL.search(title):
        return _annex_kind(name if _LABEL.search(name) else title)
    if not title and (_HISTORY_NAME.search(name) or _SUMMARY.search(name) or _COMPARISON.search(name)):
        return _history_kind(name)
    return 'attachment'


def role_of_row(row):
    """Build inventory row -> role. Attachment rows carry the collector title as name."""
    raw_role = row.get('raw_role') or 'body'
    title = row.get('source_title') or (row.get('name', '') if raw_role != 'body' else '')
    return classify(raw_role, title, row.get('relative') or row.get('path') or '')


def role_of_metadata(metadata):
    """Stored document_metadata -> role; older stores lack the persisted field."""
    metadata = metadata or {}
    if metadata.get('document_role') in ROLES:
        return metadata['document_role']
    # Title is unknown here (document_title is the regulation label for old rows);
    # classify() then falls back to the file-name patterns.
    return classify(metadata.get('raw_role'), '', metadata.get('relative_path') or metadata.get('file_name') or '')


def in_scope(role, scope):
    if scope not in SCOPES:
        raise ValueError('unknown document scope: ' + str(scope) + ' (choose ' + ' / '.join(SCOPES) + ')')
    if scope == '전체':
        return True
    return (role in HISTORY_ROLES) == (scope == '개정이력')
