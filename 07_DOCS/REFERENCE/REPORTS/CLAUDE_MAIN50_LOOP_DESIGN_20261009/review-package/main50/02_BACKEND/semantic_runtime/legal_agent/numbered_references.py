"""Pure request-local wire aliases. Persistent/public contracts retain original IDs."""
from copy import deepcopy
from jsonschema import Draft202012Validator, ValidationError
from .errors import ProposalError

# Only reference slots are transformed. Legal numbers, quotes, coordinates,
# requirements, reasons, offsets and fact_dependencies are never rewritten.
FIELDS = {
    'source': 'sources', 'evidence': 'sources', 'evidence_id': 'sources',
    'evidence_ids': 'sources', 'source_evidence': 'sources', 'target_evidence': 'sources',
    'valid_sources': 'sources',
    'question_ref': 'questions', 'question_refs': 'questions', 'context_refs': 'questions',
    'obligation': 'obligations', 'obligation_refs': 'obligations',
    'claim': 'claims', 'claims': 'claims', 'claim_ids': 'claims',
    'target': 'targets', 'candidate_id': 'targets', 'corpus_root': 'targets',
    'focus': 'targets', 'parent': 'targets', 'document': 'targets',
    'scope_root': 'targets', 'breadcrumb': 'targets', 'candidate': 'targets', 'route': 'targets',
    'offered_handles': 'targets', 'term_target': 'targets', 'terms': 'targets',
    'relation_id': 'relations', 'related_relation_ids': 'relations',
    'relation_dependencies': 'relations', 'relation_checks': 'relations',
    'block_id': 'blocks', 'cursor': 'cursors', 'next_cursor': 'cursors',
}
CARD_IDS = {'question_pieces': 'questions', 'questions': 'questions',
            'demands': 'obligations', 'answer_obligations': 'obligations',
            'claims': 'claims', 'current_claims': 'claims'}
PRIVATE = {'view_id', 'goal_id', 'source_id', 'document_id', 'document_ids',
           'unit_id', 'block_hash', 'span_hash', 'source_artifact_hash',
           'selection_id', 'observation_id', 'reference_id', 'term_id',
           'semantic_hash', 'text_hash', 'source_hash', 'generation_id',
           'generation_fingerprint', 'decision_hash', 'request_hash'}
INSTRUCTIONS = (
    ' Reference fields use integer choices shown in this request. Sources, question segments, '
    'answer demands, claims, navigation targets, relations, blocks and cursors have separate '
    'number lists; the same number in different fields can mean different things. '
    'Copy the number from the matching card/field; never output original IDs, card text, '
    'or quoted numbers in reference fields. Numbers are valid only for this request. '
    'Do not renumber article headings, legal quantities or quoted text. '
    'For tool arguments copy the supplied numbered action. '
)


