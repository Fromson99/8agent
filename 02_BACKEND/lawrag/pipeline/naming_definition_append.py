"""Append source-witnessed naming hints to an existing navigation generation.

No parsing, embedding, tokenization, model calls, reference resolution or activation.
Existing references are witnesses, not a licence to infer legal equivalence/scope.
"""
from collections import defaultdict
from contextlib import closing
from copy import deepcopy
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from semantic_runtime.contracts import digest, sha, write
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from semantic_runtime.term_links import normalized

POLICY = 'explicit-reference-naming-v1'
SCHEMA = 'naming-definition-append-v1'
NAMING = re.compile(r'[（(]\s*이하\s+(?:(?P<scope>(?:이|같은)\s*(?:조|항|절|장|편|법|영|규칙|규정|세칙)에서는?)\s*)?'
                    r'(?P<term>[^()（）\n]{1,100}?)\s*(?:이라|라)\s*한다\.?\s*[)）]')
FRAME = re.compile(r'\s*(?:에\s*따른|에서\s*정하는)\s*[^()（）,，;；.。\n]{1,100}')
TRIM = ' \t\r\n\\\"\'“”‘’「」『』'


def read(path):
    return json.loads(Path(path).read_text())


def ro(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def candidates(text, references):
    """Pair each naming clause with ONE adjacent reference; never cross commas."""
    previous_end = 0
    for match in NAMING.finditer(text):
        start, end = match.span('term')
        while start < end and text[start] in TRIM:
            start += 1
        while end > start and text[end - 1] in TRIM:
            end -= 1
        if start == end:
            continue
        near = [r for r in references if r['mention_end'] <= match.start()
                and FRAME.fullmatch(text[r['mention_end']:match.start()])]
        # Document-title abbreviations and unrelated parentheticals are not this patch.
        if not near:
            previous_end = match.end()
            continue
        boundary = max(previous_end, *(text.rfind(c, previous_end, match.start()) + 1 for c in ',，;；。\n'))
        clause_refs = [r for r in references if boundary <= r['mention_start'] < match.start()]
        reason = None
        if len(near) != 1 or len(clause_refs) != 1:
            reason = 'MULTIPLE_REFERENCES_IN_NAMING_CLAUSE'
        if any(c in text[start:end] for c in '\\\"\'“”‘’「」『』'):
            reason = 'COMPLEX_NAME_OR_SCOPE_REQUIRES_REVIEW'
        ref = near[0]
        if reason is None and (not ref.get('resolution', '').startswith('EXACT_')
                               or ref.get('resolution_basis', 'deterministic') != 'deterministic'
                               or len(ref.get('targets', [])) != 1):
            reason = 'REFERENCE_NOT_UNIQUELY_RESOLVED'
        scopes = ([{'text': match['scope'], 'start': match.start('scope'), 'end': match.end('scope'),
                    'applies_to': 'UNREVIEWED'}] if match['scope'] else [])
        yield {'term': text[start:end], 'term_start': start, 'term_end': end, 'scope_hint': scopes,
               'definition_start': ref['mention_start'], 'definition_end': match.end(),
               'reference': ref, 'hold_reason': reason}
        previous_end = match.end()


def append_rows(db, store, *, document_ids=None):
    """Only append definitions and typed links. A transaction belongs to caller."""
    db.execute('CREATE TABLE IF NOT EXISTS definition_reference('
               'definition_id TEXT,reference_id TEXT,PRIMARY KEY(definition_id,reference_id))')
    db.execute('CREATE INDEX IF NOT EXISTS definition_reference_reverse ON definition_reference(reference_id,definition_id)')
    db.execute("CREATE INDEX IF NOT EXISTS definition_key ON definition(json_extract(json,'$.key'),document_id)")
    known = {r[0] for r in store.db.execute('SELECT document_id FROM document')}
    selected = known if document_ids is None else set(document_ids)
    if not selected or not selected <= known:
        raise ValueError('Unknown or empty naming patch document scope')
    groups = defaultdict(list)
    excluded_official_delegations = 0
    # Query the existing reference witness bodies, not every source document/file.
    for raw, in db.execute("SELECT json FROM reference WHERE instr(json_extract(json,'$.source_text'),'이하')>0 ORDER BY id"):
        ref = json.loads(raw)
        # API-sourced delegation edges intentionally have no inline mention span.
        # They are a different evidence type, never input to a naming-clause parser.
        if (ref.get('resolution') == 'OFFICIAL_DELEGATION'
                and 'official_delegation_lawgokr' in ref.get('origins', [])
                and ref.get('mention_start') == ref.get('mention_end') == 0
                and ref.get('mention_text') == ''):
            excluded_official_delegations += 1
            continue
        if ref['document_id'] in selected:
            groups[(ref['source_id'], ref['block_id'])].append(ref)
    accepted, held = [], []
    existing = {(d['document_id'], str(d['block_id']), d['term_start'], d['term_end'],
                 d['source_text_sha256']): d for raw, in db.execute('SELECT json FROM definition')
                for d in [json.loads(raw)]}
    for (sid, bid), refs in sorted(groups.items()):
        row = db.execute('SELECT json FROM source WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise ValueError('Naming reference source missing')
        source = json.loads(row[0])
        did = source['document_id']
        block = store.source(did, bid)
        text, body_hash = block['text'], text_sha(block['text'])
        artifact = store.db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?', (did,)).fetchone()[0]
        if (artifact != source['source_artifact_sha256'] or
                not any(str(b['block_id']) == str(bid) and b['text'] == text for b in source['blocks'])):
            raise ValueError('Naming source provenance mismatch')
        for ref in refs:
            start, end = ref['mention_start'], ref['mention_end']
            if (ref['document_id'] != did or ref['source_text'] != text or
                    ref['source_text_sha256'] != body_hash or not 0 <= start < end <= len(text) or
                    text[start:end] != ref['mention_text']):
                raise ValueError('Naming reference witness/span/hash mismatch')
        for candidate in candidates(text, refs):
            ref = candidate['reference']
            record = {k: v for k, v in candidate.items() if k != 'reference'}
            record.update(source_id=sid, document_id=did, block_id=str(bid),
                          source_text_sha256=body_hash, reference_id=ref['id'])
            if candidate['hold_reason']:
                held.append(record)
                continue
            target = ref['targets'][0]
            target_row = db.execute('SELECT json FROM source WHERE id=?', (target['source_id'],)).fetchone()
            if target_row is None:
                held.append({**record, 'hold_reason': 'TARGET_SOURCE_MISSING'})
                continue
            target_source = json.loads(target_row[0])
            target_blocks = {str(b['block_id']) for b in target_source['blocks']}
            if (target_source['document_id'] not in known or
                    not set(map(str, target.get('block_ids', []))) <= target_blocks):
                raise ValueError('Naming target provenance mismatch')
            uid = target.get('unit_id')
            if uid is not None and not store.db.execute('SELECT 1 FROM source_unit WHERE document_id=? AND unit_id=?',
                    (target_source['document_id'], str(uid))).fetchone():
                raise ValueError('Naming target unit missing')
            key = normalized(candidate['term'])
            coord = (did, str(bid), candidate['term_start'], candidate['term_end'], body_hash)
            old = existing.get(coord)
            identifier = old['id'] if old else 'naming-definition:' + digest([POLICY, *coord])
            d = {'id': identifier, 'key': key, 'label': candidate['term'], 'document_id': did,
                 'block_id': str(bid), 'unit_id': block['unit_id'],
                 **{k: candidate[k] for k in ('term_start', 'term_end', 'definition_start', 'definition_end')},
                 'source_text': text, 'source_text_sha256': body_hash,
                 'definition_status': 'EXPLICIT_NAMING_HINT',
                 'scope_status': 'EXPLICIT_SCOPE_HINT' if candidate['scope_hint'] else 'UNRESOLVED',
                 'scope_hint': candidate['scope_hint'], 'location': source.get('location', []),
                 'reference_hints': [{'reference_id': ref['id'], 'text': ref['mention_text'],
                                      'start': ref['mention_start'], 'end': ref['mention_end'],
                                      'document_name': ref.get('document_name_hint'),
                                      'article_surface': ref['locator'], 'resolution': ref['resolution']}],
                 'term_ids': [r[0] for r in db.execute('SELECT DISTINCT term_id FROM term_surface WHERE key=? ORDER BY term_id', (key,))],
                 'source_id': sid, 'document_name': source['document_name'],
                 'source_artifact_sha256': artifact, 'origin': POLICY,
                 'match_kind': 'LABEL_CANDIDATE', 'verification': 'EXACT_BLOCK_AND_HASH',
                 'canonical_approval': False}
            if not old:
                db.execute('INSERT INTO definition VALUES (?,?,?)', (identifier, did, json.dumps(d, ensure_ascii=False)))
                existing[coord] = d
            elif old['key'] != key or old['source_id'] != sid:
                raise ValueError('Existing naming definition conflicts with source witness')
            linked = db.execute('INSERT OR IGNORE INTO definition_reference VALUES (?,?)', (identifier, ref['id'])).rowcount
            accepted.append({**record, 'definition_id': identifier, 'definition_added': old is None,
                             'link_added': bool(linked), 'target': target})
    return {'policy': POLICY, 'document_scope_count': len(selected), 'witness_blocks_scanned': len(groups),
            'excluded_official_delegations': excluded_official_delegations,
            'definitions_added': sum(r['definition_added'] for r in accepted),
            'links_added': sum(r['link_added'] for r in accepted), 'accepted': accepted, 'held': held}


def preserved_rows(db, parent):
    """Prove every preexisting row/schema remains; only definition allows new rows."""
    db.execute('ATTACH DATABASE ? AS base', (Path(parent).as_uri() + '?mode=ro',))
    for name, sql in db.execute("SELECT name,sql FROM base.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        actual = db.execute('SELECT sql FROM main.sqlite_master WHERE name=?', (name,)).fetchone()
        if actual is None or actual[0] != sql:
            raise ValueError('Parent table schema changed: ' + name)
        safe = '"' + name.replace('"', '""') + '"'
        info = list(db.execute(f'PRAGMA main.table_info({safe})'))
        columns = [r[1] for r in info]
        keys = [r[1] for r in sorted(info, key=lambda r:r[5]) if r[5]] if re.search(r'WITHOUT\s+ROWID', sql, re.I) else ['rowid']
        join = ' AND '.join('b."' + c.replace('"', '""') + '"=m."' + c.replace('"', '""') + '"' for c in keys)
        missing = 'm."' + keys[0].replace('"', '""') + '" IS NULL'
        difference = ' OR '.join('b."' + c.replace('"', '""') + '" IS NOT m."' + c.replace('"', '""') + '"' for c in columns)
        if db.execute(f'SELECT 1 FROM base.{safe} b LEFT JOIN main.{safe} m ON {join} '
                      f'WHERE {missing} OR {difference} LIMIT 1').fetchone():
            raise ValueError('Parent rows changed: ' + name)
        if name not in {'definition', 'definition_reference'} and (db.execute(f'SELECT count(*) FROM main.{safe}').fetchone()[0]
                != db.execute(f'SELECT count(*) FROM base.{safe}').fetchone()[0]):
            raise ValueError('Unexpected new parent rows: ' + name)


def shared_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def input_pins(base):
    manifest = read(base / 'manifest.json')
    files = ['manifest.json', 'store.sqlite', manifest['navigation']['path'] + '/manifest.json',
             manifest['navigation']['path'] + '/navigation.sqlite']
    if manifest.get('fulltext'):
        files.extend([manifest['fulltext']['path'] + '/manifest.json', manifest['fulltext']['path'] + '/units.sqlite'])
    result = {}
    for name in files:
        path = base / name
        path.resolve().relative_to(base)
        if path.is_symlink() or Path(str(path) + '-wal').exists():
            raise ValueError('Unsealed naming patch input: ' + name)
        result[name] = sha(path)
    return result


def verify(output):
    output = Path(output).resolve()
    result = read(output / 'result.json')
    if result.get('schema_version') != SCHEMA:
        raise ValueError('Unknown naming patch receipt')
    base = Path(result['identity']['base_generation'])
    if input_pins(base) != result['identity']['input_pins']:
        raise ValueError('Naming patch parent drift')
    for path, expected in result['files'].items():
        if sha(output / path) != expected:
            raise ValueError('Naming patch output drift: ' + path)
    from semantic_runtime.navigation_storage import verify_build
    from .term_serving_bundle import verify_assets
    generation = output / 'generation'
    if result.get('navigation_audit'):
        verify_build(output)
    elif read(generation / 'manifest.json').get('glossary'):
        verify_assets(generation)
    else:
        with closing(Store(generation)) as store:
            TermIndex(generation / 'navigation', store)
    return result


def augment(base, output, *, document_ids=None):
    base, output = Path(base).resolve(), Path(output).resolve()
    if output == base or output.is_relative_to(base) or base.is_relative_to(output):
        raise ValueError('Naming patch requires a separate output directory')
    pins = input_pins(base)
    identity = {'base_generation': str(base), 'input_pins': pins, 'policy': POLICY,
                'document_ids': sorted(set(document_ids)) if document_ids is not None else None,
                'compiler_sha256': sha(__file__)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with (output.parent / ('.' + output.name + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if output.exists():
            result = verify(output)
            if result['identity'] != identity:
                raise ValueError('Naming patch identity changed; use a new output')
            return result
        manifest = read(base / 'manifest.json')
        nav_relative = Path(manifest['navigation']['path'])
        with closing(Store(base)) as store:
            if store.selection.state is not None:
                raise ValueError('Copying an active search exclusion requires an explicit selection migration')
            index = TermIndex(base / nav_relative, store)
            nav_manifest = deepcopy(index.manifest)
        if sha(base / nav_relative / 'manifest.json') != manifest['navigation']['manifest_sha256']:
            raise ValueError('Parent navigation manifest mismatch')
        if manifest.get('fulltext'):
            from semantic_runtime.fulltext import open_index
            ft = base / manifest['fulltext']['path']
            if sha(ft / 'manifest.json') != manifest['fulltext']['manifest_sha256']:
                raise ValueError('Parent fulltext manifest mismatch')
            open_index(ft, nav_manifest)
        attempt = Path(tempfile.mkdtemp(prefix='.' + output.name + '.attempt-', dir=output.parent))
        try:
            generation = attempt / 'generation'
            shutil.copytree(base, generation, copy_function=shared_copy)
            # Unlink every mutable hardlink before opening/writing it.
            dbfile = generation / nav_relative / 'navigation.sqlite'
            dbfile.unlink()
            shutil.copyfile(base / nav_relative / 'navigation.sqlite', dbfile)
            with closing(Store(base)) as store, closing(sqlite3.connect(dbfile)) as db:
                with db:
                    delta = append_rows(db, store, document_ids=document_ids)
                preserved_rows(db, base / nav_relative / 'navigation.sqlite')
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Naming patch SQLite integrity failure')
                nav_manifest['counts']['definition'] = db.execute('SELECT count(*) FROM definition').fetchone()[0]
                runtime_tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            write(attempt / 'delta.json', delta)
            nav_manifest['index_sha256'] = sha(dbfile)
            receipt = {'schema_version': SCHEMA, 'identity': identity,
                       'parent_index_sha256': index.manifest['index_sha256'],
                       'output_index_sha256': nav_manifest['index_sha256'],
                       'delta_sha256': sha(attempt / 'delta.json'),
                       'definitions_added': delta['definitions_added'], 'links_added': delta['links_added'],
                       'held_count': len(delta['held']), 'canonical_approval': False}
            receipt_file = generation / nav_relative / 'naming-definition-append.json'
            if receipt_file.exists():
                receipt_file.unlink()
            write(receipt_file, receipt)
            nav_manifest['naming_definition_append'] = {'receipt_sha256': sha(receipt_file), **receipt}
            audit_binding = None
            if nav_manifest.get('storage'):
                from semantic_runtime.navigation_storage import verify_audit
                parent_audit = base.parent / 'audit/navigation'
                old_audit = verify_audit(parent_audit,
                    expected_manifest_sha256=nav_manifest['storage']['audit_manifest_sha256'],
                    expected_index_sha256=index.manifest['index_sha256'])
                audit = attempt / 'audit/navigation'
                shutil.copytree(parent_audit, audit, copy_function=shared_copy)
                value = {**old_audit, 'serving_index_sha256': nav_manifest['index_sha256'],
                         'serving_index_bytes': dbfile.stat().st_size, 'runtime_tables': sorted(runtime_tables),
                         'parent_audit_manifest_sha256': sha(parent_audit / 'manifest.json'),
                         'naming_definition_append': {'receipt_sha256': sha(receipt_file),
                                                     'delta_sha256': sha(attempt / 'delta.json')}}
                (audit / 'manifest.json').unlink()
                write(audit / 'manifest.json', value)
                nav_manifest['storage']['audit_manifest_sha256'] = sha(audit / 'manifest.json')
                audit_binding = {'path': 'audit/navigation', 'manifest_sha256': sha(audit / 'manifest.json')}
            (generation / nav_relative / 'manifest.json').unlink()
            write(generation / nav_relative / 'manifest.json', nav_manifest)
            if manifest.get('fulltext'):
                path = generation / manifest['fulltext']['path'] / 'manifest.json'
                ft_manifest = read(path)
                ft_manifest['navigation_index_sha256'] = nav_manifest['index_sha256']
                path.unlink()
                write(path, ft_manifest)
                manifest['fulltext'].update(manifest_sha256=sha(path), navigation_index_sha256=nav_manifest['index_sha256'])
            manifest['navigation']['manifest_sha256'] = sha(generation / nav_relative / 'manifest.json')
            (generation / 'manifest.json').unlink()
            write(generation / 'manifest.json', manifest)
            files = {str(p.relative_to(attempt)): sha(p) for p in
                     [attempt / 'delta.json', receipt_file, generation / 'manifest.json',
                      generation / nav_relative / 'manifest.json', dbfile]}
            result = {'schema_version': SCHEMA, 'identity': identity, 'files': files,
                      'manifest_sha256': sha(generation / 'manifest.json'), 'navigation_audit': audit_binding,
                      'definitions_added': delta['definitions_added'], 'links_added': delta['links_added'],
                      'held_count': len(delta['held']), 'base_rows_preserved': True,
                      'source_reparsed': 0, 'documents_retokenized': 0, 'model_calls': 0,
                      'activated': False, 'quality_certified': False}
            write(attempt / 'result.json', result)
            verify(attempt)
            if input_pins(base) != pins:
                raise ValueError('Naming patch parent changed during publication')
            os.rename(attempt, output)
            return result
        except BaseException as exc:
            write(attempt / 'failure.json', {'published': False, 'identity': identity,
                    'error_type': type(exc).__name__, 'error': str(exc)})
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['augment-definitions', 'verify-definitions'])
    parser.add_argument('--base-generation', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--document-id', action='append')
    args = parser.parse_args(argv)
    if args.action == 'verify-definitions':
        result = verify(args.output)
    else:
        if args.base_generation is None:
            parser.error('--base-generation is required')
        result = augment(args.base_generation, args.output, document_ids=args.document_id)
    print(json.dumps({k: result[k] for k in ('schema_version', 'definitions_added', 'links_added',
          'held_count', 'base_rows_preserved', 'documents_retokenized', 'model_calls', 'activated')}, ensure_ascii=False))
    return 0
