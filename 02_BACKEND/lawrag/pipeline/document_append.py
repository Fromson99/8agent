"""Append disjoint compact document indexes without rebuilding the base corpus.

Only new documents are structured/linked/tokenized before this operation. Existing
source, navigation and FTS rows are copied verbatim. New reference sources are
resolved against the union catalogue using the existing source checkpoints.
Audit is parent-linked (document-append-v1), not a counterfeit full-build audit.
Failures retain an unpublished attempt and error receipt; retry starts a new
attempt. Completed requests are idempotent, input drift is never repaired.
"""
from contextlib import closing
from copy import deepcopy
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
from semantic_runtime.contracts import sha, digest, write
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from semantic_runtime.unit_fulltext import UnitFulltextIndex

SCHEMA = 'document-append-v1'
SOURCE_TABLES = ('document', 'source_unit', 'block_payload')
NAV_LOCAL = ('source', 'definition', 'source_unit_map', 'document_frame', 'source_literal')
NAV_SHARED = ('term', 'edge', 'term_surface')


def read(path):
    return json.loads(Path(path).read_text())


def ro(path):
    path = Path(path).resolve()
    if path.is_symlink() or Path(str(path) + '-wal').exists():
        raise ValueError('Unbound SQLite input')
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def attach(db, path, name):
    db.execute('ATTACH DATABASE ? AS ' + name, (Path(path).resolve().as_uri() + '?mode=ro',))


def columns(db, table, namespace='main'):
    return [r[1] for r in db.execute(f'PRAGMA {namespace}.table_info("{table}")')]


def merge_rows(db, table, *, shared=False):
    """Only allow ignored inserts after proving every shared key's full payload."""
    cols = columns(db, table)
    if not cols or cols != columns(db, table, 'delta'):
        raise ValueError('Incompatible append table: ' + table)
    if shared:
        info = list(db.execute(f'PRAGMA table_info("{table}")'))
        pk = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
        # term_surface is a set with a composite UNIQUE index.
        pk = pk or (cols if table == 'term_surface' else [])
        if not pk:
            raise ValueError('No stable append key: ' + table)
        join = ' AND '.join(f'b."{c}" IS d."{c}"' for c in pk)
        changed = ' OR '.join(f'b."{c}" IS NOT d."{c}"' for c in cols)
        if table == 'term':
            for identifier, old, new in db.execute('SELECT b.id,b.json,d.json FROM term b JOIN delta.term d USING(id) WHERE b.json!=d.json'):
                old, new = json.loads(old), json.loads(new)
                # Representative labels depend on corpus occurrence order. Keep
                # the base label only when the delta label is an exact indexed
                # surface of the SAME concept; all other payload fields agree.
                if (not identifier.startswith('concept:') or
                    {k:v for k,v in old.items() if k != 'label'} != {k:v for k,v in new.items() if k != 'label'} or
                    not db.execute('SELECT 1 FROM delta.term_surface WHERE term_id=? AND text=?', (identifier, new.get('label'))).fetchone()):
                    raise ValueError('Shared catalogue collision: ' + table)
        elif db.execute(f'SELECT 1 FROM "{table}" b JOIN delta."{table}" d ON {join} WHERE {changed} LIMIT 1').fetchone():
            raise ValueError('Shared catalogue collision: ' + table)
    db.execute(('INSERT OR IGNORE' if shared else 'INSERT') + f' INTO "{table}" SELECT * FROM delta."{table}"')


def verify_base_rows(db, tables):
    """Copied rowids and payloads remain exact, including FTS pretokenized text."""
    for table in tables:
        cols = columns(db, table)
        changed = ' OR '.join(f'b."{c}" IS NOT m."{c}"' for c in cols)
        if db.execute(f'SELECT 1 FROM base."{table}" b LEFT JOIN main."{table}" m '
                      f'ON b.rowid=m.rowid WHERE m.rowid IS NULL OR {changed} LIMIT 1').fetchone():
            raise ValueError('Existing row changed: ' + table)


