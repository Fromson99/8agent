"""Deterministic, own-block-only ontology cards; no reading or authority grants.

The caller owns original-span, version, authorization and receipt verification.
This module rejects changed bundle anchors/text and never creates evidence IDs.
Both renderers consume one semantic payload; neither can add legal content.
"""
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker

from ..contracts import digest
from .errors import ContractError

VERSION = 'ontology-compiled-v0'
MAX_PROVISIONS = 128
MAX_CONNECTIONS = 512
MAX_SOURCE_CHARS = 160000
MAX_JSON_CHARS = 2000000
MAX_JSON_NODES = 20000
ROLE_LABELS = {'DEFINITION': '정의', 'SCOPE': '범위', 'REQUIREMENT': '조건·요건',
               'THRESHOLD': '수치 기준', 'EXCEPTION': '예외', 'PROCEDURE': '절차',
               'EFFECT': '효과'}
TIMESTAMP = re.compile(r'[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])'
    r'[Tt](?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?'
    r'(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])')


def _bounded_json(value):
    """Check size/types before schema recursion, serialization or copying."""
    pending = [(value, 0)]; nodes = chars = 0
    while pending:
        item, depth = pending.pop(); nodes += 1
        if nodes > MAX_JSON_NODES or depth > 24:
            raise ContractError('ontology JSON structural limit')
        if isinstance(item, str):
            chars += len(item)
        elif type(item) is dict:
            if len(item) > 256 or any(type(k) is not str for k in item):
                raise ContractError('ontology JSON object shape')
            chars += sum(len(k) for k in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            if len(item) > 8192:
                raise ContractError('ontology JSON array limit')
            pending.extend((child, depth + 1) for child in item)
        elif item is None or type(item) in (bool, int):
            if type(item) is int and item.bit_length() > 256:
                raise ContractError('ontology JSON integer limit')
        elif type(item) is float and math.isfinite(item):
            pass
        else:
            raise ContractError('ontology requires finite JSON values')
        if chars > MAX_JSON_CHARS:
            raise ContractError('ontology JSON character limit')


@lru_cache(maxsize=1)
def _validator():
    path = Path(__file__).resolve().parents[3] / '00_SYSTEM/SCHEMAS/ontology-bundle-v0.schema.json'
    if path.stat().st_size > 128000:
        raise ContractError('ontology schema size limit')
    schema = json.loads(path.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def content_hash(text):
    """Hash exact UTF-8 text: no whitespace or Unicode normalization."""
    if type(text) is not str:
        raise ContractError('ontology original must be text')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def anchor_key(anchor):
    """Stable identity independent of display label or source body hash."""
    if type(anchor) is not dict or any(type(anchor.get(k)) is not str or not anchor[k].strip()
                                     for k in ('document_id', 'version', 'unit_id')):
        raise ContractError('ontology anchor identity missing')
    return digest({k: anchor[k] for k in ('document_id', 'version', 'unit_id')})


def _timestamp(value):
    """Require a real ISO calendar instant with explicit UTC/offset timezone.

    jsonschema's date-time checker depends on optional packages, so this gate
    must work even when that format is unavailable in the installed extras.
    """
    if type(value) is not str or not TIMESTAMP.fullmatch(value):
        raise ContractError('ontology proposed_by.at requires ISO date-time with timezone')
    try:
        parsed = datetime.fromisoformat(value.upper().replace('Z', '+00:00'))
    except ValueError as error:
        raise ContractError('ontology proposed_by.at invalid calendar date-time') from error
    if parsed.utcoffset() is None:
        raise ContractError('ontology proposed_by.at timezone missing')


def validate_bundle(bundle):
    """Validate a candidate's shape and closed references, without approving it.

    Manual seeds may have no judgment IDs. When IDs exist, their presence in a
    real judgment ledger is the proposing workflow's responsibility.
    """
    _bounded_json(bundle)
    error = next(_validator().iter_errors(bundle), None)
    if error:
        path = '.'.join(map(str, error.absolute_path)) or '$'
        raise ContractError('ontology bundle schema at ' + path + ': ' + error.message)
    _timestamp(bundle['proposed_by']['at'])
    identities = set(); labels = set()
    for provision in bundle['provisions']:
        anchor = provision['anchor']; key = anchor_key(anchor)
        if key in identities:
            raise ContractError('duplicate ontology anchor')
        if anchor['label'] in labels:
            raise ContractError('ambiguous ontology anchor label')
        identities.add(key); labels.add(anchor['label'])
    relations = set()
    for relation in bundle['relations']:
        if relation['from'] not in labels or relation['to'] not in labels:
            raise ContractError('ontology relation endpoint not in bundle')
        key = digest(relation)
        if key in relations:
            raise ContractError('duplicate ontology relation')
        relations.add(key)
    judgments = [(row['session_id'], row['judgment_id']) for row in bundle['evidence_judgments']]
    if len(judgments) != len(set(judgments)):
        raise ContractError('duplicate ontology evidence judgment')
    return bundle


def _rows(value, maximum, name):
    if not isinstance(value, (list, tuple)) or len(value) > maximum:
        raise ContractError('ontology ' + name + ' list limit or shape')
    rows = list(value)
    _bounded_json(rows)
    if any(type(row) is not dict for row in rows):
        raise ContractError('ontology ' + name + ' requires object rows')
    return rows


def _sections(payload, mode):
    provisions = payload['provisions']
    if mode == 'A1':
        return [{'label': '원문 조각 — 승인 묶음의 등록 순서',
                 'provision_indices': list(range(len(provisions)))}]
    base = set(); delegated = set()
    for relation in payload['relations']:
        if relation['type'] == 'DELEGATES_TO':
            base.add(relation['from']); delegated.add(relation['to'])
        elif relation['type'] == 'SPECIFIES_DELEGATED_CASES_OF':
            base.add(relation['to']); delegated.add(relation['from'])
    sections = {}
    for index, row in enumerate(provisions):
        role = row['role']; label = row['anchor']['label']
        if label in base:
            rank, title = 0, '법이 정한 것 — 승인된 위임 출발 조항'
        elif role == 'EXCEPTION':
            rank, title = 3, '예외'
        elif role == 'REQUIREMENT':
            rank, title = 2, '조건·요건'
        elif label in delegated:
            rank, title = 1, '위임받은 내용 — 승인된 연결 대상'
        else:
            rank, title = 4, '그 밖의 승인 조각 — 역할 표시'
        section = sections.setdefault(rank, {'label': title, 'provision_indices': []})
        section['provision_indices'].append(index)
    return [sections[rank] for rank in sorted(sections)]


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _render(payload, sections, mode):
    """Both forms print the same approved metadata, verified text and gaps."""
    title = '컴파일 묶음' if mode == 'A2' else '연결 목록과 원문 조각'
    lines = [f'[{title}] {payload["concept"]["label"]}',
             '목적: 이 개념 묶음의 원문·연결 범위를 확인한다. 적용 결론은 별도 판단한다.',
             '개념 정보: ' + _encoded(payload['concept']),
             '확보 상태: ' + payload['status'] + ' (원문 확보 여부이며 답변 충분성 판정 아님)',
             '범위: 각 anchor의 자체 본문만. 하위 조항·상위 본문은 별도 provision이다.',
             '승인 연결(읽기 예정·확보 상태는 각 조각에 표시):']
    lines.extend(' - ' + _encoded(row) for row in payload['relations'])
    if not payload['relations']:
        lines.append(' - 등록된 연결 없음')
    for section in sections:
        lines.append('\n' + section['label'])
        for index in section['provision_indices']:
            row = payload['provisions'][index]
            lines.append(f'{index + 1}) {row["anchor"]["label"]} / {ROLE_LABELS[row["role"]]}')
            lines.append('원문 위치: ' + _encoded(row['anchor']))
            if row['acquisition_status'] == 'UNACQUIRED':
                lines.append('원문 미확보 — 본문·값·내용 메모를 표시하지 않음')
                continue
            lines.append(row['text'])
            lines.append('근거: ' + _encoded(row['evidence_refs']))
            lines.append('승인 값: ' + _encoded(row['value']))
            lines.append('승인 메모: ' + row['note'])
    lines.append('\n검토 메모 상태: ' + payload['review_notes_status'])
    lines.extend(' - ' + note for note in payload['review_notes'])
    lines.append('\n미확인·미확보:')
    lines.extend(' - ' + _encoded(row) for row in payload['unresolved'])
    if not payload['unresolved']:
        lines.append(' - 이 묶음의 원문 확보에서 기록된 미확인 없음')
    lines.append('\n이 묶음 밖에 남은 연결(적용·필요성은 직접 판단):')
    lines.extend(' - ' + _encoded(row) for row in payload['remaining_connections'])
    if not payload['remaining_connections']:
        lines.append(' - 전달된 목록 없음. 연결 부재를 증명하지 않음')
    return '\n'.join(lines)


def compile_bundle(bundle, fragments, *, unresolved=(), remaining_connections=(), mode='A2'):
    """Compile verified own-block fragments without I/O, calls or scope grants.

    Missing fragments produce PARTIAL. A supplied changed/unknown fragment is
    an integrity error, never silently omitted or relabelled as missing.
    """
    if mode not in ('A1', 'A2'):
        raise ContractError('ontology compiler mode must be A1 or A2')
    validate_bundle(bundle)
    if bundle['status'] != 'APPROVED':
        raise ContractError('ontology compilation requires APPROVED experiment bundle')
    supplied = _rows(fragments, MAX_PROVISIONS, 'fragments')
    pending = deepcopy(_rows(unresolved, MAX_CONNECTIONS, 'unresolved'))
    remaining = deepcopy(_rows(remaining_connections, MAX_CONNECTIONS, 'remaining connections'))
    expected = {anchor_key(p['anchor']): p for p in bundle['provisions']}
    by_key = {}; source_chars = 0
    for fragment in supplied:
        if set(fragment) != {'anchor', 'text', 'evidence_refs'}:
            raise ContractError('ontology fragment fields must be anchor/text/evidence_refs')
        key = anchor_key(fragment['anchor'])
        if key not in expected:
            raise ContractError('unknown ontology fragment anchor')
        if key in by_key:
            raise ContractError('duplicate ontology fragment anchor')
        if fragment['anchor'] != expected[key]['anchor']:
            raise ContractError('ontology fragment anchor changed')
        text = fragment['text']
        if type(text) is not str:
            raise ContractError('ontology original must be text')
        source_chars += len(text)
        if source_chars > MAX_SOURCE_CHARS:
            raise ContractError('ontology source character limit')
        if content_hash(text) != fragment['anchor']['content_sha256']:
            raise ContractError('ontology original hash mismatch')
        refs = fragment['evidence_refs']
        if (type(refs) is not list or not refs or len(refs) > 512
                or any(type(ref) is not str or not ref.strip() or len(ref) > 512 for ref in refs)
                or len(refs) != len(set(refs))):
            raise ContractError('ontology fragment requires distinct existing evidence references')
        by_key[key] = fragment
    provisions = []
    for provision in bundle['provisions']:
        anchor = provision['anchor']; fragment = by_key.get(anchor_key(anchor))
        row = {'anchor': deepcopy(anchor), 'role': provision['role'],
               'acquisition_status': 'ACQUIRED' if fragment else 'UNACQUIRED'}
        if fragment:
            row.update(text=fragment['text'], evidence_refs=list(fragment['evidence_refs']),
                       value=deepcopy(provision['value']), note=provision['note'])
        else:
            pending.append({'anchor': deepcopy(anchor), 'reason': 'SOURCE_NOT_ACQUIRED'})
        provisions.append(row)
    complete = len(by_key) == len(expected)
    payload = {'bundle_id': bundle['bundle_id'], 'revision': bundle['revision'],
               'bundle_sha256': digest(bundle), 'concept': deepcopy(bundle['concept']),
               'status': 'COMPLETE' if complete else 'PARTIAL', 'extent_contract': 'OWN_BLOCKS_ONLY',
               'provisions': provisions, 'relations': deepcopy(bundle['relations']),
               'review_notes': deepcopy(bundle['review_notes']) if complete else [],
               'review_notes_status': 'AVAILABLE' if complete else 'WITHHELD_UNTIL_ALL_ORIGINALS_ACQUIRED',
               'unresolved': pending, 'remaining_connections': remaining}
    _bounded_json(payload)
    sections = _sections(payload, mode)
    return {'contract': VERSION, 'mode': mode, 'status': payload['status'], 'payload': payload,
            'payload_sha256': digest(payload), 'presentation': {'kind': mode, 'sections': sections,
            'text': _render(payload, sections, mode)}}
