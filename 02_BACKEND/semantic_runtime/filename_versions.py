"""Common filename selection for RAW admission and immutable generation visibility."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timezone
import csv
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
import uuid

POLICY = 'internal-filename-audit-v2'
DATE = re.compile(r'(?<![0-9])(?:(?P<long>(?:19|20)[0-9]{6})|(?P<short>[0-9]{6})|'
    r'(?P<y>(?:19|20)[0-9]{2}|[0-9]{2})\s*(?:[._/\-]\s*|년\s*)'
    r'(?P<m>[0-9]{1,2})\s*(?:[._/\-]\s*|월\s*)(?P<d>[0-9]{1,2})(?:\s*일)?)(?![0-9])')
EXT = re.compile(r'\.(?:docx?|hwpx?|gul|pdf|xml|html?|xlsx?|pptx?|txt|md)(?=$|[._\s()\[\]-])', re.I)
TITLE = re.compile(r'^[^_()\[\]{}]*(?:시행세칙|시행규칙|운영준칙|운영지침|시행기준|준칙|규정|지침|기준|세칙|요령|정관|규약|정책|매뉴얼|계획|가이드)(?=$|[\s_.,()\[\]{}-])')
DECOR = re.compile(r'^(?:clean|최종본?|수정본?|개정본?|전산반영|조직개편|직위수정|본문|원본|사본|별첨\s*[0-9]*|별지\s*[0-9]*|붙임\s*[0-9]*|첨부\s*[0-9]*)$', re.I)
LABEL = {'LATEST': '최신 유지', 'OLDER': '구버전 제외 후보', 'REVIEW': '검토 보존', 'TEMP': '임시파일 제외 후보'}
LABEL.update(KEEP='예외로 모두 유지', EXCLUDED='지정 판본 외 제외 후보')
ATTACHMENT = re.compile(r'(?:\[|\()?\s*별첨\s*([0-9]+)\s*(?:\]|\))?')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def state(path):
    p = Path(path)
    s = p.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def parse_filename(filename):
    """No fuzzy title matching, filesystem dates, LLM calls or content reads."""
    name = unicodedata.normalize('NFKC', filename)
    matches = list(DATE.finditer(name))
    dates, invalid, tokens = [], [], []
    for match in matches:
        token = match.group()
        tokens.append(token)
        compact = match['long'] or match['short']
        if compact:
            year, month, day = int(compact[:-4]), int(compact[-4:-2]), int(compact[-2:])
            short = len(compact) == 6
        else:
            year, month, day = int(match['y']), int(match['m']), int(match['d'])
            short = len(match['y']) == 2
        if short:
            year += 2000 if year <= 69 else 1900
        try:
            dates.append(date(year, month, day).isoformat())
        except ValueError:
            invalid.append(token)
    # A dated bracket is version metadata, including text such as 고난도금융투자상품.
    text = re.sub(r'\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}',
                  lambda m: ' ' if DATE.search(m.group()) else m.group(), name)
    text = EXT.sub(' ', DATE.sub(' ', text))
    text = re.sub(r'[\[(]\s*(?:별첨|별지|붙임|첨부)\s*[0-9]*\s*[\])]', ' ', text)
    text = re.sub(r'[\[(]\s*[0-9]{1,3}\s*[\])]', ' ', text)
    text = text.strip(' _-.,()[]{}')
    # Known standalone labels may occur before or after the title.
    chunks = [x.strip(' .-()[]{}') for x in re.split(r'_+', text)]
    text = '_'.join(x for x in chunks if x and not DECOR.fullmatch(x)).strip(' _-.,')
    text = re.sub(r'^\d{1,3}[. _-]+', '', text)
    text = re.split(r'\s+(?:별첨|별지|붙임|첨부)\s*[0-9]', text, maxsplit=1)[0]
    match = TITLE.match(text)
    title_rule = 'document_suffix' if match else 'single_name'
    if match:
        title = match.group().strip()
    else:
        title = text.strip()
    title = re.sub(r'\s+', ' ', title).strip(' _-.,()[]{}')
    key = re.sub(r'[\s_\-]+', '', title).casefold()
    reasons = []
    if not dates: reasons.append('invalid_date' if invalid else 'missing_date')
    elif invalid: reasons.append('invalid_date')
    if len(set(dates)) > 1: reasons.append('multiple_dates')
    if not key or not re.search(r'[가-힣A-Za-z]', key): reasons.append('missing_title')
    if not match and ('_' in title or re.search(r'별첨|별지|붙임|첨부', title)):
        reasons.append('ambiguous_title')
    return {'title': title, 'title_key': key,
            'date': dates[0] if len(set(dates)) == 1 and not invalid else '',
            'date_candidates': sorted(set(dates)), 'date_tokens': tokens,
            'invalid_date_tokens': invalid, 'title_rule': title_rule,
            'parse_issues': reasons, 'temporary': name.startswith(('~$', '.~', '~WRL'))}


def name_key(value):
    return re.sub(r'[\s_\-]+', '', unicodedata.normalize('NFKC', value)).casefold()


def filename_key(value):
    return re.sub(r'\s+', '', EXT.sub('', unicodedata.normalize('NFKC', value))).casefold()


def validate_exceptions(value):
    if not isinstance(value, dict) or value.get('schema_version') != 'filename-audit-exceptions-v1':
        raise ValueError('invalid exceptions schema')
    if set(value) - {'schema_version', 'revision', 'description', 'single_file_folder_is_latest', 'rules'}:
        raise ValueError('unknown exceptions configuration field')
    if not isinstance(value.get('revision'), str) or not value['revision']:
        raise ValueError('exceptions revision required')
    if type(value.get('single_file_folder_is_latest')) is not bool or not isinstance(value.get('rules'), list):
        raise ValueError('invalid exceptions rules/options')
    ids, titles = set(), set()
    for rule in value['rules']:
        if not isinstance(rule, dict) or set(rule) - {'id', 'titles', 'action', 'reason', 'date', 'filename_stem', 'match_parent_folder', 'expected_locations', 'title_spacing'}:
            raise ValueError('invalid exception rule fields')
        if not isinstance(rule.get('id'), str) or not rule['id'] or rule['id'] in ids:
            raise ValueError('duplicate/missing exception ID')
        ids.add(rule['id'])
        if not isinstance(rule.get('reason'), str) or not rule['reason']:
            raise ValueError('exception reason required')
        if not isinstance(rule.get('titles'), list) or not rule['titles'] or any(not isinstance(t, str) or not name_key(t) for t in rule['titles']):
            raise ValueError('exact exception titles required')
        spacing = rule.get('title_spacing', 'any')
        if spacing not in {'any', 'compact', 'spaced'}: raise ValueError('invalid title spacing rule')
        keys = {(name_key(t), spacing) for t in rule['titles']}
        if any(k == old and (s == os or 'any' in {s, os}) for k, s in keys for old, os in titles): raise ValueError('conflicting exception titles')
        titles.update(keys)
        action = rule.get('action')
        if action not in {'confirm_auto_latest', 'select_date', 'select_filename', 'separate_attachments', 'keep_all', 'merge_titles'}:
            raise ValueError('unknown exception action')
        if action == 'merge_titles' and len(keys) < 2:
            raise ValueError('merge_titles needs at least two titles')
        if 'match_parent_folder' in rule and (type(rule['match_parent_folder']) is not bool or action != 'separate_attachments'):
            raise ValueError('parent folder matching is limited to attachment identity')
        if 'expected_locations' in rule and (type(rule['expected_locations']) is not int or rule['expected_locations'] < 1 or action != 'keep_all'):
            raise ValueError('invalid expected location count')
        if action in {'select_date', 'select_filename'}:
            stamp = rule.get('date')
            if not isinstance(stamp, str): raise ValueError('exception date required')
            if action == 'select_date' or len(stamp) != 7:
                if date.fromisoformat(stamp).isoformat() != stamp: raise ValueError('invalid exception date')
            else:
                if not re.fullmatch(r'[0-9]{4}-[0-9]{2}', stamp): raise ValueError('invalid month date')
                date.fromisoformat(stamp + '-01')
        elif 'date' in rule: raise ValueError('date only applies to explicit selection')
        if action == 'select_filename':
            if not isinstance(rule.get('filename_stem'), str) or not rule['filename_stem'] or '/' in rule['filename_stem'] or '\\' in rule['filename_stem']:
                raise ValueError('exact filename stem required')
        elif 'filename_stem' in rule: raise ValueError('filename only applies to select_filename')
    return value


def load_exceptions(path):
    raw = Path(path).read_bytes()
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('duplicate exceptions JSON key: ' + key)
            value[key] = item
        return value
    value = validate_exceptions(json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_pairs))
    return value, hashlib.sha256(raw).hexdigest()


def rule_matches(rule, row):
    keys = {name_key(t) for t in rule['titles']}
    spacing = 'spaced' if re.search(r'\s', row['title']) else 'compact'
    if rule.get('title_spacing', 'any') not in {'any', spacing}: return False
    if name_key(row['title']) in keys: return True
    if rule.get('match_parent_folder'):
        folder = Path(row['path'].replace('\\', '/')).parent.name
        folder = re.sub(r'^\d{1,3}[. _-]+', '', folder)
        return name_key(folder) in keys
    return False


def select(rows, exceptions=None, exception_events=None):
    baseline = None
    if exceptions is not None:
        validate_exceptions(exceptions)
        baseline = {(r['document_id'], r['path'], r['filename']): r for r in select(rows)}
    rows = [{**r, **parse_filename(r['filename'])} for r in rows]
    rule_members = {}
    for rule in exceptions['rules'] if exceptions else []:
        members = [r for r in rows if not r['temporary'] and rule_matches(rule, r)]
        rule_members[rule['id']] = members
        if rule['action'] == 'merge_titles':
            # One document filed under differently spelled titles (e.g. a typo in one file name).
            # The rule only joins the family; the latest edition is still the newest filename
            # date, so later editions need no rule change and no date is pinned.
            for r in members: r['title_key'] = name_key(rule['titles'][0])
        if rule.get('title_spacing', 'any') != 'any':
            for r in members: r['title_key'] += '::spacing:' + rule['title_spacing']
        if rule['action'] != 'separate_attachments': continue
        for r in members:
            numbers = sorted({int(n) for n in ATTACHMENT.findall(r['filename'])})
            base = rule['titles'][0]
            if len(numbers) == 1:
                r['title'] = base + ' [별첨' + str(numbers[0]) + ']'
                r['title_key'] = name_key(base) + '::attachment:' + str(numbers[0])
                # Folder/title evidence identifies the document; never invent a date.
                r['parse_issues'] = [x for x in r['parse_issues'] if x not in {'missing_title', 'ambiguous_title'}]
            elif '별첨' in r['filename']:
                r['title'] = base + ' [' + EXT.sub('', r['filename']) + ']'
                r['title_key'] = name_key(base) + '::unresolved:' + filename_key(r['filename'])
                r['parse_issues'].append('ambiguous_attachment_number')
            else:
                r['title'], r['title_key'] = base, name_key(base)
    groups = defaultdict(list)
    for row in rows:
        row['status'] = 'TEMP' if row['temporary'] else 'REVIEW'
        row['reason'] = 'office_temporary_file' if row['temporary'] else ','.join(row['parse_issues'])
        if not row['temporary'] and row['title_key']:
            groups[row['title_key']].append(row)
    for items in groups.values():
        valid = [r for r in items if not r['parse_issues']]
        if not valid: continue
        newest = max(r['date'] for r in valid)
        for r in items: r['latest_date'] = newest
        # Invalid/ambiguous members may be newer; preserve the whole family for review.
        if len(valid) != len(items):
            for r in items: r['reason'] = r['reason'] or 'family_contains_unresolved_filename'
            continue
        if any(r.get('has_original') is False for r in valid if r['date'] == newest):
            for r in items: r['reason'] = 'latest_has_no_original_blocks'
            continue
        for r in valid:
            r['status'] = 'LATEST' if r['date'] == newest else 'OLDER'
            r['reason'] = 'latest_filename_date' if r['status'] == 'LATEST' else 'older_filename_date'
        paths = {str(Path(r['path']).parent) for r in items}
        for r in items: r['cross_folder_family'] = len(paths) > 1
    events = []
    if exceptions is not None:
        for r in rows:
            before = baseline[(r['document_id'], r['path'], r['filename'])]
            r.update(before_exception_status=before['status'], before_exception_title=before['title'],
                     before_exception_date=before['date'], before_exception_reason=before['reason'],
                     exception_ids=[], date_precision='day' if r['date'] else None)
        for rule in exceptions['rules']:
            members, action = rule_members[rule['id']], rule['action']
            event = {'rule_id': rule['id'], 'title': rule['titles'][0], 'action': action,
                'matched_locations': len(members), 'status': 'DOCUMENT_NOT_FOUND' if not members else 'APPLIED', 'reason': rule['reason']}
            if not members:
                events.append(event); continue
            for r in members:
                r['exception_ids'].append(rule['id'])
                r['exception_reason'] = rule['reason']
            if action in {'select_date', 'select_filename'}:
                winners = [r for r in members if (r['date'] == rule['date'] if action == 'select_date' else filename_key(r['filename']) == filename_key(rule['filename_stem']))]
                if not winners or any(r.get('has_original') is False for r in winners):
                    event['status'] = 'TARGET_NOT_FOUND' if not winners else 'TARGET_HAS_NO_ORIGINAL'
                    for r in members: r.update(status='REVIEW', reason=event['status'].lower())
                else:
                    for r in members:
                        r['latest_date'] = rule['date']
                        if r in winners:
                            r.update(status='LATEST', reason='user_selected_version', date=rule['date'],
                                     date_precision='month' if len(rule['date']) == 7 else 'day')
                        else: r.update(status='EXCLUDED', reason='not_user_selected_version')
            elif action == 'keep_all':
                for r in members:
                    r.update(status='KEEP' if r.get('has_original') is not False else 'REVIEW', reason='user_keep_all_versions')
                if rule.get('expected_locations') and len(members) != rule['expected_locations']:
                    event['status'] = 'APPLIED_COUNT_DIFFERS'
                    event['expected_locations'] = rule['expected_locations']
            elif action == 'merge_titles':
                event['merged_titles'] = sorted({r['title'] for r in members})
                if not any(r['status'] == 'LATEST' for r in members): event['status'] = 'MERGED_LATEST_UNRESOLVED'
            elif action == 'confirm_auto_latest':
                event['status'] = 'CONFIRMED' if any(r['status'] == 'LATEST' for r in members) else 'AUTO_LATEST_UNRESOLVED'
            elif action == 'separate_attachments':
                event['separate_document_keys'] = len({r['title_key'] for r in members})
                if any('ambiguous_attachment_number' in r['parse_issues'] for r in members): event['status'] = 'ATTACHMENT_NUMBER_UNRESOLVED'
            event['retained_locations'] = sum(r['status'] in {'LATEST', 'KEEP', 'REVIEW'} for r in members)
            events.append(event)
        if exceptions['single_file_folder_is_latest']:
            folders = defaultdict(list)
            for r in rows:
                if r['temporary']: continue
                parent = str(Path(r['path'].replace('\\', '/')).parent)
                if r.get('filename_source') == 'document_name' or (parent == '.' and r.get('filename_source') != 'raw_filename'): continue
                folders[parent].append(r)
            singles = []
            explicit = {r['id'] for r in exceptions['rules'] if r['action'] != 'separate_attachments'}
            for items in folders.values():
                if len({r['path'] for r in items}) != 1: continue
                for r in items:
                    if explicit.intersection(r['exception_ids']): continue
                    if r.get('has_original') is False or 'ambiguous_attachment_number' in r['parse_issues']: continue
                    r.update(status='LATEST', reason='single_file_in_folder_user_rule')
                    r['exception_ids'].append('single-file-folder')
                    r['exception_reason'] = '사용자 지정: 현재 입력 목록에서 폴더에 문서 파일이 하나이면 최신으로 취급'
                    singles.append(r)
            events.append({'rule_id': 'single-file-folder', 'title': '폴더당 문서 한 개', 'action': 'single_file_latest',
                'status': 'APPLIED', 'matched_locations': len(singles), 'retained_locations': len(singles),
                'reason': '실제 경로가 있는 현재 내규 입력 목록 기준; 임시파일 제외; 명시 개별 예외 우선'})
        for r in rows:
            r['exception_changed'] = any(r[k] != r['before_exception_' + k] for k in ('status', 'title', 'date'))
            r['exception_ids_text'] = ','.join(r['exception_ids'])
    if exception_events is not None: exception_events.extend(events)
    # One physical document can own several aliases. Its SQL ID is excludable only
    # when ALL locations are older and none is external/unknown/current.
    physical = defaultdict(list)
    for r in rows: physical[r['document_id']].append(r)
    for items in physical.values():
        can_exclude = all(r['status'] in {'OLDER', 'EXCLUDED', 'TEMP'} and not r.get('protected_alias') for r in items)
        for r in items: r['physical_exclusion_candidate'] = can_exclude
    return sorted(rows, key=lambda r: (r['title_key'], r['date'], r['path'], r['document_id']))


def inventory_generation(generation):
    manifest_path, database = generation / 'manifest.json', generation / 'store.sqlite'
    manifest = json.loads(manifest_path.read_text('utf-8'))
    if manifest.get('schema_version') not in {'term-source-generation-v1', 'term-source-generation-v2'}:
        raise ValueError('unsupported source generation schema')
    if any(Path(str(database) + s).exists() for s in ('-wal', '-journal')):
        raise ValueError('source database has WAL/journal; immutable generation required')
    before, manifest_hash = state(database), sha(manifest_path)
    result, external, unknown = [], 0, 0
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        records = db.execute("SELECT document_id,name,source_artifact_sha256,"
            "json_extract(json,'$.document_metadata'),json_extract(json,'$.origin'),"
            "json_extract(json,'$.document_category'),json_extract(json,'$.document_kind') "
            "FROM document ORDER BY document_id").fetchall()
        for did, name, artifact, raw, origin_raw, category, kind in records:
            meta, origin = json.loads(raw) if raw else {}, json.loads(origin_raw) if origin_raw else {}
            meta, origin = meta or {}, origin or {}
            if not isinstance(meta, dict) or not isinstance(origin, dict): raise ValueError('invalid document metadata: ' + did)
            aliases = meta.get('aliases', [])
            if not isinstance(aliases, list) or any(not isinstance(a, dict) for a in aliases):
                raise ValueError('invalid document aliases: ' + did)
            locations = [meta, *aliases]
            if not meta.get('relative_path') and origin.get('status') == 'verified':
                if origin.get('source_artifact_sha256') != artifact: raise ValueError('origin hash mismatch: ' + did)
                locations[0] = {**meta, 'relative_path': origin.get('raw_relative_path')}
            local_rows, seen, protected = [], set(), False
            for loc in locations:
                path = loc.get('relative_path') or ''
                source = loc.get('source_category') or meta.get('source_category') or category
                if not source:
                    source = {'internal_regulation': 'internal', 'internal_rule': 'internal', 'internal': 'internal'}.get(kind or meta.get('kind'))
                if not source and isinstance(path, str) and path.startswith(('internal/', 'RAW/internal/')): source = 'internal'
                if source != 'internal':
                    protected = True
                    if source == 'external': external += 1
                    else: unknown += 1
                    continue
                if not isinstance(path, str): raise ValueError('non-string path: ' + did)
                filename = loc.get('file_name') or (path.replace('\\', '/').rsplit('/', 1)[-1] if path else '') or name
                if not isinstance(filename, str) or not filename: raise ValueError('missing document filename: ' + did)
                identity = path or filename
                if identity in seen: continue
                seen.add(identity)
                local_rows.append({'document_id': did, 'source_artifact_sha256': artifact,
                    'filename': filename, 'path': path or filename, 'team': loc.get('team') or meta.get('team', ''),
                    'filename_source': 'metadata_filename' if loc.get('file_name') else 'relative_path' if path else 'document_name',
                    'has_original': bool(db.execute('SELECT 1 FROM source_block WHERE document_id=? LIMIT 1', (did,)).fetchone())})
            for row in local_rows: row['protected_alias'] = protected
            result.extend(local_rows)
    if before != state(database) or sha(manifest_path) != manifest_hash:
        raise ValueError('generation changed during inventory; rerun into a new result directory')
    return result, {'mode': 'structured_generation', 'generation_id': manifest.get('generation_id'),
        'manifest_sha256': manifest_hash, 'store_sha256_declared': manifest.get('store_sha256'),
        'large_store_hash_recomputed': False, 'database_state': before, 'metadata_sha256': fingerprint(records),
        'total_physical_documents': len(records), 'external_locations_skipped': external,
        'unknown_locations_skipped': unknown, 'scope': 'all classified internal locations in selected generation; before current search exclusions'}



DEFAULT_EXCEPTIONS = Path(__file__).resolve().parents[2] / '00_SYSTEM/FILENAME_EXCEPTIONS.json'

def latest_marks(rows):
    """Serving approval, not certification of a legal effective date."""
    groups = defaultdict(list)
    for row in rows: groups[row['document_id']].append(row)
    return [{'document_id': did, 'source_artifact_sha256': items[0]['source_artifact_sha256'],
             'is_latest': not all(r['physical_exclusion_candidate'] for r in items),
             'selection_statuses': sorted({r['status'] for r in items}),
             'date_verified': False,
             'locations': [{'path': r['path'], 'title': r['title'], 'date': r['date'],
                 'status': r['status'], 'reason': r['reason'], 'exception_ids': r.get('exception_ids', [])}
                 for r in items]} for did, items in sorted(groups.items())]
