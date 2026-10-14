"""Explain existing stop states without changing retrieval or completion policy.

Data resolution, model decisions, unprocessed work and execution limits retain
their separate provenance. No source body or prompt is copied into diagnostics.
"""
from collections import Counter
from copy import deepcopy
import traceback

VERSION = 'investigation-diagnostics-v1'


def report(stage, pending, blockers, observations=(), **context):
    return {'schema_version': VERSION, 'stage': stage, 'pending': pending,
            'cause_codes': list(dict.fromkeys(r['code'] for r in blockers)),
            'counts': dict(Counter(r['category'] for r in blockers)),
            'blockers': list(blockers), 'observations': list(observations), **context}


def reference_detail(ref):
    return {k: deepcopy(ref[k]) for k in ('reference_id', 'resolution', 'locator',
        'reading_policy', 'source_unit_path', 'target_unit_path', 'required_block_ids',
        'endpoint_block_ids', 'already_read') if k in ref}


def group_detail(group):
    return {'group_id': group['key'], 'anchor': deepcopy(group['anchor']),
            'target': deepcopy(group['target']), 'direction': group['direction'],
            'references': [reference_detail(c) for c in group['connections']]}


def navigation_report(session, state, limits, remaining, *, work_steps, model_batches, policy):
    blockers = []; observations = []
    for row in state['unresolved'].values():
        item = {'category': 'DATA_REFERENCE', 'code': row.get('reason_code', 'REFERENCE_TARGET_UNRESOLVED'),
                'basis': 'stored_reference', **deepcopy(row)}
        required = row.get('reading_policy', {}).get('obligation') in ('REQUIRED', 'CHECK_APPLICABILITY')
        item['blocks_completion'] = required
        (blockers if required else observations).append(item)
    for signature, group in state['deferred'].items():
        blockers.append({'category': 'MODEL_DECISION', 'code': 'MODEL_REFERENCE_DEFERRED',
            'basis': 'accepted_model_decision', **group_detail(group),
            'decision': deepcopy(state['decisions'].get(signature)),
            'decision_recorded': signature in state['decisions']})
    if state.get('needs_more'):
        blockers.append({'category': 'MODEL_DECISION', 'code': 'MODEL_REQUESTED_MORE_REFERENCES',
            'basis': 'accepted_model_decision', 'decision': deepcopy(state.get('last_model_decision')),
            'decision_recorded': state.get('last_model_decision') is not None})
    for group in state['queue']:
        blockers.append({'category': 'UNPROCESSED_WORK', 'code': 'REFERENCE_GROUP_NOT_PROCESSED',
                         'basis': 'navigation_queue', **group_detail(group)})
    for sid in remaining:
        src = session.tools.sources[sid]
        depth = state['depths'].get(sid, 0)
        blockers.append({'category': 'EXECUTION_LIMIT' if depth >= policy['max_depth'] else 'UNPROCESSED_WORK',
            'code': 'REFERENCE_DEPTH_LIMIT' if depth >= policy['max_depth'] else 'ADOPTED_SCOPE_NOT_SCANNED',
            'basis': 'scan_cursor', 'source_id': sid, 'document_id': src['document_id'],
            'document_name': src['document_name'], 'heading': src.get('heading', ''),
            'depth': depth, 'depth_limit': policy['max_depth'],
            'after_reference_id': state['cursors'].get(sid)})
    for limit in limits:
        remaining_only = limit['kind'] == 'reference_work_limit' and not (
            limit.get('work_steps_limit_reached') or limit.get('model_batches_limit_reached'))
        blockers.append({'category': 'UNPROCESSED_WORK' if remaining_only else 'EXECUTION_LIMIT',
                         'code': 'REFERENCE_WORK_REMAINING' if remaining_only else str(limit['kind']).upper(),
                         'basis': 'runtime_limit', **deepcopy(limit)})
    return report('REFERENCE_NAVIGATION', bool(blockers), blockers, observations,
        generation_id=session.context.query['generation_id'], work_steps=work_steps,
        model_batches=model_batches, policy_limits=deepcopy(policy))


