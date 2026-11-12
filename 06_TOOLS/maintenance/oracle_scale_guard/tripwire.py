"""Record Oracle read volume of the code under test against a scaled row budget.

Field Oracle stops one enumeration at 10,000 rows (oracle_query_matcher.pages
QUERY_NAV_BUDGET, oracle_query_db._pages QUERY_SQL_RESULT_BUDGET). The guard
fixture is ~250x smaller than the field corpus, so the same budget is scaled to
BUDGET rows: any single enumeration that streams more than BUDGET rows here is
one that grows with the scope or document size and stops in the field.

Nothing is raised or changed: the product keeps its behaviour and every
over-budget read, full-catalogue request, SQL and its calling site is recorded.
"""
import hashlib
import json
import re
import time
import traceback
from pathlib import Path

NARROW = ('document_id', 'lookup_id', 'lookup_ids', 'owner_id', 'target_id')


class Records:
    def __init__(self, code_root, budget):
        self.code = str(Path(code_root).resolve())
        self.budget = budget
        self.scenario = self.turn = None
        self.sql, self.reads, self.raised, self.guard_errors = [], [], [], []
        self.point_lookups = {}

    def site(self, depth=6):
        frames = []
        for f in reversed(traceback.extract_stack()[:-2]):
            name = f.filename
            if not name.startswith(self.code) or '/semantic_runtime/' not in name:
                continue
            short = name.split('/02_BACKEND/semantic_runtime/', 1)[1]
            if short.startswith('oracle_') and not frames:
                continue
            frames.append(f'{short}:{f.lineno} {f.name}')
            if len(frames) >= depth:
                break
        return frames

    def dump(self, path):
        Path(path).write_text(json.dumps({'budget': self.budget, 'sql': self.sql, 'reads': self.reads,
                                          'raised': self.raised, 'guard_errors': self.guard_errors,
                                          'point_lookups': [{'scenario': k[0], 'turn': k[1], 'kind': k[2], 'document_id': k[3],
                                                             'site': k[4], 'calls': v} for k, v in self.point_lookups.items()]},
                                         ensure_ascii=False) + '\n')


def sql_features(statement, binds):
    plain = re.sub(r"'(?:[^']|'')*'", "''", statement)
    upper = plain.upper()
    numbers = [b['name'] for b in binds if b.get('data_type') == 'NUMBER']
    in_with = bool(re.search(r'\bWITH\s+"?[A-Z_0-9]+"?\s+AS\s*\(', upper))
    return {'binds': len(binds), 'number_binds': numbers, 'with_and_number': in_with and bool(numbers),
            'clob_binds': [b.get('data_type') for b in binds].count('CLOB')}


