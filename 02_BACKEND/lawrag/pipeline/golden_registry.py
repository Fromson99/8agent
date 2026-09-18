"""One registry for every golden collection. Derived from the source sheets, never hand-edited.

Collections keep their own authoring source (CM 동결 JSON, 내규 작성 CSV). The registry
re-reads them, records how far each case is from being freezable, and hands only complete
cases to the existing import → review → freeze path. Incomplete cases stay listed, never dropped.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from semantic_runtime.contracts import sha
from .golden import TAGS, read, seal, verify
from .golden_authoring import csv_rows, csv_target, input_cases

VERSION = 'term-golden-registry-v1'
# 사진 전사가 질문 자체를 확정하지 못한 상태. 'transcribed' 는 원본 대조 전이라 경고만 남긴다.
INCOMPLETE_TRANSCRIPTION = ('partial', 'uncertain', 'source_placeholder')


def _cm_entries(path):
    source = read(path)
    cases, lineage = input_cases(path, 'cm')
    raw = {c['id']: c for c in source['cases']}
    entries = []
    for case in cases:
        original = raw[case['id']]
        entries.append({
            'id': case['id'], 'collection': 'cm', 'question': case['question'],
            'reference_answer': case['reference_answer'], 'as_of': case['as_of'], 'targets': case['targets'],
            'facets': {**original.get('axes', {}), 'topic': original.get('topic')},
            'provenance': {'input_sha256': lineage['input_sha256'], 'schema_version': source.get('schema_version'),
                           'source_question_no': original.get('source_question_no'),
                           'source_question': original.get('source_question')},
            'blockers': [], 'warnings': []})
    return entries, lineage


def _internal_entries(path):
    path = Path(path)
    lineage = {'input_path': str(path.resolve()), 'input_sha256': sha(path), 'format': 'internal-csv'}
    grouped = {}
    for row in csv_rows(path):
        cid = row['문항ID'].strip()
        if not cid or not row['질문'].strip():
            raise ValueError('internal sheet row without case ID or question')
        values = (row['질문'], row['기준답변'].strip(), row['기준일'].strip())
        entry = grouped.get(cid)
        if entry is None:
            entry = grouped[cid] = {
                'id': cid, 'collection': 'internal', 'question': values[0],
                'reference_answer': values[1] or None, 'as_of': values[2] or None, 'targets': [],
                'facets': {'team': row.get('팀', '')},
                'provenance': {'input_sha256': lineage['input_sha256'], 'source_row': row.get('원본행'),
                               'photos': row.get('원본사진'), 'transcription': row.get('전사상태'),
                               'note': row.get('확인사항')},
                'blockers': [], 'warnings': [], '_values': values}
        elif entry['_values'] != values:
            raise ValueError(f'{cid}: same case ID has conflicting question/answer/date')
        if row['문서명'].strip() or row['조문'].strip():
            entry['targets'].append(csv_target(row, len(entry['targets']) + 1))
        status = row.get('전사상태', '')
        if status in INCOMPLETE_TRANSCRIPTION and 'transcription_incomplete' not in entry['blockers']:
            entry['blockers'].append('transcription_incomplete')
        elif status == 'transcribed' and 'transcription_unverified' not in entry['warnings']:
            entry['warnings'].append('transcription_unverified')
        if row.get('중복원본ID', '').strip():
            entry['warnings'].append('duplicate_of:' + row['중복원본ID'].strip())
    for entry in grouped.values():
        entry.pop('_values')
    return list(grouped.values()), lineage


def _complete(entry):
    blockers = entry['blockers']
    if not entry['reference_answer']:
        blockers.append('reference_answer_missing')
    if not entry['as_of']:
        blockers.append('as_of_missing')
    else:
        try:
            datetime.strptime(entry['as_of'], '%Y-%m-%d')
        except ValueError:
            blockers.append('as_of_invalid')
    if not any(t['role'] == 'required' for t in entry['targets']):
        blockers.append('evidence_missing')
    entry['stage'] = ('ready' if not blockers else
                      'question_only' if 'reference_answer_missing' in blockers else 'incomplete')
    # 여러 문서에 걸친 필수 근거는 reconciliation 후보 신호일 뿐, 태그는 사람이 붙인다.
    required = {t.get('doc_id') or t.get('law') for t in entry['targets'] if t['role'] == 'required'}
    entry['signals'] = {'required_documents': len(required)}


def build(cm=None, internal=None, annotations=None):
    entries, sources = [], {}
    if cm:
        found, sources['cm'] = _cm_entries(cm); entries += found
    if internal:
        found, sources['internal'] = _internal_entries(internal); entries += found
    if not entries:
        raise ValueError('at least one collection source required')
    ids = [e['id'] for e in entries]
    if len(set(ids)) != len(ids):
        raise ValueError('case IDs collide across collections')
    notes = read(annotations) if annotations else {}
    if annotations:
        sources['annotations'] = {'input_path': str(Path(annotations).resolve()), 'input_sha256': sha(annotations)}
    unknown = set(notes) - set(ids)
    if unknown:
        raise ValueError('annotation for unknown case: ' + ','.join(sorted(unknown)))
    for entry in entries:
        tags = notes.get(entry['id'], {}).get('tags', [])
        if not isinstance(tags, list) or set(tags) - set(TAGS):
            raise ValueError(f"{entry['id']}: unknown tag")
        entry['tags'] = sorted(set(tags))
        _complete(entry)
    return seal({'schema_version': VERSION, 'sources': sources, 'summary': summarize(entries), 'cases': entries})


def summarize(entries):
    by = {}
    for entry in entries:
        slot = by.setdefault(entry['collection'], {'total': 0, 'stages': Counter(), 'blockers': Counter(), 'tags': Counter()})
        slot['total'] += 1
        slot['stages'][entry['stage']] += 1
        slot['blockers'].update(entry['blockers'])
        slot['tags'].update(entry['tags'])
    return {'total': len(entries), 'ready': sum(e['stage'] == 'ready' for e in entries),
            'collections': {k: {**v, **{f: dict(v[f]) for f in ('stages', 'blockers', 'tags')}} for k, v in by.items()}}


def ready_cases(registry):
    """Import input for golden_authoring: complete cases only, the rest reported with reasons."""
    registry = verify(registry)
    if registry.get('schema_version') != VERSION:
        raise ValueError('unsupported golden registry')
    cases, deferred = [], []
    for entry in registry['cases']:
        if entry['stage'] != 'ready':
            deferred.append({'id': entry['id'], 'collection': entry['collection'],
                             'stage': entry['stage'], 'blockers': entry['blockers']})
            continue
        cases.append({'id': entry['id'], 'question': entry['question'], 'reference_answer': entry['reference_answer'],
                      'as_of': entry['as_of'], 'targets': entry['targets'],
                      'collection': entry['collection'], 'tags': entry['tags'],
                      'registry_notes': {'facets': entry['facets'], 'provenance': entry['provenance'],
                                         'warnings': entry['warnings'], 'signals': entry['signals']}})
    return cases, deferred
