"""Import curated source entries through the existing shortcut/wiki authority.

This is a data operation, not a completed model investigation or an interpretation
approval. Portable coordinates are rebound to an explicitly selected source store.
"""
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from semantic_runtime.legal_agent.corrected_memory import MemoryError, digest, encoded
from semantic_runtime.document_roles import ANNEX_FOLDERS, HISTORY_ROLES, classify

SCHEMA = 'curated-source-package-v1'
CONTRACT = 'curated-core-evidence-route-v1'
COMMON_VISIBILITY = 'COMMON_CATALOG'
COMMON_OWNER = '__shortcut_catalog__'
COMMON_TEAM = '__common__'
COMMON_TENANT = '__application_catalog__'
_COMMON_OPERATOR = object()
TARGET_BINDING = 'target-selected-document-article-v1'
# Same structured-primary-pdf-reference-v2 order. The serving handoff omits
# offline build modules, so resolution has no dependency on their installation.
REPRESENTATION_PRIORITY = {'.xml': 0, '.html': 1, '.htm': 1, '.hwpx': 2,
                           '.docx': 3, '.pdf': 4, '.hwp': 5, '.doc': 6}


def name_key(value):
    return ''.join(unicodedata.normalize('NFC', str(value)).split())


def document_labels(doc):
    """Keep canonical titles separate from the physical/display name."""
    payload = json.loads(doc['json'])
    meta = payload.get('document_metadata') or {}
    labels = [doc['name']]
    for item in [meta, *meta.get('aliases', [])]:
        if not isinstance(item, dict):
            continue
        labels.extend(str(item[k]) for k in ('document_title', 'file_name', 'relative_path',
                                             'display_name', 'folder_path', 'original_path') if item.get(k))
        labels.extend(item.get('folder_names') or [])
    expanded = []
    for label in labels:
        expanded.extend(re.split(r'\s*>\s*|[/\\]', str(label)))
    return meta, [*labels, *expanded]


def body_name_match(doc, entry, *, context=None):
    meta, _ = context if context is not None else document_labels(doc)
    role = meta.get('document_role') or meta.get('raw_role')
    if role and role != 'body':
        return False

    def leaf(value):
        return re.split(r'\s*>\s*|[/\\]', unicodedata.normalize('NFC', str(value)))[-1]

    def stem(value):
        return re.sub(r'\.(?:html?|xml|hwpx?|docx?|pdf)$', '', leaf(value), flags=re.I)

    def forms(value):
        key = name_key(stem(value))
        return {key, re.sub(r'[_\-]*(?:전문|조문|본문)$', '', key)}

    canonical = name_key(entry['document_name'])
    expected = {canonical}
    for alias in entry.get('document_name_aliases', []):
        expected.update(forms(alias))
    physical = meta.get('file_name') or meta.get('relative_path') or leaf(doc['name'])
    physical_stem = stem(physical)
    # Strip the known whole title before looking for attachment markers. Words
    # such as 서식 can be part of the actual regulation title, not its role.
    folded = name_key(physical_stem)
    remainder = physical_stem
    for key in sorted(expected, key=len, reverse=True):
        if key and folded.startswith(key):
            remainder = folded[len(key):]
            break
    # Registered body titles can themselves start with [별첨1]. A collector
    # basename may change brackets/spaces to parentheses/underscores. Use the
    # preserved canonical title to distinguish that whole name from an added
    # attachment label; this equivalence never grants a name match by itself.
    compact = lambda value: re.sub(r'[_\s\[\]()（）［］]', '', name_key(value))
    if role == 'body' and forms(meta.get('document_title', '')) & expected:
        if any(compact(physical_stem) == compact(key) for key in expected):
            remainder = ''
    inferred = classify('attachment', '', remainder)
    if inferred in HISTORY_ROLES or inferred in ('annex', 'form', 'reference'):
        return False
    if re.search(r'(?:^|[_\s\-.(（\[［])(?:별표|별지|서식|별첨|참고|부록|첨부)(?=$|[_\s\-.)）\]］\d])', remainder):
        return False
    if re.match(r'^[_\s\-]*(?:시행령|시행규칙|시행세칙)', remainder):
        return False
    # Folder components are scope/location evidence only. They cannot identify
    # a body when the individual title or filename names another document.
    path = meta.get('relative_path') or meta.get('folder_path') or ''
    folders = re.split(r'\s*>\s*|[/\\]', unicodedata.normalize('NFC', path))
    if meta.get('relative_path'):
        folders = folders[:-1]
    folders.extend(meta.get('folder_names') or [])
    if any(unicodedata.normalize('NFC', part) in ANNEX_FOLDERS
           and name_key(part) != canonical for part in folders):
        return False
    labels = [leaf(doc['name'])]
    for item in [meta, *meta.get('aliases', [])]:
        if not isinstance(item, dict):
            continue
        if (item.get('document_role') or item.get('raw_role')) not in (None, 'body'):
            continue
        labels.extend(item[k] for k in ('document_title', 'file_name', 'relative_path',
                                       'display_name', 'original_path', 'orig_filename') if item.get(k))
    return any(forms(label) & expected for label in labels)


