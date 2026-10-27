"""Prospectively declared tiny state census; no corpus, model or network.

The owner freezes this file and finite-matrix.json before execution. Each arm
uses a separate semantic_runtime package namespace and a fresh mutable fixture.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
from itertools import product
import json
from pathlib import Path
import resource
import socket
import sqlite3
import sys
from types import ModuleType, SimpleNamespace as S

MATRIX_PATH = Path(__file__).with_name('finite-matrix.json')


def tree(value, seen=None):
    """Type/order-preserving diagnostic, including deliberate unsupported data."""
    seen = set() if seen is None else seen
    kind = type(value)
    if kind in (dict, list, tuple, set, frozenset):
        if id(value) in seen:
            return ['cycle', kind.__name__]
        seen.add(id(value))
        if kind is dict:
            result = ['dict', [[tree(k, seen), tree(v, seen)] for k, v in value.items()]]
        else:
            items = [tree(v, seen) for v in value]
            if kind in (set, frozenset):
                items.sort(key=lambda x: json.dumps(x, ensure_ascii=False))
            result = [kind.__name__, items]
        seen.remove(id(value))
        return result
    if kind in (str, int, float, bool, type(None)):
        return [kind.__name__, value]
    return ['unsupported', kind.__module__ + '.' + kind.__name__]


def fingerprint(value):
    return hashlib.sha256(json.dumps(tree(value), ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load_runtime(root, name):
    path = Path(root).resolve() / '02_BACKEND/semantic_runtime'
    package = ModuleType(name)
    package.__path__ = [str(path)]
    package.__package__ = name
    sys.modules[name] = package
    sys.path.insert(0, str(Path(root).resolve() / '02_BACKEND'))
    return S(rel=importlib.import_module(name + '.legal_agent.unit_relations'),
             cs=importlib.import_module(name + '.legal_agent.connection_scope'),
             contracts=importlib.import_module(name + '.contracts'))


class PlainStore:
    def __init__(self, texts):
        self.texts = deepcopy(texts)
        self.generation = self.initial_generation = 1
        self.reads = self.checks = 0
        self.fail_reads = set()
        self.check_error = False
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE source_block(document_id TEXT, block_id TEXT, unit_id TEXT, text TEXT)')
        self.db.executemany('INSERT INTO source_block VALUES(?,?,NULL,?)',
                           [(d, b, t) for (d, b), t in texts.items()])

    def guard(self):
        if self.check_error:
            raise TimeoutError('synthetic source binding timeout')
        if self.generation != self.initial_generation:
            raise ValueError('synthetic immutable source changed')

    def source(self, did, bid):
        self.reads += 1
        if hasattr(self, 'check_unchanged'):
            self.check_unchanged()
        else:
            self.guard()
        if self.reads in self.fail_reads:
            raise TimeoutError('synthetic interrupted original read')
        return {'text': self.texts[(did, str(bid))], 'unit_id': None}

    def close(self):
        self.db.close()


class CheckedStore(PlainStore):
    def check_unchanged(self):
        self.checks += 1
        self.guard()


def span(rel, text, start=0, end=None, block='1'):
    end = len(text) if end is None else end
    return {'block_id': block, 'start_cp': start, 'end_cp': end,
            'text': text[start:end], 'block_hash': rel.text_hash(text),
            'span_hash': rel.text_hash(text[start:end])}


def fixture(rt, pattern='full', control=True, checker=True):
    texts = {('D1', '1'): '가나다라마바사', ('D1', '2'): '추가 원문',
             ('D2', '1'): '둘째 자료', ('D3', '1'): '새 자료'}
    store = (CheckedStore if checker else PlainStore)(texts)
    sources = {f'S{i}': {'document_id': f'D{i}', 'document_name': f'문서{i}',
               'heading': f'제{i}조', 'unit_id': None,
               'blocks': [{'block_id': '1'}] + ([{'block_id': '2'}] if i == 1 else [])}
               for i in (1, 2, 3)}
    s = S(scope={'D1', 'D2', 'D3'}, store=store, tools=S(sources=sources),
          profile={'candidate_navigation': {'investigation_control': control}},
          investigation_delivered_spans={})
    text = texts[('D1', '1')]
    spans = [span(rt.rel, text)]
    if pattern == 'partition': spans = [span(rt.rel, text, 0, 3), span(rt.rel, text, 3)]
    if pattern == 'overlap': spans = [span(rt.rel, text, 0, 5), span(rt.rel, text, 3)]
    if pattern == 'duplicate': spans = spans + deepcopy(spans)
    if pattern == 'empty': spans = []
    selected = {'R1': {'source_id': 'S1', 'evidence': [{'spans': spans}]}}
    if pattern == 'multi_source':
        selected['R2'] = {'source_id': 'S2', 'evidence': [{'spans': [span(rt.rel, texts[('D2', '1')])]}]}
    return s, selected


def mutate_fault(s, selected, fault):
    record = selected['R1']; rows = record['evidence'][0]['spans']
    p = rows[0] if rows else None
    if fault == 'none': return
    if fault == 'source_missing': del s.tools.sources['S1']
    elif fault == 'source_denied': s.scope.remove('D1')
    elif fault == 'source_document': s.tools.sources['S1']['document_id'] = 'D-hidden'
    elif fault == 'source_blocks_missing': del s.tools.sources['S1']['blocks']
    elif fault == 'original_missing': del s.store.texts[('D1', '1')]
    elif p is None: return  # Deliberately declared inactive empty-span fault.
    elif fault == 'block_outside': p['block_id'] = '99'
    elif fault == 'text_mismatch': p['text'] = '변조'
    elif fault == 'block_hash': p['block_hash'] = '0' * 64
    elif fault == 'span_hash': p['span_hash'] = '0' * 64
    elif fault == 'start_bool': p['start_cp'] = False
    elif fault == 'start_float': p['start_cp'] = 0.0
    elif fault == 'start_string': p['start_cp'] = '0'
    elif fault == 'start_negative': p['start_cp'] = -1
    elif fault == 'end_bool': p['end_cp'] = True
    elif fault == 'end_float': p['end_cp'] = float(p['end_cp'])
    elif fault == 'end_string': p['end_cp'] = str(p['end_cp'])
    elif fault == 'end_negative': p['end_cp'] = -1
    elif fault == 'end_before_start': p.update(start_cp=2, end_cp=1)
    elif fault == 'end_past_text': p['end_cp'] = 99
    elif fault == 'start_missing': del p['start_cp']
    elif fault == 'end_missing': del p['end_cp']
    elif fault == 'text_missing': del p['text']
    elif fault == 'block_missing': del p['block_id']
    else: raise AssertionError(fault)


def state(s, selected):
    return tree((s.scope, s.tools.sources, s.profile, selected,
                 s.investigation_delivered_spans, s.store.texts, s.store.generation))


def preparation(rt):
    cls = getattr(rt.rel, 'CatalogReadPreparation', None)
    return cls() if cls is not None else None


def acquired(rt, s, selected, prepared):
    if prepared is None:
        return rt.rel.acquired_blocks(s, selected)
    return rt.rel.acquired_blocks(s, selected, preparation=prepared)


def observed(call):
    try:
        value = call()
        return {'status': 'success', 'value': tree(value)}, value
    except Exception as exc:
        return {'status': 'error', 'type': type(exc).__name__, 'message': str(exc)}, None


def static_case(rt, case):
    s, selected = fixture(rt, case['pattern'], case['control'], case['checker'])
    try:
        mutate_fault(s, selected, case['fault'])
        before = state(s, selected); prepared = preparation(rt); outputs = []
        for _ in range(case['repeats']):
            out, _ = observed(lambda: acquired(rt, s, selected, prepared)); outputs.append(out)
        assert state(s, selected) == before, ('acquired_blocks mutated inputs', case)
        if not case['control'] or case['pattern'] == 'empty':
            assert s.store.reads == 0 and s.store.checks == 0, ('new store work introduced', case)
        return {'outputs': outputs, 'state': before}, {'reads': s.store.reads, 'checks': s.store.checks}
    finally:
        s.store.close()


def transition_case(rt, case):
    s, selected = fixture(rt, 'multi_source', case['control'], case['checker'])
    stores = [s.store]; prepared = preparation(rt); name = case['transition']; outputs = []
    def call():
        before = state(s, selected)
        out, value = observed(lambda: acquired(rt, s, selected, prepared))
        assert state(s, selected) == before, ('transition mutated inputs', case)
        outputs.append(out)
        return value
    try:
        if name == 'source_after_first_read_failure':
            s.store.fail_reads = {2}
        first = call()
        p = selected['R1']['evidence'][0]['spans'][0]
        if name == 'unchanged': pass
        elif name == 'deep_copy': selected = deepcopy(selected)
        elif name == 'order_reverse': selected = dict(reversed(list(selected.items())))
        elif name == 'valid_extra_span': selected['R1']['evidence'][0]['spans'].append(span(rt.rel, s.store.texts[('D1', '2')], block='2'))
        elif name == 'valid_extra_source': selected['R3'] = {'source_id': 'S3', 'evidence': [{'spans': [span(rt.rel, s.store.texts[('D3', '1')])]}]}
        elif name == 'delivered_append': s.investigation_delivered_spans = {'S1': [span(rt.rel, s.store.texts[('D1', '2')], block='2')]}
        elif name == 'delivered_remove':
            s.investigation_delivered_spans = {'S1': [deepcopy(p)]}; call(); s.investigation_delivered_spans.clear()
        elif name == 'acl_remove': s.scope.remove('D1')
        elif name == 'source_meta_document': s.tools.sources['S1']['document_id'] = 'D2'
        elif name == 'source_meta_blocks': s.tools.sources['S1']['blocks'] = [{'block_id': '2'}]
        elif name == 'source_meta_order': s.tools.sources['S1'] = dict(reversed(list(s.tools.sources['S1'].items())))
        elif name == 'span_start_bool': p['start_cp'] = False
        elif name == 'span_start_float': p['start_cp'] = 0.0
        elif name == 'span_end_bool': p['end_cp'] = True
        elif name == 'span_text': p['text'] = '변조'
        elif name == 'span_hash': p['span_hash'] = 'bad'
        elif name == 'store_changed': s.store.generation += 1
        elif name == 'store_replaced':
            s.store = type(s.store)(s.store.texts); stores.append(s.store)
        elif name == 'control_toggle': s.profile['candidate_navigation']['investigation_control'] = not case['control']
        elif name == 'returned_blocks':
            if first is not None: first[0]['S1'].add('FORGED')
        elif name == 'returned_spans':
            if first is not None: first[1]['S1'][0]['start_cp'] = False
        elif name == 'failure_then_recovery':
            p['span_hash'] = 'bad'; call(); p['span_hash'] = rt.rel.text_hash(p['text'])
        elif name == 'new_view': prepared = preparation(rt)
        elif name == 'cross_session':
            s, selected = fixture(rt, 'multi_source', case['control'], case['checker']); stores.append(s.store)
            selected['R1']['evidence'][0]['spans'][0]['text'] = '변조'
        elif name == 'checker_exception': s.store.check_error = True
        elif name == 'source_after_first_read_failure': s.store.fail_reads.clear()
        elif name == 'unsupported_source_metadata': s.tools.sources['S1']['unused_metadata'] = object()
        elif name == 'cyclic_source_metadata': s.tools.sources['S1']['unused_metadata'] = s.tools.sources['S1']
        else: raise AssertionError(name)
        call()
        if name == 'checker_exception': s.store.check_error = False; call()
        return {'outputs': outputs, 'state': state(s, selected)}, {'reads': sum(x.reads for x in stores), 'checks': sum(x.checks for x in stores)}
    finally:
        for store in stores: store.close()


class FaultDB:
    def __init__(self, db, fault): self.db, self.fault = db, fault
    def execute(self, sql, args=()):
        if 'FROM reference r' in sql and self.fault in ('operational', 'timeout'):
            if self.fault == 'timeout': raise TimeoutError('synthetic reference timeout')
            exc = sqlite3.OperationalError('database is locked')
            exc.sqlite_errorcode = sqlite3.SQLITE_BUSY
            raise exc
        return self.db.execute(sql, args)


def integration_fixture(rt, case):
    count, links = case['scopes'], case['links']
    texts = {(f'D{i}', '1'): f'문서 {i}의 합성 연결 원문' for i in range(1, count + 1)}
    texts.update({(f'TD{i}', '1'): f'대상 {i}의 합성 원문' for i in range(1, links + 1)})
    store = CheckedStore(texts); events = []; sources = {}; selected = {}; groups = {}; pages = []
    for i in range(1, count + 1):
        sid, did, gid = f'S{i}', f'D{i}', f'G{i}'
        sources[sid] = {'document_id': did, 'document_name': f'문서{i}', 'heading': f'원문{i}', 'unit_id': None, 'blocks': [{'block_id': '1'}]}
        offer = {'id': 'exact:source', 'unit_id': None, 'extent': 'exact', 'reader_target': 'source', 'block_ids': ['1'], 'block_count': 1, 'chars': len(texts[(did, '1')])}
        raw_span = span(rt.rel, texts[(did, '1')]); hit = {'source_id': sid, 'document_id': did, 'document_name': f'문서{i}', 'unit_id': None, 'article_unit_id': None, 'heading': f'원문{i}'}
        selected[gid] = {'source_id': sid, 'document_id': did, 'offer': offer, 'evidence': [{'spans': [deepcopy(raw_span)]}]}
        groups[gid] = {'id': gid, 'status': 'ACTIVE', 'hit': hit}
        pages.append({'id': f'P{i}', 'branch_id': gid, 'document_id': did, 'source_id': sid, 'scope_id': rt.contracts.digest(offer), 'spans': [deepcopy(raw_span)]})
    for i in range(1, links + 1):
        sources[f'T{i}'] = {'document_id': f'TD{i}', 'document_name': f'대상{i}', 'heading': f'대상원문{i}', 'unit_id': None, 'blocks': [{'block_id': '1'}]}
    db = sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE reference(id TEXT PRIMARY KEY,json TEXT); CREATE TABLE reference_end(reference_id TEXT,source_id TEXT);')
    for a in range(1, count + 1):
        for t in range(1, links + 1):
            ref = {'id': f'R{a}-{t}', 'source_id': f'S{a}', 'source_text': texts[(f'D{a}', '1')], 'source_text_sha256': rt.rel.text_hash(texts[(f'D{a}', '1')]), 'block_id': '1', 'resolution': 'EXACT_SOURCE', 'locator': {}, 'targets': [{'source_id': f'T{t}', 'unit_id': None, 'block_ids': ['1'], 'target_level': 'source'}]}
            db.execute('INSERT INTO reference VALUES(?,?)', (ref['id'], json.dumps(ref, ensure_ascii=False)))
            db.executemany('INSERT INTO reference_end VALUES(?,?)', [(ref['id'], f'S{a}'), (ref['id'], f'T{t}')])
    db.commit()
    session = S(store=store, scope={d for d, _ in texts}, profile={'candidate_navigation': {'investigation_control': True}},
                tools=S(sources=sources, db=FaultDB(db, case['fault'])),
                matcher=S(units={}, unit_fulltext=S(manifest={'index_sha256': 'synthetic-index'})),
                context=S(request={'question': '합성 질문'}), repo=S(event=lambda kind, value: events.append((kind, deepcopy(value)))))
    inv = S(s=session, modern=True, policy={'selected_connection_scope': True}, question='합성 질문',
            p={'binding': 'synthetic-binding', 'groups': groups, 'selected': selected, 'issues': [], 'basis_history': {}},
            closed_reference_decisions=lambda *args: {}, read_records=lambda: selected)
    saves = []
    inv.save = lambda: saves.append(fingerprint(inv.p))
    def delivered(current_pages):
        session.investigation_delivered_spans = {p['source_id']: deepcopy(p['spans']) for p in current_pages}
    inv.bind_reference_delivery = delivered
    data = {'sources': pages, 'references': {}, 'actions': []}
    if case['fault'] == 'acl': session.scope.remove('D1')
    elif case['fault'] == 'text': data['sources'][0]['spans'][0]['text'] = '변조'
    elif case['fault'] == 'generation': store.generation += 1
    return inv, data, {}, events, saves, db


def integration_case(rt, case):
    inv, data, actions, events, saves, db = integration_fixture(rt, case)
    outputs = []; view_counts = []
    try:
        for _ in range(2):
            reads_before, checks_before = inv.s.store.reads, inv.s.store.checks
            before_scope = getattr(inv.s, 'connection_scope_spans', None)
            out, _ = observed(lambda: rt.cs.offer_choices(inv, data, actions))
            assert getattr(inv.s, 'connection_scope_spans', None) == before_scope, 'scope binding leaked'
            expected_error = {'acl': 'ContractError', 'text': 'ContractError', 'generation': 'ValueError'}.get(case['fault'])
            assert out['status'] == ('error' if expected_error else 'success'), ('fixture integration outcome', case, out)
            if expected_error:
                assert out['type'] == expected_error, ('fixture integration error', case, out)
            else:
                choices = data['connection_scope_choices']
                assert len(choices) == case['scopes'], ('fixture connection scope count', case, choices)
                expected_status = ('FAILED' if case['fault'] in ('operational', 'timeout') else
                                   'PARTIAL' if case['links'] == 7 else 'COMPLETE')
                assert all(c['connection_preview']['status'] == expected_status for c in choices), ('fixture catalog status', case, choices)
                if case['fault'] == 'none':
                    expected_inline = case['scopes'] if case['links'] == 1 else 0
                    assert data['references']['inline_connection_count'] == expected_inline, ('fixture inline links', case)
                    assert len(actions) == (case['scopes'] if case['links'] else 0), ('fixture actions', case)
            outputs.append({'outcome': out, 'data': tree(data), 'actions': tree(actions), 'events': tree(events), 'state': tree(inv.p), 'saves': list(saves)})
            view_counts.append({'reads': inv.s.store.reads - reads_before, 'checks': inv.s.store.checks - checks_before})
        if case['fault'] == 'none':
            assert view_counts[0]['reads'] == view_counts[1]['reads'] > 0, ('next menu reused prior original verification', case, view_counts)
        return {'outputs': outputs}, {'reads': inv.s.store.reads, 'checks': inv.s.store.checks, 'views': view_counts}
    finally:
        inv.s.store.close(); db.close()


def cases(matrix, group):
    axes = matrix[group]
    keys = [k for k in axes if isinstance(axes[k], list)]
    for values in product(*(axes[k] for k in keys)):
        yield dict(zip(keys, values))


def run_matrix(baseline_root, candidate_root, emit, matrix=None):
    matrix = json.loads(MATRIX_PATH.read_text()) if matrix is None else matrix
    base = load_runtime(baseline_root, 'adr1076_baseline')
    candidate = load_runtime(candidate_root, 'adr1076_candidate')
    assert hasattr(candidate.rel, 'CatalogReadPreparation'), 'candidate preparation interface missing'
    counts = {}; reductions = []
    for name, run in [('static', static_case), ('transitions', transition_case), ('integration', integration_case)]:
        counts[name] = 0
        for case in cases(matrix, name):
            before, bc = run(base, case)
            after, cc = run(candidate, case)
            equal = before == after
            record = {'group': name, 'case': case, 'equal': equal, 'baseline': {'sha256': fingerprint(before), 'counts': bc}, 'optimized': {'sha256': fingerprint(after), 'counts': cc},
                      'baseline_output': before, 'optimized_output': after}
            emit(record)
            assert equal, ('mechanical equivalence mismatch', name, case)
            counts[name] += 1
            if name == 'static' and (not case['control'] or not case['checker'] or case['pattern'] == 'empty'):
                assert cc == bc, ('bypass changed original-read/check counts', case, bc, cc)
            if name == 'transitions' and (not case['control'] or not case['checker'] or case['transition'] == 'new_view'):
                assert cc == bc, ('transition bypass or new view skipped verification', case, bc, cc)
            if name == 'static' and case == {'pattern': 'full', 'fault': 'none', 'control': True, 'checker': True, 'repeats': 3}:
                assert cc['reads'] < bc['reads'], ('expected preparation reuse absent', bc, cc)
                reductions.append(record)
            if name == 'integration' and case == {'scopes': 4, 'links': 0, 'fault': 'none'}:
                assert cc['reads'] < bc['reads'], ('menu preparation is not connected', bc, cc)
                reductions.append(record)
    assert counts == {k: matrix['counts'][k] for k in counts}
    return {'status': 'PASS', 'paired_cases': sum(counts.values()), 'counts': counts, 'read_reduction_witnesses': reductions, 'external_model_calls': 0, 'real_data_loads': 0, 'legal_quality_certified': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-root', type=Path, required=True)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
    def forbidden(*args, **kwargs): raise RuntimeError('network forbidden in finite contract census')
    socket.create_connection = forbidden; socket.socket.connect = forbidden
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        def emit(row):
            stream.write(json.dumps(row, ensure_ascii=False) + '\n'); stream.flush()
        try:
            result = run_matrix(args.baseline_root, args.candidate_root, emit)
            emit({'summary': result}); print(json.dumps(result, ensure_ascii=False))
        except BaseException as exc:
            emit({'failure': {'type': type(exc).__name__, 'message': str(exc)}})
            raise


if __name__ == '__main__': main()