def install(monkeypatch, records):
    from semantic_runtime import oracle_query_matcher as qm, oracle_query_index as qi, oracle_query_db as qdb
    from semantic_runtime import oracle_query_native as qn

    def read(via, request, **extra):
        # Bookkeeping must never raise into the product under test.
        entry = {'scenario': records.scenario, 'turn': records.turn, 'via': via, 'rows': 0, 'error': None}
        try:
            entry.update(scope_documents=len(request.sources.allowed), site=records.site(), **extra)
        except Exception as exc:
            records.guard_errors.append({'via': via, 'error': type(exc).__name__ + ': ' + str(exc)[:200]})
            entry.setdefault('site', [])
        records.reads.append(entry)
        return entry

    original_pages = qm.pages

    def pages(request, kind, **filters):
        entry = read('pages', request, kind=kind, filters=sorted(filters), narrow=[k for k in NARROW if k in filters])
        try:
            for value in original_pages(request, kind, **filters):
                entry['rows'] += 1
                yield value
        except Exception as exc:
            entry['error'] = str(exc)[:200]
            raise
    monkeypatch.setattr(qm, 'pages', pages)

    original_prepare = qn.prepare

    statements = {}

    def prepare(connection, statement, parameters):
        result = original_prepare(connection, statement, parameters)
        try:
            if len(statements) > 20000:
                statements.clear()
            statements[result[1]] = (connection.asset, statement, records.site())
        except Exception as exc:
            records.guard_errors.append({'via': 'prepare', 'error': type(exc).__name__ + ': ' + str(exc)[:200]})
        return result
    monkeypatch.setattr(qn, 'prepare', prepare)

    original_stream = qdb.Connection._pages

    def streamed(self, packed, binds):
        asset, statement, site = statements.get(packed, (None, None, None))
        entry = read('sql_rows', self.request, asset=asset, statement=statement)
        if site:
            entry['site'] = site
        try:
            for row in original_stream(self, packed, binds):
                entry['rows'] += 1
                yield row
        except Exception as exc:
            entry['error'] = str(exc)[:200]
            raise
    monkeypatch.setattr(qdb.Connection, '_pages', streamed)

    original_definitions = qi.Tools.definition_summaries_for

    def definitions(self, **kwargs):
        entry = read('definition_summaries_for', self.request, filters=sorted(k for k, v in kwargs.items() if v is not None))
        for value in original_definitions(self, **kwargs):
            entry['rows'] += 1
            yield value
    monkeypatch.setattr(qi.Tools, 'definition_summaries_for', definitions)

    def refuse(cls, name, label, *, is_property=False):
        original = getattr(cls, name)
        target = original.fget if is_property else original

        def wrapper(self, *a, **k):
            try:
                return target(self, *a, **k)
            except Exception as exc:
                try:
                    if 'QUERY_FULL_CATALOGUE' in str(exc):
                        records.raised.append({'scenario': records.scenario, 'turn': records.turn, 'object': label,
                                               'method': name, 'error': str(exc)[:200], 'site': records.site()})
                except Exception as own:
                    records.guard_errors.append({'via': 'refuse', 'error': type(own).__name__})
                raise
        monkeypatch.setattr(cls, name, property(wrapper) if is_property else wrapper)

    from semantic_runtime import oracle_query_catalog as qc
    original_page = qc.Records.page

    def page(self, kind, **filters):
        # One-row lookups by key: many of them for one document in one question is an N+1 that grows with document size.
        try:
            if filters.get('lookup_id') is not None and filters.get('after') is None:
                site = (records.site(3) or ['?'])[0]
                key = (records.scenario, records.turn, kind, filters.get('document_id') or '-', site)
                records.point_lookups[key] = records.point_lookups.get(key, 0) + 1
        except Exception as exc:
            records.guard_errors.append({'via': 'records.page', 'error': type(exc).__name__})
        return original_page(self, kind, **filters)
    monkeypatch.setattr(qc.Records, 'page', page)

    refuse(qi.Lists, '__iter__', 'Lists')
    refuse(qi.Lists, '__len__', 'Lists')
    refuse(qm.BodyValues, '__iter__', 'BodyValues')
    refuse(qm.BodyValues, '__len__', 'BodyValues')
    refuse(qi.Tools, 'definition_summaries', 'Tools.definition_summaries', is_property=True)


def bridge_record(records, payload, started, rows, error):
    try:
        _bridge_record(records, payload, started, rows, error)
    except Exception as exc:
        records.guard_errors.append({'via': 'bridge', 'error': type(exc).__name__ + ': ' + str(exc)[:200]})


def _bridge_record(records, payload, started, rows, error):
    statement = payload['statementText']
    binds = payload.get('binds', [])
    entry = {'scenario': records.scenario, 'turn': records.turn, 'sha': hashlib.sha256(statement.encode()).hexdigest()[:16],
             'payload_bytes': len(json.dumps(payload, ensure_ascii=False).encode()),
             'ms': round((time.monotonic() - started) * 1000, 1), 'rows': rows, 'error': error,
             **sql_features(statement, binds), 'site': records.site(3)}
    if error or entry['with_and_number']:
        entry['statement'] = statement[:4000]
    # 2026-11-12: the first statement of each kind and the caller past the Oracle/cache layers, so a
    # repeated statement (one per item) can be named.
    seen = records.__dict__.setdefault('statement_texts', {})
    if entry['sha'] not in seen:
        seen[entry['sha']] = statement[:4000]
        entry['statement'] = statement[:4000]
    entry['caller'] = [f for f in records.site(12) if not f.split(':')[0].startswith(('oracle_', 'runtime_cache'))][:3]
    records.sql.append(entry)