def target_documents(store, entries):
    """Resolve all articles of one logical title to one target body document."""
    docs = [(doc, document_labels(doc)) for doc in store.db.execute('SELECT * FROM document ORDER BY document_id')]
    selected = {}
    for name, entry in entries.items():
        candidates = [(d, context) for d, context in docs if body_name_match(d, entry, context=context)]
        if not candidates:
            raise MemoryError('target body document missing: '+name)
        def rank(candidate):
            doc, (meta, _) = candidate
            file = meta.get('file_name') or meta.get('relative_path') or doc['name']
            return REPRESENTATION_PRIORITY.get(Path(file).suffix.lower(), 99)
        best = min(map(rank, candidates))
        candidates = [d for d in candidates if rank(d) == best]
        if len(candidates) != 1:
            raise MemoryError('target body document ambiguous: '+name+'; candidates='+
                              ', '.join(d['name'] for d, _ in candidates))
        selected[name] = candidates[0][0]
    return selected


def common_scope_id():
    return 'scope:' + digest([COMMON_TENANT, COMMON_OWNER, COMMON_TEAM, None])


def is_common_operator(principal):
    return (principal.get('_common_operator') is _COMMON_OPERATOR
            and principal.get('authenticated') is True
            and (principal.get('tenant_id'), principal.get('user_id'), principal.get('team_id'))
            == (COMMON_TENANT, COMMON_OWNER, COMMON_TEAM))


