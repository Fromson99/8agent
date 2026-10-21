"""Select a parse representation; retain every physical location as source context.

Filename matching establishes a candidate pairing, never content equivalence.
Only equal SHA-256 values establish exact duplicates; RAW is never deleted.
"""
from __future__ import annotations
import copy
from datetime import datetime
import re
import unicodedata
from pathlib import Path

POLICY = 'structured-primary-pdf-reference-v2'
PRIORITY = {'.xml': 0, '.html': 1, '.htm': 1, '.hwpx': 2, '.docx': 3,
            '.pdf': 4, '.hwp': 5, '.doc': 6}
COPY_SUFFIX = re.compile(r'\s*\(([1-9]\d{0,2})\)$')
LATEST_INTERNAL_POLICY = 'user-approved-retained-set-latest-v2'
DATE_SUFFIX = re.compile(r'^(?P<title>.+?)\s*\((?P<date>[0-9]{8})\)$')
SHORT_DATE_SUFFIX = re.compile(r'^(?P<title>.+?)\s*\([0-9]{6}\)$')


def select_latest_internal(rows, exceptions_path=None):
    from semantic_runtime.filename_versions import select as select_versions, load_exceptions, DEFAULT_EXCEPTIONS
    config, config_hash = load_exceptions(exceptions_path or DEFAULT_EXCEPTIONS)
    rows = copy.deepcopy(rows)
    inventory = [{'document_id': r['path'], 'filename': Path(r['path']).name, 'path': r['path'],
                  'filename_source': 'raw_filename', 'source_artifact_sha256': r['sha256']}
                 for r in rows if r['source'] == 'internal']
    selected = {r['path']: r for r in select_versions(inventory, config)}
    output, excluded = [], []
    for row in rows:
        row['input_version_policy'] = 'user-approved-retained-set-latest-v2'
        if row['source'] != 'internal': output.append(row); continue
        decision = selected[row['path']]
        latest = not decision['physical_exclusion_candidate']
        row['is_latest'] = latest
        row['filename_version'] = {'policy': row['input_version_policy'], 'is_latest': latest,
            'family_title': decision['title'], 'date': decision['date'], 'status': decision['status'],
            'basis': decision['reason'], 'exception_ids': decision.get('exception_ids', []),
            'exceptions_sha256': config_hash, 'effective_date_verified': False}
        if latest: output.append(row)
        else: excluded.append({'path': row['path'], 'document_id': row['document_id'], 'sha256': row['sha256'],
            'reason': 'superseded_filename_version', 'policy': row['input_version_policy'],
            'selection': row['filename_version'], 'original_preserved': True})
    return output, excluded


def metadata(row):
    path = Path(row['relative'])
    folders = list(path.parent.parts)
    title = row['name']
    display = folders if folders and folders[-1] == title else [*folders, title]
    return {'document_title': title, 'file_name': path.name, 'folder_names': folders,
            'folder_path': ' > '.join(folders), 'display_name': ' > '.join(display),
            'relative_path': row['relative'], 'source_category': row['source'],
            **({'team': row['team']} if row.get('team') else {}),
            **({'official_abbreviation': row['official_abbreviation']} if row.get('official_abbreviation') else {}),
            **({'original_path': row['original_path']} if row.get('original_path') else {})}


def physical(row):
    return {**metadata(row), 'path': row['path'], 'sha256': row['sha256'],
            'format': Path(row['path']).suffix.lower()}


def unique(values, key):
    return [v for _, v in sorted({key(v): v for v in values}.items())]


def merge_context(target, other):
    target['aliases'] = unique([*target.get('aliases', []), metadata(other),
                               *other.get('aliases', [])], lambda a: a['relative_path'])
    for field in ('representations', 'pdf_references'):
        target[field] = unique([*target.get(field, []), *other.get(field, [])],
                              lambda a: a['path'])


def select(rows):
    rows = copy.deepcopy(rows)
    # Copy suffixes are collapsed only WITH same-format/same-content evidence in
    # the same directory. Revision dates and different-content copies stay distinct.
    families = {}
    for row in rows:
        p = Path(row['path']);stem = unicodedata.normalize('NFC', p.stem)
        base = COPY_SUFFIX.sub('', stem)
        families.setdefault((str(p.parent), base, p.suffix.lower(), row['sha256']), []).append(row)
    stems = {}
    for (_, base, _, _), family in families.items():
        for row in family:
            stems[row['path']] = base if len(family) > 1 else unicodedata.normalize('NFC', Path(row['path']).stem)
    groups = {}
    for row in rows:
        p = Path(row['path'])
        key = (row['source'], row.get('external_source'), row.get('raw_role', 'body'),
               row.get('representation_group') or str(p.parent / stems[row['path']]))
        groups.setdefault(key, []).append(row)
    selected, excluded = [], []
    for alternatives in groups.values():
        rank = min(PRIORITY.get(Path(r['path']).suffix.lower(), 99) for r in alternatives)
        winners = [r for r in alternatives if PRIORITY.get(Path(r['path']).suffix.lower(), 99) == rank]
        # Keep different contents of the winning format independent.
        by_hash = {}
        for row in sorted(winners, key=lambda r: (bool(COPY_SUFFIX.search(Path(r['path']).stem)), len(r['path']), r['path'])):
            authority = (row['sha256'], row.get('doc_type'), row.get('engine'))
            if authority in by_hash:
                merge_context(by_hash[authority], row)
                excluded.append({'path': row['path'], 'reason': 'exact_duplicate_representation',
                                 'selected_paths': [by_hash[authority]['path']], 'policy': POLICY})
            else:
                by_hash[authority] = row
        winners = list(by_hash.values())
        locations = unique([v for r in alternatives for v in [physical(r), *r.get('representations', [])]], lambda a: a['path'])
        for winner in winners:
            winner['representation_policy'] = POLICY
            winner['representations'] = locations
            winner['pdf_references'] = [r for r in locations if r['format'] == '.pdf' and r['path'] != winner['path']]
            winner['pairing_basis'] = 'explicit_group' if winner.get('representation_group') else 'same_directory_and_stem'
            winner['pairing_content_verified'] = False
            winner['aliases'] = unique([*winner.get('aliases', []),
                *[metadata(r) for r in alternatives if r['path'] != winner['path']],
                *[a for r in alternatives for a in r.get('aliases', [])]], lambda a: a['relative_path'])
            selected.append(winner)
        winner_paths = {r['path'] for r in winners}
        for row in alternatives:
            if row['path'] not in winner_paths and not any(e['path'] == row['path'] for e in excluded):
                excluded.append({'source': row.get('external_source', row['source']), 'path': row['path'],
                                 'selected_paths': sorted(winner_paths),
                                 'reason': 'alternate_body_representation', 'policy': POLICY})
    return sorted(selected, key=lambda r: r['path']), excluded


def verify_representations(row):
    from semantic_runtime.contracts import sha
    for rep in row.get('representations', []):
        p = Path(rep['path'])
        if any(q.is_symlink() for q in (p, *p.parents)) or sha(p) != rep['sha256']:
            raise ValueError('paired original/PDF changed: ' + str(p))
