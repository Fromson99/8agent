"""Explicit Oracle export policy; original SQLite files and logical rows stay immutable."""
import copy
import re
import sqlite3

from gold_io import Stop, digest
from semantic_runtime.oracle_dp_assets import checked_path
from lawrag.pipeline.oracle_query_publish import _kind

POLICY = 'g19-reduced-search-v1'
DIRECTORY_SUFFIX = '-reduced-r4'
VIEWS = {
    'occurrence': 'CREATE VIEW occurrence AS SELECT t.id AS term_id,s.id AS source_id FROM occurrence_keys o JOIN term t ON t.rowid=o.term_key JOIN source s ON s.rowid=o.source_key',
    'entry_corpus_link': 'CREATE VIEW entry_corpus_link AS SELECT e.id AS entry_id,o.*,d.name AS document_name,d.source_sha256 FROM entry e JOIN occurrence o ON o.key=e.key JOIN corpus_document d ON d.document_id=o.document_id',
    'entry_definition_link': "CREATE VIEW entry_definition_link AS SELECT e.id AS entry_id,d.id AS definition_id,CASE WHEN e.id=d.id THEN 'SOURCE_DEFINITION' ELSE 'LABEL_CANDIDATE' END AS match_kind FROM entry e JOIN corpus_definition d ON d.key=e.key",
}


def tokens(sql):
    # Whitespace outside literals is irrelevant; quoted text/case is preserved.
    return re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[^\s]", sql.rstrip().rstrip(';'))


def plan(root, source, query, paths):
    """Reuse exact prepared per-kind counts/chains; never rescan the removed views."""
    if 'projection_policy' in query:
        raise Stop('REDUCED_PARENT_ALREADY_CHANGED')
    manifest = source['source_manifest']
    nav = manifest['navigation']['path'] + '/navigation.sqlite'
    dictionary = manifest['glossary']['dictionary']
    if nav == dictionary or not {nav, dictionary} <= set(paths):
        raise Stop('REDUCED_ASSET_BINDING')
    targets = {nav: ('occurrence_keys',), dictionary: ('entry_corpus_link', 'entry_definition_link')}
    required = {nav: ('term', 'source', 'occurrence'),
                dictionary: ('entry', 'occurrence', 'corpus_document', 'corpus_definition')}
    removed = {}
    for relative, names in targets.items():
        path = checked_path(root, relative)
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            catalogue = {r[0]: (r[1], r[2]) for r in db.execute(
                "SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view')")}
            for name in (*required[relative], *names):
                kind = _kind(relative, name)
                spec = query['tables'].get(kind, {})
                if (name not in catalogue or spec.get('asset') != relative or spec.get('table') != name
                        or spec.get('storage') != catalogue[name][0]):
                    raise Stop('REDUCED_SCHEMA_BINDING:' + name)
                columns = [r[1] for r in db.execute('PRAGMA table_info("' + name + '")')]
                if set(spec.get('columns', {})) != set(columns):
                    raise Stop('REDUCED_COLUMNS_CHANGED:' + name)
                if name in names and name in VIEWS:
                    if catalogue[name][0] != 'view' or tokens(catalogue[name][1]) != tokens(VIEWS[name]):
                        raise Stop('REDUCED_VIEW_CHANGED:' + name)
            if relative == nav:
                if (catalogue['occurrence_keys'][0] != 'table'
                        or tokens(catalogue['occurrence'][1]) != tokens(VIEWS['occurrence'])
                        or set(query['tables'][_kind(relative, 'occurrence_keys')]['columns']) != {'term_key', 'source_key'}):
                    raise Stop('REDUCED_NAVIGATION_CHANGED')
            for name in names:
                kind = _kind(relative, name)
                removed[kind] = copy.deepcopy(query['tables'][kind])
        finally:
            db.close()
    result = copy.deepcopy(query)
    result['tables'] = {kind: spec for kind, spec in result['tables'].items() if kind not in removed}
    counts = [v['rows'] for v in query['tables'].values()]
    if any(type(n) is not int or n < 0 for n in counts):
        raise Stop('REDUCED_PREPARED_COUNT')
    result['projection_policy'] = {
        'schema_version': POLICY, 'parent_query_release_id': digest(query),
        'excluded_tables': removed, 'original_rows': sum(counts),
        'retained_rows': sum(v['rows'] for v in result['tables'].values()),
        'excluded_rows': sum(v['rows'] for v in removed.values()),
    }
    return result


def exclusions(query, relative):
    policy = query.get('projection_policy', {})
    if policy.get('schema_version') != POLICY:
        raise Stop('REDUCED_POLICY_REQUIRED')
    return tuple(sorted(spec['table'] for spec in policy['excluded_tables'].values() if spec['asset'] == relative))
