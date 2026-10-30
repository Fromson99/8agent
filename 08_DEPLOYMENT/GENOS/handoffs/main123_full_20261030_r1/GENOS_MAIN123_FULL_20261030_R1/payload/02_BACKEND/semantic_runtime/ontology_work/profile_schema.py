"""Closed, generated contracts shared by authoring, review and compilation."""
from copy import deepcopy
from .schema import obj, arr, text

REF = {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_:-]{0,159}$'}
HASH = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
LOCATOR = obj({'payload_hash': HASH, 'pointer': {'type': 'string', 'maxLength': 2000},
               'start': {'type': 'integer', 'minimum': 0},
               'end': {'type': 'integer', 'minimum': 1}, 'quote': text(16000)})
BASIS = obj({'source': REF, 'quote': text(16000)})
STATES = ['PRESENT', 'NOT_RECORDED', 'UNSPECIFIED', 'NOT_APPLICABLE',
          'NOT_ACQUIRED', 'CONFLICTED', 'UNSUPPORTED_SEMANTICS']
MISSING = obj({'state': {'enum': STATES[1:]}, 'value': {'type': 'null'},
               'locators': arr(LOCATOR)})
GLOSSARY_LINK = obj({'concept_id': text(160), 'state': {'enum': [
    'CANDIDATE', 'CONTEXT_LINKED', 'AMBIGUOUS', 'UNRESOLVED']},
    'mention_refs': arr(LOCATOR, 1), 'reason': text()})


def slot_schema(slot):
    types = {'TEXT': text(), 'NUMBER': {'type': 'number'}, 'BOOLEAN': {'type': 'boolean'},
             'DATE': {'type': 'string', 'format': 'date'}, 'SET': arr(text()), 'NODE_REFS': arr(REF)}
    value = deepcopy(types[slot['value_type']])
    if slot['allowed_values'] is not None:
        value = {'enum': slot['allowed_values']}
    return {'anyOf': [obj({'state': {'const': 'PRESENT'}, 'value': value,
                          'locators': arr(LOCATOR, 1)}), deepcopy(MISSING)]}


def node_schema(profile, *, observation):
    slots = {s['id']: s for s in profile['slots']}
    variants = []
    for kind in profile['node_types']:
        values = {key: slot_schema(s) for key, s in slots.items()}
        # Knowledge provenance is in source basis, not invented raw locators.
        if not observation:
            for v in values.values():
                for branch in v['anyOf']:
                    branch['required'].remove('locators')
                    del branch['properties']['locators']
        fields = {'id': REF, 'kind': {'const': kind['kind']},
                  'slots': {'type': 'object', 'additionalProperties': False,
                            'required': kind['required_review_slots'], 'properties': values}}
        if not observation:
            fields.update(text=text(16000), basis=arr(BASIS, 1),
                          observation_refs=arr(REF, 1), glossary_refs=arr(text(160)))
        variants.append(obj(fields))
    return {'anyOf': variants}


def observation_schema(profile):
    field = {'anyOf': [obj({'state': {'const': 'PRESENT'}, 'value': text(16000),
                           'locators': arr(LOCATOR, 1)}), deepcopy(MISSING)]}
    observation = obj({'id': REF, 'kind': {'enum': ['QUESTION', 'CLAIM', 'DECISION',
        'CORRECTION', 'FINAL_USE', 'FAILURE', 'INCOMPLETE']},
        **{k: deepcopy(field) for k in ('statement', 'reason', 'purpose', 'scope')},
        'previous_refs': arr(LOCATOR), 'semantic_elements': arr(node_schema(profile, observation=True)),
        'glossary_refs': arr(GLOSSARY_LINK), 'source_claims': arr(LOCATOR), 'unresolved': arr(text())})
    return obj({'observations': arr(observation), 'coverage': arr(obj({
        'pointer': {'type': 'string'}, 'state': {'enum': ['USED', 'NON_JUDGMENT', 'NEEDS_CONTEXT']},
        'observation_ids': arr(REF), 'reason': text()}), 1, 2048), 'unresolved': arr(text())})


def graph_schema(profile):
    return obj({'nodes': arr(node_schema(profile, observation=False), 1),
        'edges': arr(obj({'id': REF, 'type': {'enum': [r['id'] for r in profile['relations']]},
                         'from': REF, 'to': REF, 'basis': arr(BASIS, 1)})),
        'purposes': arr(obj({'id': REF, 'purpose': {'enum': [p['id'] for p in profile['purposes']]},
                            'roots': arr(REF, 1), 'title': text(240)}), 1),
        'unused_nodes': arr(obj({'id': REF, 'reason': text()})), 'unresolved': arr(text())})


def accumulation_schema(profile):
    return obj({'graph': graph_schema(profile), 'comparisons': arr(obj({
        'observation_ref': REF, 'relation': {'enum': ['NEW', 'SAME', 'COMPLEMENT', 'SPECIALIZATION',
            'CONTRADICTION', 'DIFFERENT_SCOPE', 'VERSION_CHANGE']},
        'verdict': {'enum': ['SUPPORTED', 'CONTRADICTED', 'PARTIAL', 'UNKNOWN']},
        'reason': text(), 'basis': arr(BASIS), 'node_ids': arr(REF)}), 1),
        'removed_nodes': arr(obj({'id': REF, 'reason': text(), 'basis': arr(BASIS, 1)}))})
