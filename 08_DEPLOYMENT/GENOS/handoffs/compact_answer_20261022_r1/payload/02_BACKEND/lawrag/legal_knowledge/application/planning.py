"""Bounded advisory plans; execution/facts/source receipts remain caller-owned."""
from ..contracts import digest
from ..ontology import evaluate, scope_status


def assemble(base, records, context, facts, *, as_of=None):
    from . import ref
    items, seen = [], set()
    for record in records:
        reference = ref(record)
        if digest(reference) in seen: continue
        seen.add(digest(reference))
        definition, content = record['definition'], record['definition']['content']
        status, missing = scope_status(definition['scope'], context)
        if as_of is None:
            missing = [*missing, 'AS_OF_UNSPECIFIED']
            if status == 'MATCHED': status = 'UNRESOLVED'
        elif ((definition['effective_from'] and as_of < definition['effective_from']) or
              (definition['effective_to'] and as_of > definition['effective_to'])):
            status = 'NOT_APPLICABLE'; missing = [*missing, 'OUTSIDE_EFFECTIVE_PERIOD']
        elif not definition['effective_from']:
            status = 'UNRESOLVED'; missing = [*missing, 'EFFECTIVE_PERIOD_UNVERIFIED']
        receipts = []
        if 'condition' in content:
            condition = evaluate(content['condition'], facts, binding=base['binding'])
            receipts.append(condition)
            if condition['status'] == 'FALSE': status = 'NOT_APPLICABLE'
            elif condition['status'] != 'TRUE': status = 'UNRESOLVED'
            missing.extend(condition['missing'])
        for field in content.get('inputs', []) + content.get('input_refs', []):
            if field['id'] not in facts: missing.append(field['id'])
        policies = []
        for policy in content.get('policies', []):
            decision = evaluate(policy['condition'], facts, binding=base['binding'])
            reopen = evaluate(policy['reopen_condition'], facts, binding=base['binding'])
            # Even a TRUE skip proposal is advisory until the host binds actual facts.
            proposed = status == 'MATCHED' and decision['status'] == 'TRUE' and reopen['status'] == 'FALSE'
            policies.append({'target': policy['target'], 'effect': policy['effect'],
                             'eligible': proposed, 'reason': 'CONDITION_MATCHED' if proposed else 'CONTINUE_RESEARCH',
                             'decision': decision, 'reopen': reopen})
        items.append({'ref': reference, 'title': definition['title'], 'description': definition['description'],
            'kind': definition['kind'], 'application_status': status, 'semantic_status': 'UNASSESSED',
            'execution_status': 'READY' if status == 'MATCHED' else 'PARTIAL', 'missing': sorted(set(missing)),
            'steps': content.get('steps', []), 'source_refs': definition['source_refs'],
            'wiki_refs': content.get('wiki_refs', []), 'policies': policies, 'decision_receipts': receipts,
            'role': 'REVIEW_GUIDANCE_NOT_EVIDENCE'})
        if len(items) == 12: break
    from ..contracts import validate, PLAN
    return validate({**base, 'items': items, 'plan_hash': digest([base['binding'], context, facts, as_of, items])}, PLAN)