def walk(value):
    if isinstance(value, dict):
        yield value
        for key in sorted(value):
            yield from walk(value[key])
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class NumberedReferences:
    def __init__(self, view):
        self.ids = {kind: [] for kind in set(FIELDS.values())}
        def add(kind, ident):
            if isinstance(ident, str) and ident and ident not in self.ids[kind]:
                self.ids[kind].append(ident)
        for row in view.get('exact_evidence', []):
            add('sources', row.get('evidence') or row.get('source'))
        for row in view.get('question_pieces', view.get('questions', [])):
            if isinstance(row, dict): add('questions', row.get('id') or row.get('question_ref'))
        for row in (view.get('question_plan') or {}).get('demands', []):
            add('obligations', row.get('id'))
        for row in view.get('answer_obligations', []):
            add('obligations', row.get('id') or row.get('obligation'))
        for row in view.get('claims', view.get('current_claims', [])):
            if isinstance(row, dict): add('claims', row.get('claim') or row.get('entity_id') or row.get('id'))
        for ident in view.get('offered_handles', []): add('targets', ident)
        add('targets', view.get('corpus_root'))
        # Navigation and span references are supplied by the server in cards or
        # executable actions. Semantic reference choices come ONLY from cards above.
        for row in walk(view):
            for key, value in sorted(row.items()):
                kind = FIELDS.get(key)
                if kind in ('targets', 'relations', 'blocks', 'cursors'):
                    for ident in value if isinstance(value, list) else [value]: add(kind, ident)
        self.forward = {kind: {ident: i for i, ident in enumerate(ids, 1)} for kind, ids in self.ids.items()}

    def project(self, value, container=None):
        if isinstance(value, list):
            return [self.project(v, container) for v in value]
        if not isinstance(value, dict): return deepcopy(value)
        out = {}
        for key, item in value.items():
            if key in PRIVATE or key.endswith('_sha256'): continue
            kind = CARD_IDS.get(container) if key in ('id', 'entity_id') else FIELDS.get(key)
            if key in ('id', 'entity_id') and kind is None: continue
            if kind and (isinstance(item, str) or isinstance(item, list) and all(isinstance(x, str) for x in item)):
                # Historical/stale identifiers are not selectable in this request.
                # Explicit null/[] preserves the distinction from a valid choice.
                out[key] = ([self.forward[kind][x] for x in item if x in self.forward[kind]]
                            if isinstance(item, list) else self.forward[kind].get(item))
            else:
                out[key] = self.project(item, key)
        return out

    def view(self, view):
        projected = self.project(view)
        projected['reference_numbers'] = {kind: list(range(1, len(ids)+1)) for kind, ids in self.ids.items()}
        projected['navigation_choices'] = [
            {'target': i, 'kind': {'R': 'corpus', 'F': 'folder', 'D': 'document',
                                  'P': 'candidate', 'U': 'unit', 'T': 'term',
                                  'L': 'route', 'E': 'evidence'}.get(ident[:1], 'location')}
            for i, ident in enumerate(self.ids['targets'], 1)]
        return projected

    def schema(self, original):
        def ref(node, kind):
            if node.get('type') == 'array':
                result = deepcopy(node)
                result['items'] = ref(node['items'], kind)
                if not self.ids[kind]:
                    # The request has no selectable references. Keep the wire
                    # grammar satisfiable; the original contract still rejects
                    # a required reference if a proposal supplies an empty list.
                    result['minItems'] = 0
                    result['maxItems'] = 0
                return result
            nullable = node.get('type') == ['string', 'null'] or any(
                x.get('type') == 'null' for x in node.get('anyOf', []))
            # Empty enum is legal JSON Schema but poorly supported by providers.
            # A null-only choice cannot satisfy a nonnullable server reference.
            choice = {'type': 'integer', 'enum': list(range(1, len(self.ids[kind])+1))} if self.ids[kind] else {'type': 'null'}
            return {'anyOf': [choice, {'type': 'null'}]} if nullable and self.ids[kind] else choice
        def convert(node):
            if isinstance(node, list): return [convert(v) for v in node]
            if not isinstance(node, dict): return deepcopy(node)
            result = {k: convert(v) for k, v in node.items() if k != 'properties'}
            if 'properties' in node:
                result['properties'] = {k: ref(v, FIELDS[k]) if k in FIELDS else convert(v)
                                        for k, v in node['properties'].items()}
            return result
        result = convert(original)
        # Fix complete-review cardinality for both review kinds. Uniqueness and
        # cross-reference semantics remain enforced by the existing session.
        for field, kind in [('checks', 'claims'), ('obligation_checks', 'obligations')]:
            if field in result.get('properties', {}):
                result['properties'][field].update(minItems=len(self.ids[kind]), maxItems=len(self.ids[kind]))
        return result

    def decode(self, value, wire_schema, schema_name=None):
        envelope = deepcopy(wire_schema)
        # Keep the inherited partial-operation contract. Malformed non-reference
        # fields are handled independently by the session, preserving successful
        # selections/actions. Reference slots are ALWAYS checked below.
        if schema_name == 'TurnDecision':
            for key in ('actions', 'assessments', 'relation_assessments'):
                envelope['properties'][key]['items'] = {}
            envelope['properties']['source_selection'] = {'type': ['object', 'null']}
        elif schema_name == 'SourceSelectionDecision':
            envelope['properties']['choices']['items'] = {}
        try: Draft202012Validator(envelope).validate(value)
        except ValidationError as exc:
            path = '/'.join(map(str, exc.absolute_path))
            raise ProposalError('Numbered response at /'+path+': '+exc.message) from exc
        def convert(item, node):
            if 'oneOf' in node or 'anyOf' in node:
                branches = node.get('oneOf', node.get('anyOf'))
                match = next((b for b in branches if Draft202012Validator(b).is_valid(item)), None)
                if match is None and isinstance(item, dict) and isinstance(item.get('tool'), str):
                    # TurnDecision deliberately accepts malformed individual actions
                    # so other actions/selections can survive. Recover the branch by
                    # its fixed tool name before local validation: otherwise numbered
                    # target/question references stay as integers and the repair
                    # reports a misleading reference/type error instead of the
                    # actual invalid field.
                    named = [b for b in branches if b.get('properties', {}).get('tool', {}).get('const') == item['tool']]
                    if len(named) == 1:
                        match = named[0]
                if match is not None: return convert(item, match)
            if isinstance(item, list): return [convert(v, node.get('items', {})) for v in item]
            if not isinstance(item, dict): return deepcopy(item)
            out = {}
            for key, val in item.items():
                child = node.get('properties', {}).get(key, {})
                if key in FIELDS:
                    kind = FIELDS[key]
                    def resolve(number):
                        if number is None:
                            # A null cursor is an explicit first page; other
                            # empty reference sets must never invent an ID.
                            if key == 'cursor': return None
                            raise ProposalError('No current choices for '+key)
                        if type(number) is not int or not 1 <= number <= len(self.ids[kind]):
                            raise ProposalError('Invalid numbered choice for '+key)
                        return self.ids[kind][number-1]
                    out[key] = [resolve(n) for n in val] if isinstance(val, list) else resolve(val)
                else: out[key] = convert(val, child)
            return out
        return convert(value, wire_schema)

    def receipt(self, view):
        return {'view_id': view.get('view_id'), 'base_state_revision': view.get('base_state_revision'),
                'evidence_revision': view.get('evidence_revision'), 'number_to_id': deepcopy(self.ids)}