def common_principal(*, store=None, receipt=None):
    """Filesystem-only catalogue operations; no consumer user/team registration."""
    if store is not None:
        documents = sorted(store.manifest['scope']['document_version_ids'])
    elif receipt is not None and receipt.get('visibility') == COMMON_VISIBILITY:
        documents = receipt['documents']
    else:
        raise MemoryError('common catalogue needs selected source or common receipt')
    return {'tenant_id': COMMON_TENANT, 'user_id': COMMON_OWNER, 'team_id': COMMON_TEAM,
            'authenticated': True, 'document_ids': documents, '_common_operator': _COMMON_OPERATOR}


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def resolve(package, store, principal):
    """Strict imports retain their pins; explicit portable seeds bind onsite."""
    if package.get('schema_version') != SCHEMA or not package.get('cases'):
        raise MemoryError('unsupported or empty curated source package')
    if not principal.get('authenticated'):
        raise MemoryError('explicit authenticated target owner/team required')
    common = package.get('visibility') == COMMON_VISIBILITY
    if common != is_common_operator(principal):
        raise MemoryError('explicit common catalogue operation or private principal required')
    if package.get('legal_claim_reuse') is not False:
        raise MemoryError('curated entries cannot grant legal interpretation approval')
    policy = package.get('source_binding_policy', 'exact-source-v1')
    if policy not in ('exact-source-v1', TARGET_BINDING):
        raise MemoryError('unsupported curated source binding policy')
    portable = policy == TARGET_BINDING
    if portable and package.get('target_source_interpretation') != 'CURRENT_SOURCE_REQUIRES_ASSESSMENT':
        raise MemoryError('portable source seeds cannot approve the target interpretation')
    nav = json.loads((store.path/'navigation'/'manifest.json').read_text())
    if nav['generation_id'] != store.manifest['generation_id'] or nav['source_store_sha256'] != store.manifest['store_sha256']:
        raise MemoryError('selected navigation/source generation mismatch')
    fulltext = json.loads((store.path/'fulltext'/'manifest.json').read_text())
    if fulltext['generation_id'] != nav['generation_id'] or fulltext['source_store_sha256'] != nav['source_store_sha256'] or fulltext['navigation_index_sha256'] != nav['index_sha256']:
        raise MemoryError('selected fulltext/navigation generation mismatch')
    binding = {'generation': store.manifest['generation_id'],
               'store_sha256': store.manifest['store_sha256'], 'unit_index_sha256': fulltext['index_sha256']}
    entries = {}
    if portable:
        for case in package['cases']:
            for entry in case['entries']:
                old = entries.setdefault(entry['document_name'], entry)
                if old.get('document_name_aliases', []) != entry.get('document_name_aliases', []):
                    raise MemoryError('inconsistent portable document aliases')
    selected = target_documents(store, entries) if portable else {}
    ids = set(); cases = []; unit_cache = {}
    for case in package['cases']:
        if case['case_id'] in ids or not case['question'].strip() or not case['entries']:
            raise MemoryError('duplicate case, empty question or missing source entries')
        ids.add(case['case_id']); targets = []
        for entry in case['entries']:
            docs = ([selected[entry['document_name']]] if portable else
                    list(store.db.execute('SELECT * FROM document WHERE name=?', (entry['document_name'],))))
            if not portable:
                docs = [d for d in docs if d['source_artifact_sha256'] == entry['source_artifact_sha256']]
            if len(docs) != 1:
                raise MemoryError('source document version missing or ambiguous: '+entry['document_name'])
            doc = docs[0]; did = doc['document_id']
            if did not in principal['document_ids']:
                raise MemoryError('source outside target document permissions: '+did)
            if did not in unit_cache:
                coordinates = {}
                for unit in store.db.execute('SELECT * FROM source_unit WHERE document_id=?', (did,)):
                    coordinates.setdefault(json.loads(unit['json']).get('coordinate_key'), []).append(unit)
                unit_cache[did] = coordinates
            units = unit_cache[did].get(entry['coordinate_key'], [])
            if len(units) != 1:
                raise MemoryError('source coordinate missing or ambiguous: '+entry['coordinate_key'])
            section = store.section(did, units[0]['unit_id'])
            blocks = section['blocks']; text = '\n'.join(b['text'] for b in blocks)
            if not blocks or not text.strip() or (not portable and text_sha(text) != entry['section_text_sha256']):
                raise MemoryError('source section bytes differ: '+entry['document_name']+' '+entry['coordinate_key'])
            if any(store.source(did, b['block_id'])['source_artifact_sha256'] != doc['source_artifact_sha256'] for b in blocks):
                raise MemoryError('target section source provenance differs: '+entry['document_name'])
            spans = [{'block_id': str(b['block_id']), 'start_cp': 0, 'end_cp': len(b['text']),
                      'text_hash': digest(b['text']), 'unit_id': str(b['unit_id'])} for b in blocks if b['text']]
            read_ids = list(dict.fromkeys(s['unit_id'] for s in spans))
            targets.append({'document_id': did, 'document_name': doc['name'],
                            'article_unit_id': str(units[0]['unit_id']), 'read_unit_ids': read_ids,
                            'spans': spans, 'text': text, 'coordinate_key': entry['coordinate_key'],
                            'evidence_role': entry['evidence_role'],
                            'canonical_document_name': entry['document_name'],
                            'source_binding_policy': policy,
                            'source_artifact_sha256': doc['source_artifact_sha256'],
                            'section_text_sha256': text_sha(text)})
        cases.append({'case': case, 'targets': targets})
    store.check_unchanged()
    return binding, cases


