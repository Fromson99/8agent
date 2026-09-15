"""Offline validation of the single legal-semantic-v2 contract.

This tool never approves observations, verifies reviewer identity, mutates a
corpus, or loads the product runtime. Schema validity is not legal correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path('00_SYSTEM/LEGAL_SCHEMA.json')
COLLECTIONS = {'concepts': 'Concept', 'mentions': 'Mention', 'clauses': 'SemanticClause',
               'rules': 'Rule', 'provisos': 'Proviso', 'relations': 'LegalRelation', 'evidence': 'Evidence'}

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()

def load_contract(root=ROOT):
    registry = json.loads((root / REGISTRY).read_text())
    entry = registry['normative_schema']
    path = (root / entry['path']).resolve()
    path.relative_to(root.resolve())
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError('SSOT schema hash drift: review and update registry explicitly')
    schema = json.loads(raw)
    Draft202012Validator.check_schema(schema)
    if schema['$id'] != entry['id'] or schema['x-contract-revision'] != entry['revision']:
        raise ValueError('SSOT schema identity differs from registry')
    if schema['$defs']['Observation']['properties']['schema_version']['const'] != entry['version']:
        raise ValueError('SSOT version differs from registry')
    expected = {row['$ref'].split('/')[-1] for row in schema['oneOf']}
    if expected != set(registry['record_profiles'].values()):
        raise ValueError('Registry profiles do not cover the schema')
    for kind, name in registry['record_profiles'].items():
        if schema['$defs'][name]['properties']['record_kind']['const'] != kind:
            raise ValueError('Registry record kind mismatch')
    return registry, schema

def profile_schema(kind, root=ROOT):
    """Generate consumer/provider schema from SSOT; do not hand-copy fields."""
    registry, schema = load_contract(root)
    name = registry['record_profiles'][kind]
    return {'$schema': schema['$schema'], '$defs': schema['$defs'], '$ref': '#/$defs/' + name}

def validate(record, *, canonical=None, templates=(), sources=None, root=ROOT):
    registry, schema = load_contract(root)
    errors = []
    def require(ok, message):
        if not ok: errors.append(message)
    def shape(value, label):
        found = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
        for error in found:
            errors.append(f'{label}:schema:{list(error.absolute_path)}:{error.message[:240]}')
        require(value.get('schema_sha256') == registry['normative_schema']['sha256'], label + ':schema_hash')
        return not found
    if not shape(record, 'record'): return errors
    if canonical is not None:
        if not shape(canonical, 'canonical'): return errors
        require(canonical['record_kind'] == 'CANONICAL_BUNDLE', 'context:not_canonical_bundle')
        if canonical['record_kind'] != 'CANONICAL_BUNDLE': return errors
        errors.extend(validate(canonical, sources=sources, root=root))
    tmap = {}
    for t in templates:
        if not shape(t, 'template'): continue
        require(t['record_kind'] == 'ASSEMBLY_TEMPLATE', 'context:not_template')
        if t['record_kind'] == 'ASSEMBLY_TEMPLATE':
            require(t['template']['id'] not in tmap, 'duplicate_template_id')
            tmap[t['template']['id']] = t['template']
            errors.extend(validate(t, root=root))

    kind = record['record_kind']
    graph = record.get('payload') or (canonical or {}).get('payload')
    entities = {}
    if graph is not None:
        for collection, typ in COLLECTIONS.items():
            for entity in graph[collection]:
                require(entity['id'] not in entities, 'duplicate_id:' + entity['id'])
                entities[entity['id']] = (typ, entity)
    def lookup(identifier, expected=None):
        row = entities.get(identifier)
        require(row is not None, 'dangling_reference:' + str(identifier))
        if row is not None and expected is not None:
            require(row[0] == expected, f'wrong_reference_type:{identifier}:expected={expected}')
        return row[1] if row else None
    def typed(reference): return lookup(reference['id'], reference['type'])
    def evid(ids):
        for i in ids: lookup(i, 'Evidence')
    def expr(e):
        op = e['operator']
        if op == 'CLAUSE': lookup(e['clause_id'], 'SemanticClause')
        elif op in ('ALL', 'ANY'):
            for item in e['operands']: expr(item)
        elif op == 'NOT': expr(e['operand'])
        else: evid(e['evidence_ids'])
    def resolved(row, field):
        if row['resolution'] == 'RESOLVED':
            require(row[field] is not None and row['unresolved_reason'] is None, 'invalid_resolved:' + field)
        else:
            require(row[field] is None and bool(row['unresolved_reason']), 'invalid_unresolved:' + field)

    if kind in ('OBSERVATION', 'CANONICAL_BUNDLE'):
        source_map = {}
        if sources is not None:
            for source in sources:
                key = (source['document_version_id'], source['block_id'])
                require(key not in source_map, 'duplicate_source_block:' + str(key))
                source_map[key] = source
        for e in graph['evidence']:
            require(e['end'] > e['start'], 'invalid_evidence_range:' + e['id'])
            require(e['end'] - e['start'] == len(e['quote']), 'evidence_length:' + e['id'])
            require(e['quote_sha256'] == hashlib.sha256(e['quote'].encode()).hexdigest(), 'quote_hash:' + e['id'])
            require(e['document_version_id'] in record['scope']['document_version_ids'], 'evidence_outside_scope:' + e['id'])
            if sources is not None:
                source = source_map.get((e['document_version_id'], e['block_id']))
                require(source is not None, 'source_block_missing:' + e['id'])
                if source:
                    require(source['source_artifact_sha256'] == e['source_artifact_sha256'], 'source_hash:' + e['id'])
                    require(source['text'][e['start']:e['end']] == e['quote'], 'source_quote:' + e['id'])
        for collection in COLLECTIONS:
            if collection != 'evidence':
                for row in graph[collection]: evid(row['evidence_ids'])
        for c in graph['concepts']:
            for i in c['definition_rule_ids']:
                r = lookup(i, 'Rule')
                if r: require(r['rule_type'] == 'DEFINITION', 'nondefinition_rule:' + i)
        for m in graph['mentions']:
            resolved(m, 'concept_id')
            if m['concept_id'] is not None: lookup(m['concept_id'], 'Concept')
            quotes = [entities[i][1]['quote'] for i in m['evidence_ids'] if i in entities and entities[i][0] == 'Evidence']
            require(any(m['surface'] in q for q in quotes), 'mention_surface:' + m['id'])
        for c in graph['clauses']:
            require(sum(b['role'] == 'PREDICATE' for b in c['role_bindings']) == 1, 'clause_predicate:' + c['id'])
            for b in c['role_bindings']:
                resolved(b, 'concept_id'); evid(b['evidence_ids'])
                require(set(b['evidence_ids']) <= set(c['evidence_ids']), 'role_evidence_outside_clause:' + c['id'])
                if b['concept_id'] is not None: lookup(b['concept_id'], 'Concept')
                for i in b['mention_ids']:
                    m = lookup(i, 'Mention')
                    if m: require(m['concept_id'] == b['concept_id'], 'role_mention_concept:' + i)
        for r in graph['rules']:
            expr(r['applicability']); expr(r['antecedent'])
            for i in r['consequent_clause_ids']: lookup(i, 'SemanticClause')
            if r['valid_from'] and r['valid_until']:
                require(r['valid_from'] < r['valid_until'], 'rule_validity_interval:' + r['id'])
        for r in graph['relations']:
            typed(r['source']); resolved(r, 'target')
            if r['target'] is not None: typed(r['target'])
        for p in graph['provisos']:
            lookup(p['attached_rule_id'], 'Rule'); expr(p['condition'])
            for i in p['outcome_clause_ids']: lookup(i, 'SemanticClause')
            if p['completion_type'] == 'EXTERNAL':
                require(bool(p['dependency_relation_ids']), 'external_proviso_without_dependency:' + p['id'])
            if p['completion_type'] == 'INTERNAL':
                require(not p['dependency_relation_ids'], 'internal_proviso_with_dependency:' + p['id'])
            for i in p['dependency_relation_ids']:
                r = lookup(i, 'LegalRelation')
                if r:
                    require(r['source'] == {'type': 'Proviso', 'id': p['id']}, 'proviso_dependency_source:' + i)
                    require(r['predicate'] == 'DEPENDS_ON_REQUIREMENTS_OF', 'proviso_dependency_predicate:' + i)
                    if r['target']: require(r['target']['type'] == 'Rule', 'proviso_dependency_target:' + i)
        for x in graph['crosswalk']:
            require(bool(x['target_refs']) == (x['status'] == 'MAPPED'), 'invalid_crosswalk:' + x['legacy_id'])
            for target in x['target_refs']: typed(target)
        if kind == 'OBSERVATION' and record['provenance']['method'] == 'LLM':
            require(bool(record['provenance']['prompt_sha256']) and bool(record['provenance']['provider_receipt_sha256']), 'llm_provenance_missing')

    if kind == 'ASSEMBLY_TEMPLATE':
        slots = record['template']['slots']
        require(len({s['slot'] for s in slots}) == len(slots), 'duplicate_template_slot')
    if kind in ('QUERY_PLAN', 'RULE_BUNDLE', 'FEEDBACK'):
        require(canonical is not None, 'canonical_context_required')
        if canonical is not None: require(record['scope'] == canonical['scope'], 'scope_mismatch')
    if kind == 'QUERY_PLAN':
        require(len({c['id'] for c in record['cards']}) == len(record['cards']), 'duplicate_query_card')
        for card in record['cards']:
            template = tmap.get(card['template_id']); require(template is not None, 'template_missing')
            require(set(card['document_version_ids']) <= set(record['scope']['document_version_ids']), 'query_document_outside_scope')
            require(bool(card['document_version_ids']) or bool(card['unresolved_reason']), 'unresolved_query_scope_reason')
            keys = [f['key'] for f in card['facts']]
            require(len(keys) == len(set(keys)), 'duplicate_fact_key')
            require(not (set(keys) & set(card['missing_fact_keys'])), 'fact_both_present_and_missing')
            if template: require(set(template['required_fact_keys']) <= set(keys) | set(card['missing_fact_keys']), 'unaccounted_required_fact')
            for fact in card['facts']:
                require(fact['end'] > fact['start'] and record['question'][fact['start']:fact['end']] == fact['quote'], 'question_fact_quote')
                for i in fact['concept_candidates']: lookup(i, 'Concept')
    if kind == 'RULE_BUNDLE':
        template = tmap.get(record['template_id']); require(template is not None, 'template_missing')
        if canonical:
            require(record['canonical_generation_id'] == canonical['generation_id'], 'generation_mismatch')
            require(record['canonical_payload_sha256'] == digest(canonical['payload']), 'canonical_payload_hash')
        for i in record['entry_rule_ids']: lookup(i, 'Rule')
        for i in record['unresolved_relation_ids']:
            rel = lookup(i, 'LegalRelation')
            if rel: require(rel['resolution'] == 'UNRESOLVED', 'resolved_relation_in_unresolved_list')
        slots = record['slots']; require(len({s['slot'] for s in slots}) == len(slots), 'duplicate_bundle_slot')
        specs = {s['slot']: s for s in template['slots']} if template else {}
        for slot in slots:
            require(slot['slot'] in specs, 'undeclared_bundle_slot:' + slot['slot'])
            require(bool(slot['refs']) == (slot['state'] == 'PRESENT'), 'slot_state_refs:' + slot['slot'])
            if slot['state'] != 'PRESENT': require(bool(slot['reason']), 'missing_slot_reason:' + slot['slot'])
            for target in slot['refs']:
                typed(target)
                require(target['type'] in specs.get(slot['slot'], {}).get('allowed_types', []), 'slot_reference_type:' + slot['slot'])
        by_slot = {s['slot']: s for s in slots}
        if template: require(set(specs) == set(by_slot), 'template_slots_not_accounted')
        if record['structural_completeness'] == 'COMPLETE':
            require(not record['unresolved_relation_ids'], 'complete_with_unresolved_relations')
            for name, spec in specs.items():
                if spec['required']: require(by_slot.get(name, {}).get('state') == 'PRESENT', 'complete_missing_required:' + name)
    if kind == 'FEEDBACK':
        if canonical: require(record['canonical_generation_id'] == canonical['generation_id'], 'feedback_generation_mismatch')
        for change in record['changes']:
            typed(change['target_ref']); evid(change['evidence_ids'])
            require(change['field_pointer'].startswith('/'), 'invalid_field_pointer')
    return errors

def check_examples(root=ROOT):
    directory = root / '01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2'
    records = {name: json.loads((directory / (name + '.json')).read_text())
               for name in ('observation', 'canonical', 'template', 'query', 'bundle', 'feedback')}
    sources = json.loads((directory / 'source-blocks.json').read_text())
    errors = []
    for name, record in records.items():
        context = {} if name in ('observation', 'canonical', 'template') else {'canonical': records['canonical'], 'templates': [records['template']]}
        errors.extend(f'{name}:{error}' for error in validate(record, sources=sources, root=root, **context))
    return errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', help='emit a schema derived from SSOT')
    parser.add_argument('--check', action='store_true', help='check registry and all illustrative profiles')
    args = parser.parse_args()
    if args.profile: print(json.dumps(profile_schema(args.profile), ensure_ascii=False, indent=2)); return
    errors = check_examples()
    print(json.dumps({'ok': not errors, 'errors': errors, 'profiles': 6,
                      'approval_verified': False, 'runtime_migrated': False}, ensure_ascii=False))
    raise SystemExit(bool(errors))

if __name__ == '__main__': main()