def selection_report(result):
    nav = result.get('reference_navigation') or {}
    native = nav.get('diagnostics') or {}
    if result.get('status') == 'complete' and result.get('completion_policy') == 'ALLOW_UNRESOLVED_CONNECTIONS':
        return report('SELECT', False, [],
            [{'category':'MODEL_DECISION','code':'MODEL_DECISION_REJECTED','basis':'recovered_model_decision',**deepcopy(r)}
             for r in result.get('rejected_decisions',[])] +
            ([{'category':'DATA_REFERENCE','code':'UNRESOLVED_CONNECTIONS_ALLOWED','basis':'explicit_completion_policy',
              'reference_navigation':deepcopy(nav)}] if nav.get('pending') else []),
            next_action=result.get('next_action'), selected_source_ids=result.get('final_ids', []),
            sufficiency_reason=result.get('sufficiency_reason'))
    blockers = deepcopy(native.get('blockers', []))
    for rejection in result.get('rejected_decisions', []):
        blockers.append({'category':'MODEL_DECISION','code':'MODEL_DECISION_REJECTED',
            'basis':'rejected_model_decision',**deepcopy(rejection)})
    if result.get('stop_reason'):
        blockers.append({'category':'EXECUTION_LIMIT' if result['stop_reason'] != 'MODEL_DECISION_UNRESOLVED' else 'MODEL_DECISION',
            'code':result['stop_reason'],'basis':'investigation_stop_reason'})
    if nav.get('pending') and not blockers:
        # Historical checkpoints and adapters may lack the detailed contract.
        blockers.append({'category': 'DIAGNOSTIC_GAP', 'code': 'REFERENCE_PENDING_CAUSE_NOT_RECORDED',
            'basis': 'legacy_navigation_result', 'reason': 'pending=true; detailed navigation causes were not recorded'})
    if result.get('status') == 'pending' and not nav.get('pending'):
        blockers.append({'category': 'SOURCE_SELECTION', 'code': result.get('next_action') or 'SELECTION_NEXT_ACTION_NOT_RECORDED',
            'basis': 'selection_result', 'reason': result.get('sufficiency_reason'),
            'search_queries': result.get('search_queries', [])})
    return report('SELECT', result.get('status') == 'pending', blockers,
        deepcopy(native.get('observations', [])), generation_id=native.get('generation_id'),
        next_action=result.get('next_action'), selected_source_ids=result.get('final_ids', []),
        sufficiency_reason=result.get('sufficiency_reason'))


def exception_diagnostics(exc, *, stage=None):
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    location = frames[-1] if frames else None
    out = {'error_code': getattr(exc, 'code', type(exc).__name__),
        'error_type': type(exc).__module__ + '.' + type(exc).__name__,
        'error_message': str(exc), 'stage': stage or getattr(exc, 'failure_stage', None),
        'location': {'file': location.filename, 'line': location.lineno, 'function': location.name} if location else None,
        'traceback': ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}
    if getattr(exc, 'diagnostics', None) is not None:
        out['investigation'] = deepcopy(exc.diagnostics)
    return out


def scoped_report(value, allowed):
    """Do not project a document outside the journal's authenticated scope."""
    def admitted(row):
        if isinstance(row, dict):
            return (row.get('document_id') is None or row['document_id'] in allowed) and all(admitted(v) for v in row.values())
        if isinstance(row, list):
            return all(admitted(v) for v in row)
        return True
    blockers = [r for r in value.get('blockers', []) if admitted(r)]
    observations = [r for r in value.get('observations', []) if admitted(r)]
    return report(value.get('stage'), value.get('pending'), blockers, observations,
                  generation_id=value.get('generation_id'), next_action=value.get('next_action'))