def import_package(repo, principal, package, store):
    """Atomically register scope-bound source routes. Retired imports stay retired."""
    binding, cases = resolve(package, store, principal)
    fingerprint = digest(package)
    scope = repo.scope(principal)
    import_id = 'curated-import:'+digest([scope, fingerprint, binding])
    previous = repo.db.execute('SELECT payload FROM sw_import WHERE id=?', (import_id,)).fetchone()
    if previous:
        receipt = json.loads(previous[0])
        verify_package(repo, principal, receipt)
        # A corrected selector must not silently reuse a formerly misbound
        # registration in the same immutable source generation.
        records = {r['case_id']: r for r in receipt['records']}
        if len(records) != len(cases):
            raise MemoryError('existing import cases differ; preserved')
        for item in cases:
            record = records.get(item['case']['case_id'])
            if record is None:
                raise MemoryError('existing import case missing; preserved')
            value = repo.current(record['unit_id'], record['revision'], principal)
            actual = [{k: v for k, v in target.items() if k != 'source_ref'}
                      for target in value['core_evidence_route']['targets']]
            expected = [{k: v for k, v in target.items() if k != 'text'} for target in item['targets']]
            if actual != expected:
                raise MemoryError('existing import source resolution differs; preserved; retire and register a new package explicitly')
        return {**receipt, 'already_imported': True}
    records = []
    with repo.transaction():
        scope = repo.scope(principal, create=True)
        for item in cases:
            case = item['case']
            unit = 'unit:core:curated:'+digest([scope, package['package_id'], case['case_id'], fingerprint, binding])
            targets = []; members = []; sources = []
            for target in item['targets']:
                ref = repo.source(principal, {'document_id': target['document_id'],
                    'document_name': target['document_name'], 'generation': binding['generation'],
                    'coordinate': target['article_unit_id'], 'text': target['text'], 'version': binding['store_sha256']})
                sources.append(dict(repo.db.execute('SELECT * FROM sw_source WHERE id=?', (ref,)).fetchone()))
                members.append({'unit': unit, 'ref': ref, 'role': 'SOURCE', 'start': 0,
                                'stop': len(target['text']), 'reason': 'curated '+target['evidence_role']})
                targets.append({k: v for k, v in target.items() if k != 'text'} | {'source_ref': ref})
            path = {'contract': CONTRACT, 'import_id': import_id, 'package_sha256': fingerprint,
                    'case_id': case['case_id'], 'goal_revision': None,
                    'conditions': {'task': ' '.join(case['question'].split()), 'facts': [], 'source_category': 'all'},
                    'question_keys': list(dict.fromkeys(' '.join(q.split()) for q in [case['question'], *case.get('question_aliases', [])])),
                    'source_binding': binding, 'targets': targets, 'public_only': False,
                    'source_binding_policy': package.get('source_binding_policy', 'exact-source-v1'),
                    'origin': 'USER_CURATED_SOURCE_ENTRIES; NOT_A_COMPLETED_MODEL_ROUTE',
                    'execution': 'DIRECT_SOURCE_ENTRIES_THEN_CURRENT_SELECTION_AND_ASSESSMENT',
                    'legal_claim_reuse': False, 'discarded_exploration_replayed': False}
            value = {'id': unit, 'topic': case['topic'], 'question': case['question'],
                     'completeness': 'OPEN', 'unresolved': ['기준답변의 현재 적용·예외·충분성은 원문에서 다시 판단'],
                     'jurisdiction': 'UNKNOWN', 'applicable_time': 'UNKNOWN', 'members': members,
                     'claims': [], 'procedures': [],
                     'observations': [{'kind': 'ACTUAL_WORK_REFERENCE_NOT_APPROVED_INTERPRETATION',
                                       'text': case['reference_answer'], 'provenance': case['reference_provenance']}],
                     'documents': sorted({t['document_id'] for t in targets}),
                     'visibility': 'COMMON' if is_common_operator(principal) else 'PRIVATE',
                     'concept_status': 'DISCOVERY', 'input_cases': [],
                     'checklist': {'required_facts': False, 'sources': True, 'exceptions': False, 'corrections': True},
                     'core_evidence_route': path}
            repo.db.execute('INSERT INTO sw_unit VALUES(?,?,1)', (unit, scope))
            repo.db.execute('INSERT INTO sw_knowledge VALUES(?,1,?,?,?,?)', (unit, import_id, encoded(value), digest(value), 'OPEN'))
            repo.db.execute("INSERT INTO sw_lifecycle VALUES(?,1,'PUBLISHED')", (unit,))
            for member, source in zip(members, sources):
                repo.db.execute('INSERT INTO sw_member VALUES(?,1,?,?)', (unit, member['ref'], encoded(member)))
                repo.db.execute('INSERT INTO sw_dependency VALUES(?,1,?,?,?,?)',
                                (unit, source['id'], source['revision'], source['hash'], 'EVIDENCE'))
            repo._event(scope, unit, 'CURATED_SOURCE_ROUTE_REGISTERED',
                        {'case_id': case['case_id'], 'package_sha256': fingerprint, 'legal_claim_reuse': False})
            repo.enqueue(scope, 'projection', unit, 1)
            records.append({'case_id': case['case_id'], 'unit_id': unit, 'revision': 1,
                            'hash': digest(value), 'path_hash': digest(path), 'sources': len(targets)})
        receipt = {'schema_version': SCHEMA, 'import_id': import_id, 'package_id': package['package_id'],
                   'package_sha256': fingerprint, 'source_binding': binding, 'scope': scope,
                   'records': records, 'legal_claim_reuse': False, 'training_cases': True}
        receipt['source_binding_policy'] = package.get('source_binding_policy', 'exact-source-v1')
        if is_common_operator(principal):
            receipt.update(visibility=COMMON_VISIBILITY,
                           documents=sorted({t['document_id'] for item in cases for t in item['targets']}),
                           consumer_scope='all users; current document permissions still required')
        repo.db.execute('INSERT INTO sw_import VALUES(?,?)', (import_id, encoded(receipt)))
        store.check_unchanged()
        verify_package(repo, principal, receipt)
    return receipt


