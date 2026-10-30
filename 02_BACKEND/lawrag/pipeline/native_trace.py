"""Offline native journal projection; never imported by the serving pipeline.

Read receipts attest to acquisition, presentation receipts attest to delivery,
and neither attests to legal correctness. All reads use one SQLite snapshot.
"""
from __future__ import annotations

from semantic_runtime.legal_agent import journal_storage
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from semantic_runtime.contracts import digest

TERMINAL = frozenset({'COMPLETED', 'FAILED', 'INTERRUPTED'})
CASE_STAGES = ('INTENT', 'PLAN', 'RECALL', 'READ', 'SELECT', 'ASSESS', 'COMPOSE')


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def checked_json(row, field, hash_field):
    value = json.loads(row[field])
    if digest(value) != row[hash_field]:
        raise ValueError('native receipt hash mismatch: ' + hash_field)
    return value


def _ids(values):
    ids = []
    for value in values:
        ident = value if isinstance(value, str) else value.get('source_id', value.get('id'))
        if not isinstance(ident, str) or not ident:
            raise ValueError('invalid native source identity')
        ids.append(ident)
    return sorted(set(ids))


def read_trace(path, *, expected_run=None, expected_binding=None, max_rows=200000):
    """Project only a terminal journal, rejecting corrupt receipts and wrong scopes.

    No raw request, model payload, feedback text or credentials is returned.
    snapshot_sha256 covers logical rows, including WAL-visible committed rows.
    """
    path = Path(path).resolve(strict=True)
    with closing(journal_storage.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
        db.row_factory = journal_storage.row
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA busy_timeout=200')
        db.execute('BEGIN')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (5, 6):
            raise ValueError('unsupported native journal version')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'run', 'event', 'entity_version', 'entity_head', 'evidence_unit',
                    'evidence_span', 'observation', 'model_view', 'model_attempt', 'presentation'}
        if not required <= tables:
            raise ValueError('incomplete native journal schema')
        rows = {}; consumed = 0
        for table in sorted(required | ({'publication'} & tables)):
            values = [dict(r) for r in db.execute('SELECT * FROM ' + table + ' ORDER BY rowid LIMIT ?', (max_rows + 1,))]
            consumed += len(values)
            if consumed > max_rows:
                raise ValueError('native diagnostic row budget exceeded')
            rows[table] = values
        if len(rows['run']) != 1:
            raise ValueError('native run singleton required')
        run = rows['run'][0]
        if run['status'] not in TERMINAL:
            raise ValueError('native journal is not terminal')
        if expected_run is not None and run['run_id'] != expected_run:
            raise ValueError('native run ID mismatch')
        binding = checked_json(run, 'binding_json', 'binding_hash')
        if expected_binding:
            for key, value in expected_binding.items():
                if binding.get(key) != value:
                    raise ValueError('native generation/binding mismatch: ' + key)
        scope = binding.get('scope', {}).get('document_version_ids')
        if not isinstance(scope, list) or not isinstance(binding.get('generation_id'), str):
            raise ValueError('native generation/scope missing')
        events = []
        for row in rows['event']:
            events.append({**row, 'payload': checked_json(row, 'payload_json', 'payload_hash')})
        event_seqs = {r['seq'] for r in events}
        events_by_seq = {r['seq']: r for r in events}
        if len(event_seqs) != len(events):
            raise ValueError('duplicate event sequence')
        entities = {}
        for row in rows['entity_version']:
            payload = checked_json(row, 'payload_json', 'payload_hash')
            if row['created_seq'] not in event_seqs:
                raise ValueError('entity event missing')
            entities[(row['kind'], row['entity_id'], row['version'])] = (row, payload)
        stages = {}; stage_refs = {}
        for head in rows['entity_head']:
            key = (head['kind'], head['entity_id'], head['version'])
            if key not in entities:
                raise ValueError('entity head version missing')
            if head['kind'] == 'case_stage' and head['validity'] == 'CURRENT':
                row, payload = entities[key]
                stage = head['entity_id'].removeprefix('case:')
                if stage not in CASE_STAGES:
                    raise ValueError('unknown native case stage')
                accepted = events_by_seq[row['created_seq']]
                if (accepted['kind'] != 'CASE_JUDGMENT_ACCEPTED' or
                        accepted['payload'].get('stage') != stage or
                        accepted['payload'].get('payload_hash') != row['payload_hash']):
                    raise ValueError('native stage acceptance mismatch')
                stages[stage] = payload
                stage_refs[stage] = {'kind': row['kind'], 'entity_id': row['entity_id'],
                                     'version': row['version'], 'payload_hash': row['payload_hash'],
                                     'event_seq': row['created_seq'],
                                     'inherited': bool(events_by_seq[row['created_seq']]['payload'].get('origin'))}
        evidence = {}; source_spans = {}; span_groups = {}
        for span in rows['evidence_span']:
            span_groups.setdefault(span['evidence_id'], []).append(span)
        for row in rows['evidence_unit']:
            if row['generation_id'] != binding['generation_id'] or row['document_id'] not in scope:
                raise ValueError('native evidence escaped generation/scope')
            spans = sorted(span_groups.get(row['evidence_id'], []), key=lambda r: r['ordinal'])
            if not spans or text_hash('\n'.join(r['text'] for r in spans)) != row['text_hash']:
                raise ValueError('native evidence text mismatch')
            for span in spans:
                if (text_hash(span['text']) != span['span_hash'] or span['start_cp'] < 0 or
                        span['end_cp'] - span['start_cp'] != len(span['text'])):
                    raise ValueError('native evidence span mismatch')
            evidence[row['evidence_id']] = row
            target = source_spans.setdefault(row['source_id'], {'document_id': row['document_id'], 'spans': []})
            target['spans'].extend({k: span[k] for k in ('block_id', 'start_cp', 'end_cp', 'span_hash')} for span in spans)
        if any(s['evidence_id'] not in evidence for s in rows['evidence_span']):
            raise ValueError('orphan evidence span')
        observations = []
        completed_reads = {}
        for row in rows['observation']:
            result = checked_json(row, 'result_json', 'result_hash')
            request = json.loads(row['request_json'])
            expected_key = digest({'action': {k: request[k] for k in ('tool', 'args')}, 'binding': run['binding_hash']})
            observed_event = events_by_seq.get(row['created_seq'])
            if (request['tool'] != row['tool'] or expected_key != row['request_key'] or
                    result.get('status') != row['status'] or observed_event is None or
                    observed_event['kind'] != 'OBSERVATION' or
                    observed_event['payload'].get('observation_id') != row['observation_id'] or
                    observed_event['payload'].get('request_key') != row['request_key']):
                raise ValueError('native observation receipt mismatch')
            args = request.get('args', {})
            coverage_key = digest({'tool': row['tool'], 'target': args.get('target'), 'extent': args.get('extent')})
            observations.append({'id': row['observation_id'], 'tool': row['tool'],
                                 'status': row['status'], 'event_seq': row['created_seq'],
                                 'result_hash': row['result_hash'], 'coverage_key': coverage_key})
            if (row['tool'].lower() == 'read' and row['status'] == 'OK' and
                    result.get('coverage', {}).get('complete') is True):
                completed_reads[coverage_key] = observations[-1]
        views = {r['view_id']: checked_json(r, 'body_json', 'body_hash') for r in rows['model_view']}
        attempts = []
        for row in rows['model_attempt']:
            if row['view_id'] not in views:
                raise ValueError('native model view missing')
            checked_json(row, 'request_json', 'request_hash')
            if row['response_json'] is not None:
                checked_json(row, 'response_json', 'response_hash')
            attempts.append(row)
        delivered_views = {r['view_id'] for r in attempts if r['status'] == 'SUCCEEDED'}
        presentations = []
        for row in rows['presentation']:
            if row['view_id'] not in views or row['evidence_id'] not in evidence:
                raise ValueError('native presentation target missing')
            if row['delivered_text_hash'] != evidence[row['evidence_id']]['text_hash']:
                raise ValueError('native presentation text mismatch')
            if row['view_id'] in delivered_views:
                presentations.append(row)
        presented_ids = sorted({evidence[r['evidence_id']]['source_id'] for r in presentations})
        pools = [e for e in events if e['kind'] == 'SOURCE_RECALL_POOL']
        finished = [e for e in events if e['kind'] == 'SOURCE_RECALL_FINISHED']
        selections = [e for e in events if e['kind'] == 'BOUNDED_SOURCE_SELECTION']
        recall = stages.get('RECALL')
        initial = _ids(recall['selected_for_read']) if recall else (_ids(pools[0]['payload']['selected_for_read']) if pools else None)
        record = stages.get('READ', {}).get('record')
        full_read = _ids(record['read_complete']) if record else (_ids(finished[-1]['payload']['read_complete']) if finished else (_ids(pools[-1]['payload']['read_complete']) if pools else None))
        selected = _ids(stages['SELECT']['final_ids']) if 'SELECT' in stages else (_ids(selections[-1]['payload']['final_ids']) if selections else None)
        selection_basis = 'CASE_STAGE' if 'SELECT' in stages else 'BOUNDED_SOURCE_SELECTION' if selections else None
        publication = None
        if rows.get('publication'):
            if len(rows['publication']) != 1:
                raise ValueError('duplicate native publication')
            publication = checked_json(rows['publication'][0], 'result_json', 'result_hash')
        # Follow-up requests may execute only ASSESS/COMPOSE. Their committed
        # publication carries the accepted selection; absence of a fresh SELECT
        # stage must not erase it or imply a fresh source search.
        if selected is None and publication is not None and 'assembly' in publication:
            selected = _ids(publication['assembly']['context'])
            selection_basis = 'PUBLISHED_ASSEMBLY'
        answer = (publication or {}).get('result', {}).get('answer', (publication or {}).get('answer'))
        if answer is None and 'COMPOSE' in stages:
            answer = stages['COMPOSE']
        cited = None if answer is None else sorted({sid for c in answer.get('claims', []) for sid in c.get('source_ids', [c.get('source_id')]) if sid})
        refs = [{'seq': e['seq'], 'kind': e['kind'], 'payload_hash': e['payload_hash']} for e in events]
        failures = [e for e in events if e['kind'] == 'RUN_FAILED']
        last_view = views[attempts[-1]['view_id']] if attempts else {}
        active_phase = last_view.get('source_stage', last_view.get('phase'))
        issues = []
        for obs in observations:
            if obs['status'] in ('DENIED', 'ERROR', 'UNRESOLVED', 'PARTIAL', 'TRUNCATED'):
                issue = {'type': 'tool_' + obs['status'].lower(), 'stage': 'READ' if obs['tool'].lower() == 'read' else 'RECALL',
                               'confirmed': True, 'refs': [{'table': 'observation', 'id': obs['id'], 'hash': obs['result_hash'], 'event_seq': obs['event_seq']}]}
                recovery = completed_reads.get(obs['coverage_key'])
                if (obs['status'] in ('PARTIAL', 'TRUNCATED') and recovery is not None and
                        recovery['event_seq'] > obs['event_seq']):
                    issue['resolved'] = True
                    issue['recovery_ref'] = {'table': 'observation', 'id': recovery['id'], 'hash': recovery['result_hash'], 'event_seq': recovery['event_seq']}
                issues.append(issue)
        if full_read is not None and record and record.get('read_partial'):
            issues.append({'type': 'partial_original', 'stage': 'READ', 'confirmed': True,
                           'refs': [stage_refs['READ']]})
        if selected == [] and selection_basis != 'PUBLISHED_ASSEMBLY':
            relevant = stage_refs.get('SELECT')
            issues.append({'type': 'empty_selection', 'stage': 'SELECT', 'confirmed': True,
                           'refs': [relevant] if relevant else [{'seq': selections[-1]['seq'], 'payload_hash': selections[-1]['payload_hash']}]})
        if failures:
            e = failures[-1]
            issues.append({'type': 'execution_failure', 'stage': active_phase or 'UNKNOWN', 'confirmed': True,
                           'refs': [{'seq': e['seq'], 'payload_hash': e['payload_hash']}],
                           'cause': 'UNKNOWN'})
        if run['status'] == 'COMPLETED' and selected is not None:
            if set(selected) - set(source_spans):
                raise ValueError('selected source has no acquired evidence')
        snapshot = digest({'version': version, 'rows': rows})
        def total(field):
            return sum(r[field] for r in attempts) if attempts and all(r[field] is not None for r in attempts) else None
        result = {'schema_version': 'native-failure-trace-v1', 'journal_path': str(path),
                  'snapshot_sha256': snapshot, 'journal_version': version, 'run_id': run['run_id'],
                  'run_status': run['status'], 'binding': binding, 'question_hash': digest(json.loads(run['request_json']).get('question')),
                  'published_answer_sha256': digest(answer) if publication is not None and answer is not None else None,
                  'published_query_sha256': digest(publication['query']) if publication is not None else None,
                  'published_result_sha256': digest(publication) if publication is not None else None,
                  'selection_basis': selection_basis,
                  'stage_refs': stage_refs, 'event_refs': refs, 'issues': issues,
                  'stages': {'initial': initial, 'first_round': full_read,
                             'cumulative': sorted(source_spans) if source_spans or record is not None or pools or finished else None,
                             'presented': presented_ids if presentations or record is not None or full_read is not None else None,
                             'selected': selected, 'cited': cited},
                  'evidence_coverage': source_spans,
                  'presentation_coverage': {sid: [dict(r) for r in presentations if evidence[r['evidence_id']]['source_id'] == sid] for sid in presented_ids},
                  'usage': {'attempts': len(attempts), 'input_tokens': total('input_tokens'),
                            'output_tokens': total('output_tokens'), 'cost_usd': total('cost_usd')},
                  'legal_quality': 'UNKNOWN', 'runtime_loadable': False}
        result['content_sha256'] = digest(result)
        return result