def pin_inputs(base, delta, delta_fulltext):
    result = {}
    for prefix, directory, files in (
        ('base', base, ('../result.json', 'manifest.json', 'store.sqlite', 'navigation/manifest.json', 'navigation/navigation.sqlite', 'fulltext/manifest.json', 'fulltext/units.sqlite')),
        ('delta', delta, ('../result.json', 'manifest.json', 'store.sqlite', 'navigation/manifest.json', 'navigation/navigation.sqlite')),
        ('delta_fulltext', delta_fulltext, ('manifest.json', 'units.sqlite')),
    ):
        result[prefix] = {'directory': str(directory), 'files': {name: sha(directory / name) for name in files}}
    return result


def glossary_identity(generation):
    result = read(generation.parent / 'result.json')
    if result.get('schema_version') == SCHEMA:
        parent = result['identity']['inputs']['base']
        verify_pins({'base': parent})
        return glossary_identity(Path(parent['directory']))
    return result['identity']['glossary']


def verify_pins(pins):
    for value in pins.values():
        for name, expected in value['files'].items():
            path = Path(value['directory']) / name
            if path.is_symlink() or sha(path) != expected:
                raise ValueError('Append parent/input changed: ' + str(path))


def check_inputs(base, delta, delta_fulltext):
    manifests = [read(p / 'manifest.json') for p in (base, delta)]
    navigation = [read(p / 'navigation/manifest.json') for p in (base, delta)]
    for directory, manifest in zip((base, delta), manifests):
        if manifest['schema_version'] != 'term-source-generation-v2' or 'search_selection' in manifest:
            raise ValueError('Append requires unfiltered compact-v2 generations')
        with closing(Store(directory)) as store:
            TermIndex(directory / 'navigation', store)
        if sha(directory / 'navigation/manifest.json') != manifest['navigation']['manifest_sha256']:
            raise ValueError('Append navigation binding mismatch')
    for key in ('schema_version', 'legal_sha256', 'reference_inputs_sha256', 'scope_contract'):
        if navigation[0].get(key) != navigation[1].get(key):
            raise ValueError('Incompatible navigation input: ' + key)
    if navigation[0]['schema_version'] != 'term-navigation-index-v7' or navigation[0].get('scope_contract'):
        raise ValueError('Append currently supports compact legacy reference scope only')
    # dictionary_sha256 is the document linkage DB, not the shared glossary DB.
    identities = [glossary_identity(p) for p in (base, delta)]
    for key in ('dictionary_sha256', 'knowledge', 'sense_review', 'review_contract'):
        if identities[0].get(key) != identities[1].get(key):
            raise ValueError('Append glossary differs: ' + key)
    UnitFulltextIndex(base / 'fulltext', navigation[0])
    UnitFulltextIndex(delta_fulltext, navigation[1])
    fm = [read(p / 'manifest.json') for p in (base / 'fulltext', delta_fulltext)]
    for key in ('tokenizer', 'tokenizer_code_sha256', 'ranking', 'granularity', 'descendant_text_included'):
        if fm[0].get(key) != fm[1].get(key):
            raise ValueError('Append fulltext recipe differs: ' + key)
    with closing(ro(base / 'store.sqlite')) as db:
        attach(db, delta / 'store.sqlite', 'delta')
        if db.execute('SELECT 1 FROM document JOIN delta.document USING(document_id) LIMIT 1').fetchone():
            raise ValueError('Append document IDs overlap; replacement requires explicit new selection')
        ids = [r[0] for r in db.execute('SELECT document_id FROM delta.document ORDER BY document_id')]
        if not ids:
            raise ValueError('Empty append')
        for namespace, ft in [('main', fm[0]), ('delta', fm[1])]:
            actual = {r[0] for r in db.execute(f'SELECT document_id FROM {namespace}.document')}
            if actual != set(ft['scope']['document_version_ids']):
                raise ValueError('Append requires complete fulltext scope')
    return manifests, navigation, fm, ids