def current(repo, value, principal):
    path = value['core_evidence_route']
    if path.get('contract') != CONTRACT or path.get('legal_claim_reuse') is not False or value['claims'] or value['procedures']:
        raise MemoryError('curated source route cannot contain approved legal judgments')
    row = repo.db.execute('SELECT payload FROM sw_import WHERE id=?', (path['import_id'],)).fetchone()
    if not row:
        raise MemoryError('curated source import receipt missing')
    receipt = json.loads(row[0])
    common = value.get('visibility') == 'COMMON'
    expected_scope = common_scope_id() if common else repo.scope(principal)
    if common and (not principal.get('authenticated') or receipt.get('visibility') != COMMON_VISIBILITY):
        raise MemoryError('common source route visibility or authentication changed')
    if receipt['scope'] != expected_scope or receipt['package_sha256'] != path['package_sha256']:
        raise MemoryError('curated source receipt scope or package changed')
    records = [r for r in receipt['records'] if r['unit_id'] == value['id']]
    if len(records) != 1 or records[0]['hash'] != digest(value) or records[0]['path_hash'] != digest(path):
        raise MemoryError('curated source route not bound to import receipt')


def verify_package(repo, principal, receipt):
    for record in receipt['records']:
        value = repo.current(record['unit_id'], record['revision'], principal)
        if value['hash'] != record['hash']:
            raise MemoryError('imported unit changed')
    return {'verified': True, 'units': len(receipt['records'])}


def retire_package(repo, principal, receipt):
    """Append a retirement event instead of deleting imported records or sources."""
    if receipt['scope'] != repo.scope(principal):
        raise MemoryError('rollback scope mismatch')
    stored = repo.db.execute('SELECT payload FROM sw_import WHERE id=?', (receipt['import_id'],)).fetchone()
    if not stored:
        raise MemoryError('rollback import receipt missing')
    authority = json.loads(stored[0])
    if any(receipt.get(k) != v for k, v in authority.items()):
        raise MemoryError('rollback import receipt changed')
    with repo.transaction():
        for record in receipt['records']:
            status = repo.db.execute('SELECT status FROM sw_lifecycle WHERE unit=? AND revision=?',
                                     (record['unit_id'], record['revision'])).fetchone()
            if status and status[0] == 'PUBLISHED':
                repo.retire(record['unit_id'], record['revision'], principal, reason='curated package rollback '+receipt['import_id'])
    return {'retired': len(receipt['records']), 'records_preserved': True, 'import_id': receipt['import_id']}
