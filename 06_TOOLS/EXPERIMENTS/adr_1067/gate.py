"""Read-only nine-cell operational gate; no continuation is authorized. Unknown evidence never passes.

This checks frozen control/delivery requirements, not answer correctness. It
does not invoke a model, repeat a cell, alter a score or change runtime state.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3

from common import ROOT, ART, read, sha, canonical_digest as digest
from collect_metrics import ro, text_hash, range_map, covered
from wire_audit import request_view, load_frozen_codecs, journal_records

VERSION = 'mvp-first-nine-gate-v1'
# These remain diagnostic configured values in the product receipt. ADR1067
# explicitly disables their enforcement; they are not effective wire limits.
CONFIGURED_LIMITS = {'ENTRY':24000, 'CATALOGUE':24000, 'REVIEW':48000,
                     'REPAIR':16000, 'ASSESS':64000, 'COMPOSE':32000}
EXPECTED = {'fsc-hard-005':'cb-1a8f9c604513', 'cm-023':'cb-764ad7c91f3f',
            'fsc-hard-008':'cb-d10a24aab57f'}
FIRST = [(case, arm) for case, arms in [
    ('fsc-hard-005', ('A0','A1','A2')), ('cm-023', ('A1','A2','A0')),
    ('fsc-hard-008', ('A2','A0','A1'))] for arm in arms]


def _reason(code, **values):
    return {'code':code, **values}


def _rooted(path):
    result = (ROOT / path).resolve()
    if not result.is_relative_to(ROOT.resolve()):
        raise ValueError('gate path escaped repository')
    return result


def _event_evidence(audit, directory):
    """Verify copied small telemetry against immutable rows in its journal."""
    errors = []
    groups = defaultdict(list)
    for row in audit.get('events', []):
        groups[row['journal']].append(row)
    for journal in (directory/'runtime').rglob('journal.sqlite'):
        groups.setdefault(str(journal.relative_to(directory)), [])
    for relative, events in groups.items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            errors.append(_reason('JOURNAL_UNAVAILABLE', journal=relative))
            continue
        db = ro(path)
        try:
            names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'event' not in names:
                if events: errors.append(_reason('JOURNAL_EVENT_TABLE_MISSING',journal=relative))
                continue
            actual_events = {(r['seq'],r['kind'],r['payload_hash']) for r in db.execute(
                "SELECT seq,kind,payload_hash FROM event WHERE kind IN "
                "('MODEL_INPUT_BUDGET','ONTOLOGY_BUNDLE_ACQUISITION','ONTOLOGY_REVIEW_PAGE_DELIVERED',"
                "'READ_CHOICE_SELECTED','LAW_DECISION_REJECTED','READ_JUDGMENT_RECORDED',"
                "'MODEL_OUTPUT_RECEPTION_STOP') OR kind LIKE 'NAVIGATION_REVIEW_%' OR kind LIKE 'NAVIGATION_TASK_%'")}
            if actual_events != {(r['seq'],r['kind'],r['payload_sha256']) for r in events}:
                errors.append(_reason('EXECUTION_EVENT_AUDIT_INCOMPLETE',journal=relative))
            for event in events:
                actual = db.execute('SELECT kind,payload_json,payload_hash FROM event WHERE seq=?', (event['seq'],)).fetchone()
                if (not actual or actual['kind'] != event['kind']
                        or actual['payload_hash'] != event.get('payload_sha256')
                        or digest(event['payload']) != actual['payload_hash']
                        or json.loads(actual['payload_json']) != event['payload']):
                    errors.append(_reason('EXECUTION_EVENT_BINDING_INVALID', journal=relative, seq=event['seq']))
        finally:
            db.close()
    return errors


def _native_records(audit, directory, frozen, proof):
    """Reconsume the collector's exact codec/native proof, not a second parser."""
    request=read(directory/'request.json')
    allowed=set(request.get('json',request).get('document_ids',[]))
    codecs=load_frozen_codecs(frozen)
    records={}
    journals={n['journal'] for call in audit.get('calls',[]) for n in call.get('successful_native_attempts',[])}
    for relative in sorted(journals):
        path=(directory/relative).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError('NATIVE_JOURNAL_UNAVAILABLE')
        db=ro(path)
        try:
            rows,invalid=journal_records(db,codecs,relative,checks=proof['checks'],
                acquired=proof['acquired'],allowed=allowed,generation=frozen['source_generation_id'])
            if invalid:raise ValueError('NATIVE_RECONSTRUCTION_INVALID')
            for group in rows.values():
                for row in group:
                    key=(relative,row['attempt_id'],row['view_id'])
                    if key in records:raise ValueError('DUPLICATE_NATIVE_RECONSTRUCTION')
                    records[key]=row
        finally:db.close()
    return records