def combine(base, delta, delta_fulltext, attempt, manifests, navigation, fts, ids):
    generation = attempt / 'generation'
    generation.mkdir()
    for relative in ('store.sqlite', 'navigation/navigation.sqlite', 'fulltext/units.sqlite'):
        target = generation / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / relative, target)  # Never hardlink a mutable DB.
    # Immutable, hash-bound glossary assets are shared; readers never rebuild them.
    shutil.copytree(base / 'glossary', generation / 'glossary', copy_function=os.link)
    with closing(sqlite3.connect(generation / 'store.sqlite')) as db:
        attach(db, delta / 'store.sqlite', 'delta')
        attach(db, base / 'store.sqlite', 'base')
        for table in SOURCE_TABLES:
            merge_rows(db, table)
        db.commit()
        verify_base_rows(db, SOURCE_TABLES)
        counts = {t: db.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in ('document', 'source_unit', 'source_block')}
    print('APPEND source copied; new documents=' + str(len(ids)), flush=True)
    with closing(sqlite3.connect(generation / 'navigation/navigation.sqlite')) as db:
        attach(db, delta / 'navigation/navigation.sqlite', 'delta')
        attach(db, base / 'navigation/navigation.sqlite', 'base')
        if db.execute("SELECT count(*) FROM source WHERE id NOT IN (SELECT item FROM navigation_checkpoint WHERE stage='reference-source')").fetchone()[0]:
            raise ValueError('Base reference checkpoints incomplete')
        for table in NAV_SHARED:
            merge_rows(db, table, shared=True)
        for table in NAV_LOCAL:
            merge_rows(db, table)
        db.execute('INSERT INTO occurrence_keys SELECT t.rowid,s.rowid FROM delta.occurrence o '
                   'JOIN main.term t ON t.id=o.term_id JOIN main.source s ON s.id=o.source_id')
        db.execute('INSERT INTO navigation_checkpoint SELECT * FROM delta.navigation_checkpoint WHERE stage="document"')
        for term, n in db.execute('SELECT term_id,n FROM delta.term_stats'):
            db.execute('INSERT INTO term_stats VALUES (?,?) ON CONFLICT(term_id) DO UPDATE SET n=n+excluded.n', (term, n))
        db.commit()
        from semantic_runtime.term_references import compile_references, load_reference_inputs
        aliases, delegations, ref_pins = load_reference_inputs()
        if ref_pins != navigation[0]['reference_inputs_sha256']:
            raise ValueError('Reference catalogue changed since parent build')
        # Only sources without a reference-source checkpoint are investigated.
        total_refs, unresolved = compile_references(db, aliases, delegations)
        db.execute("INSERT INTO reference_witness_count SELECT json_extract(json,'$.source_id'),"
            "json_extract(json,'$.block_id'),json_extract(json,'$.source_text_sha256'),count(*) "
            "FROM reference_payload WHERE document_id IN (SELECT document_id FROM delta.document_frame) "
            "AND json_extract(json,'$.source_text_sha256') IS NOT NULL GROUP BY 1,2,3")
        # Construction-stage checkpoints describe the parents; union completion is
        # recorded only in this append receipt, never as a full glossary rebuild.
        db.execute("DELETE FROM navigation_checkpoint WHERE stage NOT IN ('document','reference-source','reference-counts')")
        db.commit()
        verify_base_rows(db, NAV_LOCAL + ('term', 'edge', 'reference_payload', 'reference_body', 'reference_target', 'reference_candidate', 'reference_end', 'reference_candidate_end'))
        if db.execute('SELECT * FROM base.occurrence_keys EXCEPT SELECT * FROM main.occurrence_keys LIMIT 1').fetchone():
            raise ValueError('Existing occurrences changed')
        nav_counts = {t: db.execute('SELECT count(*) FROM ' + t).fetchone()[0]
                      for t in ('term', 'edge', 'source', 'occurrence', 'definition', 'reference')}
    print('APPEND navigation copied; new reference sources resolved', flush=True)
    with closing(sqlite3.connect(generation / 'fulltext/units.sqlite')) as db:
        attach(db, delta_fulltext / 'units.sqlite', 'delta')
        attach(db, base / 'fulltext/units.sqlite', 'base')
        merge_rows(db, 'unit')
        db.execute('INSERT INTO unit_fts(key,body) SELECT key,body FROM delta.unit_fts')
        db.commit()
        verify_base_rows(db, ('unit', 'unit_fts'))
        db.execute("INSERT INTO unit_fts(unit_fts) VALUES('integrity-check')")
        db.commit()
    for rel in ('store.sqlite', 'navigation/navigation.sqlite', 'fulltext/units.sqlite'):
        with closing(ro(generation / rel)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Append integrity failed: ' + rel)
    return generation, counts, nav_counts, unresolved


def verify(output, *, serving=True):
    output = Path(output).resolve()
    result = read(output / 'result.json')
    if result.get('schema_version') != SCHEMA:
        raise ValueError('Not a document append receipt')
    verify_pins(result['identity']['inputs'])
    for relative, expected in result['files'].items():
        if sha(output / relative) != expected:
            raise ValueError('Append output drift: ' + relative)
    if serving:
        from .term_serving_bundle import verify_assets
        verify_assets(output / 'generation')
    return result


def append(base, delta, delta_fulltext, output):
    base, delta, delta_fulltext, output = [Path(p).resolve() for p in (base, delta, delta_fulltext, output)]
    if any(output == p or output in p.parents or p in output.parents for p in (base, delta, delta_fulltext)):
        raise ValueError('Append output overlaps an input')
    output.parent.mkdir(parents=True, exist_ok=True)
    with (output.parent / ('.' + output.name + '.lock')).open('a+') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pins = pin_inputs(base, delta, delta_fulltext)
        identity = {'inputs': pins, 'builder_sha256': sha(__file__)}
        if output.exists():
            if read(output / 'result.json')['identity'] != identity:
                raise ValueError('Completed append identity changed; choose a new output')
            return verify(output)
        m, n, ft, ids = check_inputs(base, delta, delta_fulltext)
        attempt = output.parent / ('.' + output.name + '.attempt-' + str(time.time_ns()))
        attempt.mkdir()
        write(attempt / 'identity.json', identity)
        started = time.monotonic()
        try:
            generation, counts, nav_counts, unresolved = combine(base, delta, delta_fulltext, attempt, m, n, ft, ids)
            audit = {'schema_version': SCHEMA, 'parents': pins, 'added_document_ids': ids,
                'base_rows_preserved': True, 'retokenized_base_documents': 0,
                'new_document_references': 'resolved against union; old source checkpoints preserved',
                'existing_unresolved_references': 'unchanged; no retroactive resolution',
                'shared_concept_labels': 'retain base representative; add exact delta surfaces; reject any other payload difference',
                'parent_audits': [{k: v for k, v in source.items() if k in ('source_storage', 'append_lineage')}
                                  | {'navigation_storage': nav.get('storage')} for source, nav in zip(m, n)],
                'store_sha256': sha(generation / 'store.sqlite'),
                'navigation_index_sha256': sha(generation / 'navigation/navigation.sqlite'),
                'fulltext_index_sha256': sha(generation / 'fulltext/units.sqlite')}
            write(attempt / 'audit/append.json', audit)
            sm = {k: deepcopy(v) for k, v in m[0].items() if k not in
                  ('source_storage', 'source_store_sha256', 'navigation', 'fulltext', 'scope', 'fulltext_derivation')}
            sm.update(generation_id='term-append-' + digest(identity)[:20], data_status='DRAFT', quality_certified=False,
                export_allowed=False, store_sha256=audit['store_sha256'], counts=counts,
                scope={'document_version_ids': sorted(set(ft[0]['scope']['document_version_ids']) | set(ids))},
                append_lineage={'schema_version': SCHEMA, 'audit_manifest_sha256': sha(attempt / 'audit/append.json')})
            nm = {k: deepcopy(v) for k, v in n[0].items() if k not in ('storage', 'linkage', 'dictionary_sha256')}
            nm.update(generation_id=sm['generation_id'], source_store_sha256=sm['store_sha256'],
                source_manifest_sha256=digest(sm), index_sha256=audit['navigation_index_sha256'],
                counts=nav_counts, document_count=counts['document'], unresolved_references=unresolved,
                rejected_definitions=n[0]['rejected_definitions'] + n[1]['rejected_definitions'],
                append_lineage=sm['append_lineage'])
            write(generation / 'navigation/manifest.json', nm)
            sm['navigation'] = {'path': 'navigation', 'manifest_sha256': sha(generation / 'navigation/manifest.json')}
            write(attempt / 'source-stage.json', sm)
            fm = deepcopy(ft[0])
            fm.update(generation_id=sm['generation_id'], source_store_sha256=sm['store_sha256'],
                navigation_index_sha256=nm['index_sha256'], index_sha256=audit['fulltext_index_sha256'],
                source_manifest_sha256=sha(attempt / 'source-stage.json'), navigation_manifest_sha256=sm['navigation']['manifest_sha256'],
                build_seconds=time.monotonic() - started, builder_sha256=sha(__file__), append_lineage=sm['append_lineage'],
                scope={k: sorted(set(ft[0]['scope'][k]) | set(ft[1]['scope'][k])) for k in ft[0]['scope']},
                counts={k: ft[0]['counts'][k] + ft[1]['counts'][k] for k in ft[0]['counts']})
            write(generation / 'fulltext/manifest.json', fm)
            sm['fulltext'] = {'path': 'fulltext', 'manifest_sha256': sha(generation / 'fulltext/manifest.json'),
                              'navigation_index_sha256': nm['index_sha256']}
            write(generation / 'manifest.json', sm)
            result = {'schema_version': SCHEMA, 'identity': identity, 'generation': 'generation',
                'generation_id': sm['generation_id'], 'manifest_sha256': sha(generation / 'manifest.json'),
                'counts': counts, 'added_document_ids': ids, 'base_rows_preserved': True,
                'retokenized_base_documents': 0, 'model_calls': 0, 'activated': False,
                'files': {str(p.relative_to(attempt)): sha(p) for p in attempt.rglob('*') if p.is_file()}}
            write(attempt / 'result.json', result)
            verify(attempt)
            os.rename(attempt, output)
            return result
        except BaseException as error:
            write(attempt / 'failure.json', {'status': 'failed', 'error_type': type(error).__name__,
                  'message': str(error), 'seconds': time.monotonic() - started, 'published': False,
                  'recovery': 'same immutable inputs; new attempt; completed output is never overwritten'})
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('append', 'verify-append'))
    parser.add_argument('--base-generation', type=Path)
    parser.add_argument('--delta-generation', type=Path)
    parser.add_argument('--delta-fulltext', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.action == 'append':
        if not all((args.base_generation, args.delta_generation, args.delta_fulltext)):
            parser.error('append requires base, delta and delta-fulltext')
        result = append(args.base_generation, args.delta_generation, args.delta_fulltext, args.output)
    else:
        result = verify(args.output)
    print(json.dumps({k: result[k] for k in ('schema_version', 'generation_id', 'counts', 'added_document_ids',
                                            'base_rows_preserved', 'retokenized_base_documents', 'activated')}, ensure_ascii=False))
    return 0
