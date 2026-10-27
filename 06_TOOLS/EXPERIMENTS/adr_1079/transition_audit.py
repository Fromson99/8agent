"""Observe the repaired transition from existing native evidence only.

No transition is forced and missing observations never become a repair pass.
Source/ACL/codec integrity is separately verified by the unweakened cell gate.
"""


def check_transition(audit):
    observations = []
    for event in audit.get('events', []):
        if event.get('kind') != 'NAVIGATION_TASK_PROJECTED':
            continue
        payload = event.get('payload') or {}
        departure = payload.get('departure') or {}
        refs = departure.get('judgment_refs', [])
        if len(set(refs)) < 2 or payload.get('retained_source_count', 0) < 2:
            continue
        journal, seq = event.get('journal'), event.get('seq')
        # The next contract must belong to this exact projection, before another
        # screen is projected. A later unrelated successful screen is not proof.
        later = sorted((row for row in audit.get('events', [])
                        if row.get('journal') == journal and row.get('seq', -1) > seq),
                       key=lambda row: row['seq'])
        contracts = []
        for row in later:
            if row.get('kind') == 'NAVIGATION_TASK_PROJECTED':
                break
            if row.get('kind') == 'NAVIGATION_TASK_CHOICE_CONTRACT':
                contracts.append(row)
        for contract in contracts:
            cp = contract.get('payload') or {}
            pid = cp.get('presentation_id')
            matching = [call for call in audit.get('calls', [])
                        if pid and call.get('presentation_id') == pid
                        and call.get('successful_native_attempts')
                        and any(n.get('journal') == journal for n in call['successful_native_attempts'])
                        and (call.get('task_navigation') or {}).get('context_hash') == payload.get('context_hash')]
            if (cp.get('canonical_validation_required') is not True
                    or cp.get('semantic_defaults_created') is not False):
                continue
            for call in matching:
                observations.append({'journal':journal,'projected_seq':seq,
                    'contract_seq':contract['seq'],'presentation_id':pid,
                    'task':payload.get('task'),'judgment_refs':refs,
                    'retained_source_count':payload['retained_source_count'],
                    'request_path':call.get('request_path'),
                    'request_sha256':call.get('request_sha256')})
    return {'status':'OBSERVED' if observations else 'NOT_OBSERVED',
            'observations':observations,'source_integrity_gate_required':True,
            'quality_certified':False,'automatic_repetition_allowed':False}