def verify_trace(value):
    if value.get('schema_version') != 'native-failure-trace-v1' or value.get('content_sha256') != digest({k: v for k, v in value.items() if k != 'content_sha256'}):
        raise ValueError('native trace hash/version mismatch')
    return value


def native_result_stages(result, journal):
    """Cross-check the published response and terminal journal before golden scoring."""
    trace = read_trace(journal, expected_run=result['run_id'], expected_binding={
        'generation_id': result['answer']['generation_id'],
        'store_sha256': result['answer']['source_store_sha256']})
    if trace['run_status'] != 'COMPLETED':
        raise ValueError('native golden response requires a completed journal')
    if trace['published_query_sha256'] != digest(result['query']):
        raise ValueError('native golden question mismatch')
    if trace['published_answer_sha256'] != digest(result['answer']):
        raise ValueError('native golden published answer mismatch')
    if trace['published_result_sha256'] != digest(result):
        raise ValueError('native golden published result mismatch')
    scope = result['query']['scope']['document_version_ids']
    if set(scope) != set(trace['binding']['scope']['document_version_ids']):
        raise ValueError('native golden scope mismatch')
    selected = _ids(result['assembly']['context'])
    cited = sorted({sid for c in result['answer']['claims'] for sid in c['source_ids']})
    if trace['stages']['selected'] != selected or trace['stages']['cited'] != cited:
        raise ValueError('native golden selection/citation mismatch')
    return trace
