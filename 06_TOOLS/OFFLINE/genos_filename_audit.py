"""Read-only filename/date inventory. Reports are NOT a RAG activation plan."""
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
        if not isinstance(rule, dict) or set(rule) - {'id', 'titles', 'action', 'reason', 'date', 'filename_stem', 'match_parent_folder', 'expected_locations'}:
            raise ValueError('invalid exception rule fields')
        if not isinstance(rule.get('id'), str) or not rule['id'] or rule['id'] in ids:
            raise ValueError('duplicate/missing exception ID')
        ids.add(rule['id'])
        if not isinstance(rule.get('reason'), str) or not rule['reason']:
            raise ValueError('exception reason required')
        if not isinstance(rule.get('titles'), list) or not rule['titles'] or any(not isinstance(t, str) or not name_key(t) for t in rule['titles']):
            raise ValueError('exact exception titles required')
        keys = {name_key(t) for t in rule['titles']}
        if titles & keys: raise ValueError('conflicting exception titles')
        titles.update(keys)
        action = rule.get('action')
        if action not in {'confirm_auto_latest', 'select_date', 'select_filename', 'separate_attachments', 'keep_all'}:
            raise ValueError('unknown exception action')
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
    if row['title_key'] in keys: return True
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


def load_helper(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_generation(root, explicit=None):
    here = Path(__file__).resolve().parent
    # Delivery bundles the exact existing service/gate selection helpers.
    if (here / 'deployment_paths.py').exists():
        deployment_file, selector_file = here / 'deployment_paths.py', here / 'genos_generation_e2e.py'
    else:
        deployment_file = root / '02_BACKEND/semantic_runtime/deployment_paths.py'
        selector_file = root / '06_TOOLS/COMMANDS/genos_generation_e2e.py'
    deployment = load_helper('audit_deployment_paths', deployment_file)
    selector = load_helper('audit_generation_selector', selector_file)
    settings = dict(os.environ)
    config = deployment.install(root, environment=settings)
    if config is not None:
        generation = selector.selected_generation(explicit, settings=settings)
        deployment.verify_generation(config, generation)
    else:
        generation = selector.selected_generation(explicit) if explicit else selector.operator_generation(root)
    binding = {'code_root': str(root), 'generation': str(generation),
        'selection_source': deployment.CONFIG if config else 'explicit_or_existing_operator_settings',
        'selector_sha256': sha(selector_file), 'deployment_helper_sha256': sha(deployment_file),
        'code_serving_revision': None, 'field_validation': 'NOT_VERIFIED'}
    for rel in ('service.py', 'CODE_MANIFEST.json', deployment.CONFIG):
        if (root / rel).is_file(): binding[rel + '_sha256'] = sha(root / rel)
    return generation, binding


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
    if not result: raise ValueError('no classified internal document metadata found')
    return result, {'mode': 'structured_generation', 'generation_id': manifest.get('generation_id'),
        'manifest_sha256': manifest_hash, 'store_sha256_declared': manifest.get('store_sha256'),
        'large_store_hash_recomputed': False, 'database_state': before, 'metadata_sha256': fingerprint(records),
        'total_physical_documents': len(records), 'external_locations_skipped': external,
        'unknown_locations_skipped': unknown, 'scope': 'all classified internal locations in selected generation; before current search exclusions'}


def inventory_raw(root):
    result, before = [], {}
    def fail(exc): raise exc
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        for d in dirs:
            if (Path(folder) / d).is_symlink(): raise ValueError('symlink directory requires explicit separate inventory')
        before[str(Path(folder))] = state(folder)
        for filename in sorted(files):
            p = Path(folder) / filename
            if p.is_symlink(): raise ValueError('symlink file requires explicit separate inventory')
            if not p.is_file(): raise ValueError('non-regular input file')
            rel = p.relative_to(root).as_posix()
            result.append({'document_id': fingerprint(rel)[:24], 'filename': filename, 'path': rel,
                           'team': '', 'source_artifact_sha256': None, 'filename_source': 'raw_filename'})
    if any(state(p) != s for p, s in before.items()): raise ValueError('RAW directories changed during inventory')
    if not result: raise ValueError('no files in explicit internal RAW folder')
    return result, {'mode': 'explicit_internal_raw_folder', 'raw_root': str(root), 'metadata_sha256': fingerprint(result),
        'scope': 'all files recursively below explicit root; no document bodies read', 'generation': None}


def safe_cell(value):
    text = str(value or '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def validate_output(out, input_root, code_root=None, cwd=None):
    """Allow new reports in the operator's TRANSFER even inside the checkout."""
    out, input_root = Path(out).resolve(), Path(input_root).resolve()
    if out.is_relative_to(input_root):
        raise ValueError('output must be outside input directory')
    if code_root is not None and out.is_relative_to(Path(code_root).resolve()):
        reports = Path(cwd or Path.cwd()) / 'FILENAME_AUDIT_RESULTS'
        if reports.is_symlink():
            raise ValueError('FILENAME_AUDIT_RESULTS must not be a symlink')
        if not out.is_relative_to(reports.resolve()) or out == reports.resolve():
            raise ValueError('inside DEV, output must be a new directory under the current FILENAME_AUDIT_RESULTS')


def write_csv(path, rows, fields):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([label for _, label in fields])
        for row in rows: writer.writerow([safe_cell(row.get(key, '')) for key, _ in fields])


def report(out, rows, binding, exception_events=None):
    exception_events = exception_events or []
    fields = [('title', '문서명'), ('date', '날짜')]
    retained = [r for r in rows if r['status'] in {'LATEST', 'KEEP', 'REVIEW'}]
    latest = [r for r in rows if r['status'] == 'LATEST']
    review = [r for r in rows if r['status'] == 'REVIEW']
    older = [r for r in rows if r['status'] in {'OLDER', 'EXCLUDED'}]
    for name, subset in [('ALL_INTERNAL', rows), ('RETAINED_INTERNAL', retained), ('LATEST_ONLY', latest)]:
        unique = list({(r['title'], r['date']): r for r in subset}.values())
        write_csv(out / (name + '.csv'), unique, fields)
    audit_fields = fields + [('filename', '원본파일명'), ('path', '원본경로'), ('status', '판정'),
        ('reason', '사유'), ('latest_date', '그룹최신날짜'), ('document_id', '문서ID'),
        ('physical_exclusion_candidate', '문서ID제외가능후보'), ('date_tokens_text', '발견날짜전체'),
        ('date_precision', '날짜정밀도'), ('exception_ids_text', '적용예외ID'), ('exception_reason', '예외사유'),
        ('before_exception_status', '예외전판정'), ('before_exception_title', '예외전문서명'), ('before_exception_date', '예외전날짜')]
    for r in rows: r['date_tokens_text'] = ' / '.join(r['date_tokens'])
    for name, subset in [('AUDIT_DETAIL', rows), ('OLDER_CANDIDATES', older), ('REVIEW', review)]:
        write_csv(out / (name + '.csv'), subset, audit_fields)
    write_csv(out / 'EXCEPTION_CHANGES.csv', [r for r in rows if r.get('exception_changed')], audit_fields)
    write_csv(out / 'EXCEPTION_RESULTS.csv', exception_events,
        [('rule_id', '예외ID'), ('title', '문서명'), ('action', '처리'), ('status', '적용상태'),
         ('matched_locations', '해당파일수'), ('retained_locations', '유지파일수'), ('reason', '사유')])
    write_json(out / 'EXCEPTION_RESULTS.json', exception_events)
    counts = dict(Counter(r['status'] for r in rows))
    exception_warnings = [e for e in exception_events if e['status'] not in {'APPLIED', 'CONFIRMED'}]
    summary = {'policy': POLICY, 'status': 'COMPLETE_WITH_REVIEW' if review or binding.get('unknown_locations_skipped') or exception_warnings else 'COMPLETE',
        'counts_by_location': counts, 'all_locations': len(rows), 'retained_locations': len(retained),
        'latest_title_date_pairs': len({(r['title_key'], r['date']) for r in latest}),
        'internal_physical_documents': len({r['document_id'] for r in rows}),
        'physical_exclusion_candidates': len({r['document_id'] for r in rows if r['physical_exclusion_candidate']}),
        'binding': binding, 'model_calls': 0, 'source_modified': False, 'rag_applied': False,
        'exception_warning_count': len(exception_warnings),
        'exception_changed_locations': sum(bool(r.get('exception_changed')) for r in rows),
        'before_exception_counts': dict(Counter(r.get('before_exception_status', r['status']) for r in rows)),
        'date_century_rule': '00..69 => 2000..2069; 70..99 => 1970..1999',
        'filename_date_is_effective_date': False}
    write_json(out / 'AUDIT.json', {'summary': summary, 'rows': rows})
    write_json(out / 'SUMMARY.json', summary)
    esc = lambda x: html.escape(str(x or ''))
    def table(subset):
        body = ''.join('<tr class="' + r['status'].lower() + '"><td>' + esc(r['title']) + '</td><td>' +
            esc(r['date'] or ('일자 미기재' if r['status'] in {'LATEST', 'KEEP'} else '확인 필요')) + '</td><td>' + esc(LABEL[r['status']]) +
            (' · 예외' if r.get('exception_ids') else '') +
            '</td><td><details><summary>원본·사유</summary>' + esc(r['path']) + '<br>' + esc(r['reason']) +
            '<br>' + esc(r.get('exception_reason')) + '<br>' + esc(r.get('exception_ids_text')) + '</details></td></tr>' for r in subset)
        return '<table><thead><tr><th>문서명</th><th>날짜</th><th>판정</th><th>원본 확인</th></tr></thead><tbody>' + body + '</tbody></table>'
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>내규 판본 비교</title>
<style>body{font:15px system-ui;margin:24px;color:#1c2635;background:#f4f6f8}h1{font-size:24px}main{display:grid;grid-template-columns:1fr 1fr;gap:18px}section{background:white;padding:14px;min-width:0}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #ddd;padding:9px;text-align:left;overflow-wrap:anywhere}th{position:sticky;top:0;background:#e8edf4}td:nth-child(2){white-space:nowrap}.older,.excluded,.temp{background:#fff0f0}.review{background:#fff8db}.latest{background:#f0faf2}.keep{background:#e8f2ff}details{max-width:300px}a{color:#24579c}@media(max-width:900px){main{grid-template-columns:1fr}}</style>
<h1>전체 내규 ↔ 필터링 후 남은 내규</h1><p>문서명과 파일명 날짜 기준 검증 결과입니다. 실제 RAG는 변경하지 않았습니다.</p>'''
    page += '<p>전체 ' + str(len(rows)) + '개 · 최신 ' + str(len(latest)) + '개 · 예외 전체유지 ' + str(counts.get('KEEP', 0)) + '개 · 제외 후보 ' + str(len(older)) + '개 · 검토 보존 ' + str(len(review)) + '개</p>'
    page += '<p>번호별 별첨 분리·지정 판본·두 문서 유지·단일파일 폴더는 예외 설정에 따릅니다. 노란 행은 검토 보존입니다. 날짜는 시행일이 아니며 월만 지정된 파일은 일자를 만들지 않습니다.</p>'
    if exception_events:
        page += '<section><h2>예외 적용 결과</h2><p>미발견 또는 개수 차이는 아래에 표시합니다. 변경된 원본 ' + str(summary['exception_changed_locations']) + '개.</p><table><tr><th>문서/규칙</th><th>상태</th><th>파일 수</th><th>규칙</th></tr>'
        for e in exception_events:
            status_label = {'APPLIED': '적용', 'CONFIRMED': '현재 최신 확인', 'DOCUMENT_NOT_FOUND': '해당 문서 미발견',
                'TARGET_NOT_FOUND': '지정 판본 미발견 · 검토 보존', 'TARGET_HAS_NO_ORIGINAL': '지정 판본 원문 없음',
                'APPLIED_COUNT_DIFFERS': '유지 완료 · 예상 개수와 다름', 'AUTO_LATEST_UNRESOLVED': '현재 최신 미확정',
                'ATTACHMENT_NUMBER_UNRESOLVED': '별첨 번호 확인 필요'}.get(e['status'], e['status'])
            page += '<tr><td>' + esc(e['title']) + '</td><td>' + esc(status_label) + '</td><td>' + esc(e['matched_locations']) + '</td><td>' + esc(e['reason']) + '</td></tr>'
        page += '</table><p><a href="EXCEPTION_RESULTS.csv">규칙별 결과</a> · <a href="EXCEPTION_CHANGES.csv">예외 적용으로 달라진 문서</a></p></section>'
    if binding.get('unknown_locations_skipped'): page += '<p>분류 불명 위치 ' + str(binding['unknown_locations_skipped']) + '개는 내규 여부 확인이 필요합니다.</p>'
    page += '<p><a href="ALL_INTERNAL.csv">전체 문서명+날짜</a> · <a href="RETAINED_INTERNAL.csv">남은 문서명+날짜</a> · <a href="LATEST_ONLY.csv">최신 확정만</a> · <a href="AUDIT_DETAIL.csv">상세 원장</a> · <a href="REVIEW.csv">검토 대상</a></p>'
    page += '<main><section><h2>전체 내규 (' + str(len(rows)) + ')</h2>' + table(rows) + '</section><section><h2>필터링 후 (' + str(len(retained)) + ')</h2>' + table(retained) + '</section></main></html>'
    (out / 'COMPARE.html').write_text(page, encoding='utf-8')
    return summary


def main(argv=None, default_exceptions_path=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', nargs='?', choices=['compare', 'check'], default='compare')
    p.add_argument('--root', type=Path, default=Path.home() / 'DEV')
    p.add_argument('--generation', type=Path)
    p.add_argument('--raw-root', type=Path, help='Explicit INTERNAL folder; inventories filenames only')
    p.add_argument('--output', type=Path, help='New output directory; must not already exist')
    configs = p.add_mutually_exclusive_group()
    configs.add_argument('--exceptions', type=Path, help='One editable exceptions JSON document')
    configs.add_argument('--no-exceptions', action='store_true', help='Disable all temporary exceptions including singleton folders')
    a = p.parse_args(argv)
    if a.raw_root and a.generation: p.error('--raw-root and --generation cannot be combined')
    if a.action == 'check':
        import unittest
        test_file = Path(__file__).with_name('test_filename_audit.py')
        if not test_file.exists():
            test_file = Path(__file__).resolve().parents[2] / '08_DEPLOYMENT/GENOS/handoffs/filename_audit_20261015_r3/test_filename_audit.py'
        tests = load_helper('audit_tests', test_file)
        if default_exceptions_path is not None: tests.EXCEPTIONS_PATH = Path(default_exceptions_path)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        return 0 if result.wasSuccessful() else 1
    out = (a.output or Path.cwd() / 'FILENAME_AUDIT_RESULTS' / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])).resolve()
    # Resolve before creating anything: explicit output inside an input is refused.
    try:
        if a.raw_root:
            input_root = a.raw_root.expanduser().resolve(strict=True)
            if not input_root.is_dir(): raise ValueError('RAW input must be a directory')
        else:
            root = a.root.expanduser().resolve(strict=True)
            generation, binding = resolve_generation(root, a.generation)
            input_root = generation
        validate_output(out, input_root, None if a.raw_root else root)
    except Exception as exc:
        print('FAILED_PREFLIGHT: ' + str(exc), file=sys.stderr, flush=True)
        return 1
    out.mkdir(parents=True, exist_ok=False)
    status = {'status': 'STARTED', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'python': sys.executable, 'python_version': sys.version, 'scanner_sha256': sha(__file__), 'rag_applied': False,
        'working_directory': str(Path.cwd()), 'output_directory': str(out), 'delivery_revision': 'R3'}
    write_json(out / 'RUN_STARTED.json', status)
    print('RESULT_DIR=' + str(out), flush=True)
    try:
        config_path = None if a.no_exceptions else (a.exceptions or default_exceptions_path)
        exceptions, config_hash = load_exceptions(config_path) if config_path else (None, None)
        if config_path:
            print('EXCEPTIONS=' + str(Path(config_path).resolve()) + ' SHA256=' + config_hash, flush=True)
        if a.raw_root:
            rows, binding = inventory_raw(input_root)
        else:
            rows, data_binding = inventory_generation(generation)
            binding.update(data_binding)
        if config_path and sha(config_path) != config_hash: raise ValueError('exceptions file changed during inventory')
        if exceptions is not None: write_json(out / 'APPLIED_EXCEPTIONS.json', exceptions)
        events = []
        selected = select(rows, exceptions, events)
        binding['exceptions'] = {'enabled': exceptions is not None, 'path': str(Path(config_path).resolve()) if config_path else None,
                                'sha256': config_hash, 'revision': exceptions['revision'] if exceptions else None}
        result = report(out, selected, {**status, **binding}, events)
        write_json(out / 'RUN_STATUS.json', {'status': result['status'], 'rag_applied': False})
        print(json.dumps({k: result[k] for k in ('status', 'counts_by_location', 'all_locations', 'retained_locations', 'rag_applied')}, ensure_ascii=False), flush=True)
        print('COMPARE=' + str(out / 'COMPARE.html'), flush=True)
        return 0
    except Exception as exc:
        write_json(out / 'RUN_STATUS.json', {'status': 'FAILED', 'error_type': type(exc).__name__, 'error': str(exc), 'rag_applied': False})
        print('FAILED: ' + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    config = Path(__file__).with_name('FILENAME_EXCEPTIONS.json')
    if not config.exists() and Path(__file__).parent.name == 'OFFLINE':
        config = Path(__file__).resolve().parents[2] / '08_DEPLOYMENT/GENOS/handoffs/filename_audit_20261015_r3/FILENAME_EXCEPTIONS.json'
    raise SystemExit(main(default_exceptions_path=config))