def _input_calls(audit, directory, *, native_records=None):
    errors = []
    calls = audit.get('calls')
    if (not isinstance(calls, list) or not calls
            or any(not isinstance(c,dict) or not isinstance(c.get('request_path'),str) for c in calls)):
        return [_reason('PHYSICAL_INPUT_AUDIT_UNKNOWN')]
    actual_paths = {str(path.relative_to(directory)) for path in (directory/'model').glob('call-*/request.json')}
    errors.extend(_physical_call_inventory(calls, actual_paths, directory))
    if actual_paths != {c.get('request_path') for c in calls}:
        errors.append(_reason('PHYSICAL_INPUT_AUDIT_INCOMPLETE'))
    for call in calls:
        relative = call.get('request_path', '')
        path = (directory/relative).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            errors.append(_reason('ACTUAL_REQUEST_UNAVAILABLE', request=relative)); continue
        request = read(path)
        size = len(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
        if (sha(path) != call.get('request_sha256') or digest(request) != call.get('canonical_request_sha256')
                or size != call.get('request_chars')):
            errors.append(_reason('ACTUAL_REQUEST_CHANGED', request=relative)); continue
        receipts = call.get('input_budget_receipts', [])
        if not receipts:
            errors.append(_reason('MODE_BUDGET_UNKNOWN', request=relative)); continue
        for receipt in receipts:
            mode = receipt.get('input_mode')
            if (receipt.get('contract') != 'execution-review-input-modes-v1' or mode not in CONFIGURED_LIMITS
                    or receipt.get('request_sha256') != digest(request)
                    or receipt.get('measured_chars') != size
                    or receipt.get('mode_limit_chars') != CONFIGURED_LIMITS.get(mode)
                    or receipt.get('outer_limit_chars') != 100000
                    or receipt.get('configured_limit_chars') != CONFIGURED_LIMITS.get(mode)
                    or receipt.get('enforcement_enabled') is not False
                    or receipt.get('max_context_chars') != 0
                    or receipt.get('status') != 'WITHIN_BUDGET'):
                errors.append(_reason('MODE_BUDGET_RECEIPT_INVALID', request=relative)); continue
        # A proven rejected429 did not deliver originals. Its physical input
        # remains inventoried/budget-checked, but it cannot invalidate a later
        # successful delivery merely because there is no successful native view.
        from physical_transport import rejected_429
        transport=rejected_429(directory,path)
        if transport.get('status')=='KNOWN_REJECTED_HTTP429':
            if (call.get('transport')!=transport or call.get('successful_native_attempts')
                    or call.get('originals') or call.get('assessment_originals') or call.get('ontology_bundles')):
                errors.append(_reason('REJECTED_TRANSPORT_COUNTED_AS_DELIVERY',request=relative))
            continue
        if call.get('status') not in ('VERIFIED_EXACT_RECONSTRUCTION','VERIFIED_REDACTED_IDENTIFIERS'):
            errors.append(_reason('ACTUAL_WIRE_RECONSTRUCTION_UNKNOWN', request=relative))
        if not call.get('successful_native_attempts'):
            errors.append(_reason('SUCCESSFUL_NATIVE_RECEIPT_MISSING',request=relative))
        if ((call.get('status')=='VERIFIED_EXACT_RECONSTRUCTION' and call.get('missing_text_spans') != 0)
                or (call.get('status')=='VERIFIED_REDACTED_IDENTIFIERS'
                    and call.get('server_bound_missing_text_spans') != 0)):
            errors.append(_reason('ACTUAL_WIRE_SOURCE_EXTENTS_UNKNOWN',request=relative))
        for native in call.get('successful_native_attempts', []):
            journal = (directory/native['journal']).resolve()
            if not journal.is_relative_to(directory.resolve()) or not journal.is_file():
                errors.append(_reason('NATIVE_CALL_JOURNAL_UNAVAILABLE',request=relative)); continue
            db = ro(journal)
            try:
                row = db.execute('SELECT a.status,a.request_json,a.request_hash,v.body_json,v.body_hash '
                    'FROM model_attempt a JOIN model_view v USING(view_id) WHERE a.attempt_id=? AND a.view_id=?',
                    (native['attempt_id'],native['view_id'])).fetchone()
                if not row:
                    errors.append(_reason('NATIVE_CALL_RECEIPT_MISSING',request=relative)); continue
                actual = json.loads(row['request_json']); view = json.loads(row['body_json'])
                if (row['status']!='SUCCEEDED' or digest(actual)!=row['request_hash']
                        or digest(view)!=row['body_hash'] or digest(actual)!=digest(request)):
                    errors.append(_reason('NATIVE_CALL_WIRE_BINDING_CHANGED',request=relative)); continue
                record=(native_records or {}).get((native['journal'],native['attempt_id'],native['view_id']))
                if (not record or record.get('attempt_status')!='SUCCEEDED'
                        or record.get('native_request_sha256')!=digest(actual)
                        or record.get('status')!='VERIFIED_EXACT_RECONSTRUCTION'
                        or record.get('missing_text_spans')!=0):
                    errors.append(_reason('GATE_NATIVE_SOURCE_RECONSTRUCTION_UNKNOWN',request=relative));continue
                original_spans=record['spans']
                def signature(span):
                    return (span.get('document_id'),span.get('source_id'),span.get('source_ref'),span.get('evidence_id'),
                            str(span['block_id']),span['start_cp'],span['end_cp'])
                original_map = {signature(s):text_hash(s['text']) for s in original_spans}
                if Counter((signature(s),text_hash(s['text'])) for s in original_spans) != Counter(
                        (signature(s),s.get('text_sha256')) for s in call.get('originals',[])):
                    errors.append(_reason('GATE_SOURCE_SPAN_INVENTORY_CHANGED',request=relative))
                for span in call.get('originals',[]) + call.get('assessment_originals',[]):
                    if original_map.get(signature(span)) != span.get('text_sha256'):
                        errors.append(_reason('GATE_SOURCE_SPAN_NOT_IN_NATIVE_VIEW',request=relative))
                expected_cards = view.get('ontology_bundles',[])
                # Metadata is retained in the exact stored source view and
                # verified by its frozen lossless wire projection.
                if len(expected_cards)!=len(call.get('ontology_bundles',[])):
                    errors.append(_reason('GATE_ONTOLOGY_METADATA_CHANGED',request=relative))
                for card, receipt in zip(expected_cards,call.get('ontology_bundles',[])):
                    if digest(card)!=receipt.get('card_sha256'):
                        errors.append(_reason('GATE_ONTOLOGY_METADATA_CHANGED',request=relative))
                if view.get('navigation_review_tasks') != call.get('navigation_review_tasks'):
                    errors.append(_reason('GATE_REVIEW_QUEUE_METADATA_CHANGED',request=relative))
                for key in ('task_navigation','action_choice_contract','presentation_id'):
                    if view.get(key) != call.get(key):
                        errors.append(_reason('GATE_TASK_METADATA_CHANGED',request=relative,field=key))
                if digest(view.get('sources',[])) != call.get('current_source_hash'):
                    errors.append(_reason('GATE_TASK_SOURCE_HASH_CHANGED',request=relative))
            finally:
                db.close()
    return errors


def _physical_call_inventory(calls, actual_paths, directory):
    """A missing request must not disappear from both file and audit lists.

    The runner checks resources before writing START or invoking the client.
    Thus a preflight refusal has no physical call; result.model_calls is the
    client's count, not the number of native repository reservations.
    """
    errors = []
    try:
        completed = read(directory/'result.json')
        count = completed.get('model_calls')
        if type(count) is not int or not 0 <= count <= 40:
            raise ValueError('unknown physical call count')
    except (OSError, ValueError, TypeError, AttributeError):
        return [_reason('PHYSICAL_CALL_COUNT_UNKNOWN')]
    try:
        starts = []
        with (directory/'physical-calls.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                event = json.loads(line)
                if (not isinstance(event, dict) or event.get('event') not in ('START','END')
                        or type(event.get('call')) is not int or event['call'] <= 0):
                    raise ValueError('invalid physical call record')
                if event['event'] == 'START':
                    starts.append(event['call'])
    except (OSError, ValueError, TypeError, UnicodeError):
        errors.append(_reason('PHYSICAL_CALL_START_INVENTORY_UNKNOWN'))
    else:
        if len(starts) != len(set(starts)):
            errors.append(_reason('PHYSICAL_CALL_START_DUPLICATED'))
        if starts != list(range(1, count+1)):
            errors.append(_reason('PHYSICAL_CALL_START_INVENTORY_MISMATCH',
                                  completed_model_calls=count, recorded_starts=starts))
    audit_paths = [row.get('request_path') if isinstance(row,dict) else None for row in calls]
    if (any(not isinstance(path,str) for path in audit_paths)
            or len(audit_paths) != len(set(path for path in audit_paths if isinstance(path,str)))):
        errors.append(_reason('PHYSICAL_INPUT_AUDIT_DUPLICATED_OR_INVALID'))
    numbers = []
    for path in sorted(actual_paths):
        match = re.fullmatch(r'model/call-([0-9]{3})-service/request\.json', path)
        if match is None:
            errors.append(_reason('ACTUAL_REQUEST_PATH_INVALID', request=path))
        else:
            numbers.append(int(match[1]))
    if (len(actual_paths) != count or len(calls) != count
            or sorted(numbers) != list(range(1,count+1))):
        errors.append(_reason('PHYSICAL_CALL_REQUEST_INVENTORY_MISMATCH',
            completed_model_calls=count, request_files=len(actual_paths), audit_calls=len(calls)))
    return errors


def _control(audit):
    events = audit.get('events', [])
    transitions = [row['payload'] for row in events if row['kind']=='NAVIGATION_REVIEW_TRANSITION']
    errors = []
    if not transitions:
        return [_reason('REVIEW_CONTROL_AUDIT_UNKNOWN')]
    blocked = set()
    for row in transitions:
        if row.get('version') != 'navigation-review-transition-v1':
            errors.append(_reason('REVIEW_TRANSITION_VERSION_UNKNOWN'))
        if row.get('unrelated_pending_blocked') is not False:
            errors.append(_reason('UNRELATED_PENDING_ACTION_BLOCKED_OR_UNKNOWN', key=row.get('key')))
        if row.get('action_status') == 'BLOCKED':
            if not row.get('failure_code') and not row.get('failure'):
                errors.append(_reason('BLOCKED_ACTION_CAUSE_UNKNOWN', key=row.get('key')))
            if row.get('action_signature'):
                blocked.add((row['action_signature'],row.get('source_hash')))
        elif (row.get('action_signature'),row.get('source_hash')) in blocked:
            errors.append(_reason('FAILED_ACTION_REPEATED_WITH_SAME_ORIGINALS',key=row.get('key')))
    executed = Counter(row.get('canonical_action_hash') for row in transitions if row.get('action_status')=='EXECUTED')
    if any(key is None or count > 1 for key,count in executed.items()):
        errors.append(_reason('DUPLICATE_OR_UNBOUND_ACTION_EXECUTION'))
    for event in events:
        if event['kind']=='LAW_DECISION_REJECTED' and 'newly delivered originals omitted from read review' in json.dumps(event['payload']):
            errors.append(_reason('GLOBAL_REVIEW_OMISSION_BLOCKED_ACTION'))
    if not any(c.get('assessment_originals') for c in audit.get('calls', [])):
        errors.append(_reason('VALID_ORIGINALS_DID_NOT_REACH_ASSESS'))
    for call in audit.get('calls', []):
        if not call.get('successful_native_attempts') or 'read-choice' not in (call.get('source_stage') or ''):
            continue
        if any(r.get('input_mode')=='REPAIR' for r in call.get('input_budget_receipts',[])):
            continue
        tasks = call.get('navigation_review_tasks')
        if not isinstance(tasks,dict) or tasks.get('version')!='navigation-review-tasks-v1':
            errors.append(_reason('PENDING_REVIEW_QUEUE_UNKNOWN')); continue
        current = set(tasks.get('current_source_ids',[]))
        task = call.get('task_navigation')
        if isinstance(task,dict) and task.get('version') == 'task-local-navigation-v1':
            # This frozen projection intentionally keeps the complete queue on
            # the server. Do not compare its global count with an omitted list.
            count = tasks.get('pending_count')
            native_journals = {r['journal'] for r in call['successful_native_attempts']}
            projections = [r['payload'] for r in events
                if r['kind']=='NAVIGATION_TASK_INPUT_PROJECTED' and r['journal'] in native_journals
                and r['payload'].get('presentation_id') == call.get('presentation_id')
                and r['payload'].get('current_source_hash') == call.get('current_source_hash')]
            if (type(count) is not int or count < 0 or len(current)>3
                    or task.get('state_retained') is not True
                    or task.get('screen_change_is_evidence') is not False
                    or not projections or any(r.get('server_state_retained') is not True for r in projections)):
                errors.append(_reason('TASK_LOCAL_PENDING_RETENTION_NOT_PROVEN'))
            continue
        pending = {t['source_id'] for t in tasks.get('pending',[])}
        accounted = current | set(tasks.get('not_sent_source_ids',[])) | set(tasks.get('repair_exhausted_source_ids',[]))
        if len(current)>3 or not pending<=accounted or tasks.get('pending_count')!=len(tasks.get('pending',[])):
            errors.append(_reason('PENDING_REVIEW_SILENTLY_DROPPED_OR_PAGE_OVERFLOW'))
    return errors


def _provisions(bundle, store, allowed):
    rows = []
    for provision in bundle['provisions']:
        anchor = provision['anchor']
        key = digest({k:anchor[k] for k in ('document_id','version','unit_id')})
        row = {'anchor_key':key, 'label':anchor['label'], 'anchor':anchor,
               'eligible':False, 'reason':None, 'spans':[]}
        if anchor['document_id'] not in allowed:
            row['reason'] = 'DOCUMENT_NOT_AUTHORIZED'
        else:
            blocks = list(store.execute('SELECT block_id,text,source_artifact_sha256 FROM block_payload '
                'WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',
                (anchor['document_id'], anchor['unit_id'])))
            if not blocks:
                row['reason'] = 'NO_OWN_BODY'
            elif any(b['source_artifact_sha256'] != anchor['version'] for b in blocks):
                row['reason'] = 'SOURCE_VERSION_CHANGED'
            elif text_hash('\n'.join(b['text'] for b in blocks)) != anchor['content_sha256']:
                row['reason'] = 'SOURCE_CONTENT_CHANGED'
            else:
                row['eligible'] = True
                row['spans'] = [{'document_id':anchor['document_id'],'block_id':str(b['block_id']),
                    'start_cp':0,'end_cp':len(b['text']),'text_sha256':text_hash(b['text'])} for b in blocks if b['text']]
        rows.append(row)
    return rows


def _ontology(cell, audit, bundle, store, allowed):
    errors = []
    acquisitions = [r['payload'] for r in audit.get('events', []) if r['kind']=='ONTOLOGY_BUNDLE_ACQUISITION']
    actual_cards = [(call, card) for call in audit.get('calls', [])
                    if call.get('successful_native_attempts') for card in call.get('ontology_bundles', [])]
    if cell['arm']=='A0':
        if acquisitions or actual_cards:
            errors.append(_reason('A0_ONTOLOGY_LEAK'))
        return errors, {'acquisitions':len(acquisitions),'delivered_cards':len(actual_cards)}
    expected = bundle['bundle_id']
    landed = [r for r in acquisitions if r.get('bundle_id')==expected]
    if not landed:
        errors.append(_reason('LANDING_MISS', bundle_id=expected))
    elif any(r.get('recursion') is not False or r.get('scope_extended') is not False
             or r.get('automatic_adoption') is not False for r in landed):
        errors.append(_reason('ONTOLOGY_ACQUISITION_CONTRACT_INVALID',bundle_id=expected))
    provisions = _provisions(bundle, store, allowed)
    wanted_cards = [(call,card) for call,card in actual_cards if card.get('bundle_id')==expected]
    if not wanted_cards:
        errors.append(_reason('EXPECTED_BUNDLE_NOT_DELIVERED',bundle_id=expected))
    coverage = []
    for row in provisions:
        spans = []
        for call,card in wanted_cards:
            if card.get('mode') != cell['arm']:
                errors.append(_reason('ONTOLOGY_ARM_MISMATCH',bundle_id=expected))
                continue
            for delivered in card.get('provisions',[]):
                anchor = delivered.get('anchor',{})
                if anchor != row['anchor']:
                    continue
                refs = delivered.get('source_refs',delivered.get('evidence_refs',[]))
                if (delivered.get('acquisition_status')=='ACQUIRED'
                        and delivered.get('delivery_status') in (None,'PREPARED','PARTIAL_NOT_SENT')):
                    spans.extend(s for s in call.get('originals',[]) if s.get('source_ref') in refs)
        mapping = range_map(spans)
        complete = bool(row['spans']) and all(covered(s,mapping) for s in row['spans'])
        if row['eligible'] and not complete:
            errors.append(_reason('ELIGIBLE_PROVISION_NOT_FULLY_DELIVERED',bundle_id=expected,anchor_key=row['anchor_key']))
        if row['reason'] in ('SOURCE_VERSION_CHANGED','SOURCE_CONTENT_CHANGED'):
            errors.append(_reason(row['reason'],bundle_id=expected,anchor_key=row['anchor_key']))
        coverage.append({'anchor_key':row['anchor_key'],'label':row['label'],
            'eligible':row['eligible'],'reason':row['reason'],'full_span_delivered':complete})
    if not any(row['eligible'] for row in provisions):
        errors.append(_reason('EXPECTED_BUNDLE_ELIGIBILITY_UNKNOWN',bundle_id=expected))
    return errors, {'bundle_id':expected,'landed':bool(landed),
        'delivered_cards':len(wanted_cards),'provisions':coverage}


def check(frozen):
    """Return a concrete fail-closed report; caller may persist it unchanged."""
    result = {'schema_version':VERSION,'passed':False,'reasons':[],'cells':[],
        'quality_score_used_for_gate':False,'meaning_errors_are_not_stop_conditions':True}
    try:
        if (frozen.get('enforce_input_character_limits') is not False
                or frozen.get('minimal_action_choices') is not True
                or frozen.get('mode_limits') != {key:None for key in
                    ('entry','catalogue','review','repair','assess','compose','outer')}):
            result['reasons'].append(_reason('ACTION_INPUT_CONTRACT_CHANGED')); return result
        first = frozen['execution_order']
        if ([(c['case_id'],c['arm']) for c in first] != FIRST
                or [c['ordinal'] for c in first] != list(range(1,10))):
            result['reasons'].append(_reason('FIRST_NINE_ORDER_CHANGED')); return result
        freeze_path = ART/'design-freeze.json'
        if not freeze_path.is_file() or digest(read(freeze_path)) != digest(frozen):
            result['reasons'].append(_reason('DESIGN_FREEZE_UNAVAILABLE_OR_CHANGED')); return result
        frozen_hash = sha(freeze_path)
        result['design_freeze_sha256'] = frozen_hash
        snapshot_path = _rooted(frozen['snapshot_path'])
        if sha(snapshot_path) != frozen['snapshot_file_sha256']:
            result['reasons'].append(_reason('APPROVED_SNAPSHOT_CHANGED')); return result
        snapshot = read(snapshot_path)
        if digest(snapshot) != frozen['snapshot_digest']:
            result['reasons'].append(_reason('APPROVED_SNAPSHOT_BINDING_CHANGED')); return result
        bundles = {b['bundle_id']:b for b in snapshot['bundles']}
        store = ro(_rooted(frozen['data_path'])/'store.sqlite')
        try:
            for cell in first:
                directory = ART/'matrix'/f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"
                report = {'cell':cell,'passed':False,'reasons':[],'artifacts':{}}
                result['cells'].append(report)
                names = ('result.json','reservation.json','request.json','metrics.json','execution-audit.json')
                missing = [name for name in names if not (directory/name).is_file()]
                if missing:
                    report['reasons'].append(_reason('CELL_EVIDENCE_MISSING',files=missing)); continue
                report['artifacts'] = {name:sha(directory/name) for name in names}
                completed, reservation = read(directory/'result.json'), read(directory/'reservation.json')
                metrics, audit = read(directory/'metrics.json'), read(directory/'execution-audit.json')
                if (completed.get('cell') != cell or completed.get('completed') is not True
                        or completed.get('outcome') not in ('SERVICE_COMPLETED','NATIVE_BOUNDED_FAILURE')
                        or reservation.get('cell') != cell or reservation.get('design_freeze_sha256') != frozen_hash):
                    report['reasons'].append(_reason('CELL_COMPLETION_OR_FREEZE_INVALID'))
                if (audit.get('schema_version') != 'mvp-execution-gate-evidence-v1'
                        or audit.get('case_id') != cell['case_id'] or audit.get('arm') != cell['arm']
                        or audit.get('input_files',{}).get('result.json') != report['artifacts']['result.json']
                        or audit.get('input_files',{}).get('request.json') != report['artifacts']['request.json']):
                    report['reasons'].append(_reason('CELL_EXECUTION_AUDIT_BINDING_INVALID'))
                integrity = metrics.get('source_integrity',{})
                if (integrity.get('mismatch_count') != 0 or integrity.get('failures') != []
                        or audit.get('source_integrity_verified') is not True
                        or metrics.get('request_acl_check') != 'CHECKED'
                        or metrics.get('citation_unresolved') != []):
                    report['reasons'].append(_reason('SOURCE_SCOPE_STATE_OR_CITATION_INTEGRITY_NOT_PROVEN'))
                # A budget refusal may happen before a physical request, so
                # checking only requests would miss a bounded partial answer.
                outcome=metrics.get('outcome') or {}
                if isinstance(outcome,dict) and 'INPUT' in str(outcome.get('stop_reason','')):
                    report['reasons'].append(_reason('TERMINAL_INPUT_BUDGET_FAILURE',stop_reason=outcome.get('stop_reason')))
                for event in audit.get('events',[]):
                    if event.get('kind')=='MODEL_INPUT_BUDGET' and event['payload'].get('status')!='WITHIN_BUDGET':
                        report['reasons'].append(_reason('INPUT_BUDGET_REFUSAL',status=event['payload'].get('status')))
                if completed.get('outcome')=='FATAL_STOP' or completed.get('error') or metrics.get('service_error'):
                    report['reasons'].append(_reason('CODE_OR_RUNTIME_EXCEPTION'))
                report['reasons'].extend(_event_evidence(audit,directory))
                receipt_path=ART/'evaluation-case-receipts.json'
                receipts=read(receipt_path)
                if receipts.get('design_freeze_sha256')!=frozen_hash:
                    raise ValueError('METRIC_RECEIPTS_FREEZE_CHANGED')
                metric_receipts=receipts.get('metrics',{}).get(str(cell['ordinal']),{})
                for name in ('metrics.json','evidence-audit.json'):
                    path=directory/name
                    if metric_receipts.get(str(path.relative_to(ROOT)))!=sha(path):
                        raise ValueError('SOURCE_PROOF_RECEIPT_CHANGED')
                audit_path=directory/'execution-audit.json'
                if receipts.get('execution_audit',{}).get(str(cell['ordinal']),{}).get(
                        str(audit_path.relative_to(ROOT)))!=sha(audit_path):
                    raise ValueError('EXECUTION_AUDIT_RECEIPT_CHANGED')
                native_records=_native_records(audit,directory,frozen,read(directory/'evidence-audit.json'))
                report['reasons'].extend(_input_calls(audit,directory,native_records=native_records))
                report['reasons'].extend(_control(audit))
                request = read(directory/'request.json')
                allowed = set(request.get('json',request).get('document_ids',[]))
                if not allowed:
                    report['reasons'].append(_reason('REQUEST_SCOPE_UNKNOWN'))
                errors, ontology = _ontology(cell,audit,bundles[EXPECTED[cell['case_id']]],store,allowed)
                report['reasons'].extend(errors); report['ontology']=ontology
                report['passed'] = not report['reasons']
        finally:
            store.close()
    except (OSError,ValueError,TypeError,KeyError,sqlite3.DatabaseError) as error:
        result['reasons'].append(_reason('GATE_EVIDENCE_UNKNOWN',error_type=type(error).__name__))
    result['passed'] = (not result['reasons'] and len(result['cells'])==9
                        and all(row['passed'] for row in result['cells']))
    return result
