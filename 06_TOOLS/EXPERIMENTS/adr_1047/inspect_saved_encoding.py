"""Static saved-payload representation accounting, not a product replay.

Reads eleven historical JSON requests, imports only pure frozen codecs, and
writes lengths/hashes/statuses. No credentials, HTTP, source DB, model or service.
Unknown caller reconstruction is excluded rather than estimated. Bytes are not
tokens, wall time, quality or a prediction of future model decisions.
"""
from copy import deepcopy
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-1047-ontology-mvp-state-format/artifacts'
CODE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1047/state-format-r10/revisions/rev-001/snapshot'
OLD = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1045/compiler-r8/revisions/rev-001/snapshot'
LEDGER = ROOT / '04_EXPERIMENTS/ADR/ADR-1045-ontology-mvp-terminal-frame/artifacts/input-repetition-analysis.json'
R9 = ROOT / '04_EXPERIMENTS/ADR/ADR-1046-ontology-mvp-shared-io/artifacts/saved-encoding-check.json'
REL = Path('02_BACKEND/semantic_runtime/legal_agent')
MAPS = ('properties', 'patternProperties', 'dependentSchemas')
SINGLE = ('items', 'additionalProperties', 'unevaluatedProperties', 'not', 'if', 'then',
          'else', 'contains', 'propertyNames')
ARRAYS = ('anyOf', 'oneOf', 'allOf', 'prefixItems')


class Unmeasured(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Unmeasured(reason)


def pack(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def size(value): return len(pack(value).encode('utf-8'))
def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
def ref(path): return {'path': str(Path(path).relative_to(ROOT)), 'sha256': sha(path)}
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def literal(path, symbol, *, conditional_body=False):
    """Read literal assignments without executing a caller or importing its DB."""
    module = ast.parse(Path(path).read_text(encoding='utf-8'))
    env = {}
    def value(node):
        if isinstance(node, ast.Name): return env[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return value(node.left) + value(node.right)
        return ast.literal_eval(node)
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            try:
                result = value(statement.value)
            except (KeyError, ValueError, TypeError):
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name): env[target.id] = result
    if symbol in env:
        return env[symbol]
    if conditional_body:
        values = [value(node.value.body) for node in ast.walk(module)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.IfExp)
            and any(isinstance(t, ast.Name) and t.id == symbol for t in node.targets)]
        require(len(values) == 1, 'AMBIGUOUS_CALLER_LITERAL')
        return values[0]
    raise Unmeasured('CALLER_LITERAL_NOT_AVAILABLE')


def schema_inline(schema):
    """Only standalone local root $defs references; literals are never schemas."""
    definitions = schema.get('$defs', {})
    def resolve(node, stack=(), root=False):
        if not isinstance(node, dict): return deepcopy(node)
        if '$ref' in node:
            require(set(node) == {'$ref'}, 'REF_SIBLING_CONSTRAINT_UNSUPPORTED')
            target = node['$ref']
            require(isinstance(target, str) and target.startswith('#/$defs/'), 'NONLOCAL_REF_UNSUPPORTED')
            key = target[8:]
            require(key in definitions and key not in stack, 'MISSING_OR_CYCLIC_REF')
            return resolve(definitions[key], stack + (key,))
        require(not any(k in node for k in ('$id', '$anchor', '$dynamicRef', '$dynamicAnchor',
            '$recursiveRef', '$recursiveAnchor', 'definitions')), 'SCOPED_SCHEMA_UNSUPPORTED')
        require(root or '$defs' not in node, 'NESTED_DEFINITIONS_UNSUPPORTED')
        result = {k: deepcopy(v) for k, v in node.items() if k != '$defs'}
        for key in MAPS:
            if key in result: result[key] = {name: resolve(v, stack) for name, v in result[key].items()}
        for key in SINGLE:
            if isinstance(result.get(key), dict): result[key] = resolve(result[key], stack)
            elif isinstance(result.get(key), list): result[key] = [resolve(v, stack) for v in result[key]]
        for key in ARRAYS:
            if key in result: result[key] = [resolve(v, stack) for v in result[key]]
        return result
    return resolve(schema, root=True)


def old_module(name):
    path = OLD / REL / (name + '.py')
    spec = importlib.util.spec_from_file_location('semantic_runtime.legal_agent._saved_r8_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_known(system, old, new, label, changes, *, required=False):
    count = system.count(old)
    require(count <= 1 and (not required or count == 1), 'GUIDANCE_OCCURRENCE_' + label)
    if count:
        changes.append({'kind': label, 'before_sha256': digest(old), 'after_sha256': digest(new),
            'before_utf8_bytes': len(old.encode()), 'after_utf8_bytes': len(new.encode())})
        return system.replace(old, new, 1)
    return system


def remove_old_aliases(request, expanded, aliases):
    system = request['messages'][0]['content']
    marker = '\nOutput keys only: '
    if marker not in system:
        require(not aliases.Codec(expanded).changed, 'MISSING_ALIAS_LEGEND')
        return expanded, system
    require(system.count(marker) == 1, 'AMBIGUOUS_ALIAS_LEGEND')
    suffix = '. Input keys keep their original names. Use the output schema keys; keep all values, IDs and quoted text unchanged.'
    start = system.index(marker)
    end = system.find(suffix, start)
    require(end >= 0, 'UNRECOGNIZED_ALIAS_LEGEND')
    pairs = system[start + len(marker):end].split(', ')
    forward = dict(pair.split('=') for pair in pairs)
    require(len(forward) == len(pairs) and len(set(forward.values())) == len(forward), 'AMBIGUOUS_ALIAS_MAPPING')
    require(all(aliases.ALIASES.get(k) == v for k, v in forward.items()), 'UNRECOGNIZED_ALIAS_MAPPING')
    canonical = aliases._schema(expanded, {v: k for k, v in forward.items()})
    codec = aliases.Codec(canonical)
    require(codec.forward == forward and codec.wire == expanded, 'ALIAS_SCHEMA_NOT_REVERSIBLE')
    return canonical, system[:start] + system[end + len(suffix):]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-root', type=Path, default=CODE)
    parser.add_argument('--output', type=Path, default=ART / 'saved-encoding-check.json')
    args = parser.parse_args()
    code = args.code_root.resolve()
    require(code == CODE.resolve(), 'FINAL_FROZEN_R10_REQUIRED')
    require(not args.output.exists(), 'REFUSE_EXISTING_ARTIFACT')
    manifest_path = code.parents[2] / 'candidate.json'
    files = {row['target_path']: row['snapshot_sha256'] for row in read(manifest_path)['files']}
    require(all(sha(code / p) == h for p, h in files.items()), 'FROZEN_CODE_HASH_MISMATCH')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(code / '02_BACKEND'))
    from semantic_runtime.legal_agent import input_guidance, minimal_output
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    from semantic_runtime.legal_agent.shared_input_values import compact_shared_values, expand_shared_values
    from semantic_runtime.legal_agent.model_input_projection import prepare_variants
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    from semantic_runtime.legal_agent.buffered_external_transport import COMPACT_JSON_INSTRUCTION
    from semantic_runtime.legal_agent.read_connection_guidance import READ_CONNECTION_PROMPT
    from semantic_runtime.legal_agent.wire_schema import factor_schema
    old_factor, old_aliases = old_module('wire_schema'), old_module('output_key_aliases')
    policy = read(code / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    transport = SimpleNamespace(policy=policy, binding={'model': policy['model']},
                                response_reception='buffered-json-sse-v1')
    def preview(body):
        return LocalGemmaTransport.preview_request(transport, body)
    old_nav = literal(OLD / REL / 'navigation_input.py', 'INSTRUCTIONS') + ' ' + input_guidance.TEXT
    old_minimal = literal(OLD / REL / 'minimal_output.py', 'INSTRUCTIONS')
    old_stream = literal(OLD / REL / 'buffered_external_transport.py', 'COMPACT_JSON_INSTRUCTION')
    old_selection = literal(OLD / REL / 'structure_selection.py', 'PROMPT')
    old_choice = literal(OLD / REL / 'decision_projection.py', 'EXECUTABLE_CHOICE_PROMPT')
    old_scope = literal(OLD / REL / 'decision_projection.py', 'scope_prompt', conditional_body=True)
    new_choice = literal(code / REL / 'decision_projection.py', 'EXECUTABLE_CHOICE_PROMPT')
    ledger, r9 = read(LEDGER), read(R9)
    comparison = {(row['cell'], row['call']): row for row in r9['calls']}
    rows = []
    for call in ledger['calls']:
        path = ROOT / call['request']['path']
        source_hash = sha(path)
        row = {'cell': call['cell'], 'call': call['call'], 'source_request': ref(path),
               'historical_http_status': call['http_status'], 'status': 'UNMEASURED'}
        try:
            require(source_hash == call['request']['sha256'], 'SAVED_REQUEST_HASH_MISMATCH')
            before = read(path)
            require(len(before['messages']) == 2 and before['messages'][0]['role'] == 'system'
                    and before['messages'][1]['role'] == 'user', 'CALLER_MESSAGE_SHAPE_UNSUPPORTED')
            require(before['model'] == policy['model'] and before['provider'] == policy['provider_routing']
                    and before['reasoning'] == policy['reasoning'], 'SAVED_MODEL_POLICY_MISMATCH')
            require(not any(k in before for k in ('max_tokens', 'max_completion_tokens', 'max_output_tokens')),
                    'SAVED_OUTPUT_CAP_UNEXPECTED')
            payload = json.loads(before['messages'][1]['content']); view = payload['view']
            stage = view.get('source_stage'); row['stage'] = stage
            schema = before['response_format']['json_schema']['schema']
            expanded = schema_inline(schema)
            require(old_factor.factor_schema(expanded) == schema, 'OLD_FACTORING_IDENTITY_NOT_PROVEN')
            canonical, _ = remove_old_aliases(before, expanded, old_aliases)
            require(schema_inline(factor_schema(expanded)) == expanded, 'NEW_FACTORING_NOT_EXACT')
            factored = deepcopy(before)
            factored['response_format']['json_schema']['schema'] = factor_schema(expanded)
            guided = deepcopy(factored); changes = []
            system = guided['messages'][0]['content']
            v3 = view.get('input_projection') == 'compact-selection-source-v3'
            if v3:
                system = replace_known(system, old_nav, input_guidance.navigation_instructions(view),
                    'navigation', changes, required=True)
            if stage == 'request-entry' or isinstance(stage, str) and stage.endswith(('-read-choice', '-read-choice-repair')):
                symbol = 'ENTRY_PROMPT' if stage == 'request-entry' else 'READ_PROMPT'
                system = replace_known(system, old_selection, literal(code / REL / 'structure_selection.py', symbol),
                    'selection_stage', changes, required=True)
            if isinstance(stage, str) and stage.endswith(('-read-choice', '-read-choice-repair')):
                system = replace_known(system, old_choice, new_choice, 'read_choice', changes, required=True)
                system = replace_known(system, old_scope, '\n' + READ_CONNECTION_PROMPT,
                    'read_scope', changes)
            system = replace_known(system, old_minimal, minimal_output.INSTRUCTIONS, 'minimal', changes)
            system = replace_known(system, old_stream, COMPACT_JSON_INSTRUCTION, 'stream', changes, required=True)
            guided['messages'][0]['content'] = system
            # Remove only the exact old alias module after all known guide edits.
            _, without_aliases = remove_old_aliases(guided, expanded, old_aliases)
            base = deepcopy(guided)
            base['messages'][0]['content'] = without_aliases
            base['response_format']['json_schema']['schema'] = canonical
            base['stream'] = False
            shared = compact_shared_values(view) if v3 else deepcopy(view)
            require(expand_shared_values(shared) == view, 'SHARED_INPUT_NOT_EXACT')
            if v3:
                base['messages'][0]['content'] = replace_known(base['messages'][0]['content'],
                    input_guidance.navigation_instructions(view), input_guidance.navigation_instructions(shared),
                    'shared_navigation', changes, required=True)
            base['messages'][1]['content'] = pack({**payload, 'view': shared})
            proposed, reuse, inputs, keys, cost = prepare_variants(base, enabled=True, aliases=True, preview=preview)
            final = preview(proposed)
            final_view = json.loads(final['messages'][1]['content'])['view']
            if inputs is not None:
                inputs.verify_request_instructions(proposed)
            restored = inputs.verify(shared, final_view) if inputs is not None else final_view
            require(expand_shared_values(restored) == view, 'MODEL_WIRE_NOT_EXACTLY_RESTORABLE')
            require(expand_cards(restored) == expand_cards(view), 'SOURCE_CARD_ROUNDTRIP_FAILED')
            require(reuse.schema == canonical and keys.schema == reuse.wire, 'OUTPUT_CODEC_CHAIN_MISMATCH')
            require(old_aliases._schema(keys.wire, keys.reverse) == reuse.wire, 'NEW_ALIAS_SCHEMA_NOT_REVERSIBLE')
            final_schema = final['response_format']['json_schema']['schema']
            require(schema_inline(final_schema) == keys.wire, 'FINAL_SCHEMA_FACTORING_NOT_EXACT')
            require(cost['selected_request_bytes'] == size(final)
                    and size(final) <= cost['shared_request_bytes']
                    and size(final) <= cost['direct_request_bytes'], 'FULL_REQUEST_COST_GATE_MISMATCH')
            prior = comparison[(call['cell'], call['call'])]
            require(prior['source_request']['sha256'] == source_hash and prior['before_request_bytes'] == size(before),
                    'R9_DIAGNOSTIC_SOURCE_MISMATCH')
            row.update(status='MEASURED', before_request_bytes=size(before), after_encoding_bytes=size(final),
                reduction_bytes=size(before) - size(final), r9_after_encoding_bytes=prior['after_encoding_bytes'],
                reduction_from_r9_bytes=prior['after_encoding_bytes'] - size(final),
                request_sha256_after_projection=digest(final),
                component_delta_bytes={'schema_factoring': size(factored)-size(before),
                    'exact_stage_guidance': size(guided)-size(factored),
                    'input_projection_output_codecs_and_full_cost_gate': size(final)-size(guided)},
                response_format_bytes={'before': size(before['response_format']), 'after': size(final['response_format'])},
                messages_bytes={'before': size(before['messages']), 'after': size(final['messages'])},
                system_string_json_bytes={'before': size(before['messages'][0]['content']), 'after': size(final['messages'][0]['content'])},
                user_string_json_bytes={'before': size(before['messages'][1]['content']), 'after': size(final['messages'][1]['content'])},
                exact_guidance_replacements=changes, full_request_cost=cost,
                input_projection_receipt=inputs.receipt if inputs is not None else None,
                exact_input_restored=True, exact_expanded_cards_restored=True,
                input_view_sha256=digest(view), restored_input_sha256=digest(expand_shared_values(restored)),
                source_container_sha256=digest(view.get('sources')),
                output_schema_chain={'canonical_sha256': digest(canonical), 'reuse_schema_sha256': digest(reuse.wire),
                    'alias_schema_sha256': digest(keys.wire), 'final_factored_sha256': digest(final_schema),
                    'old_factor_exact_identity': True, 'new_factor_exact_identity': True,
                    'reuse_offered': reuse.changed, 'alias_mapping_changed_values': False},
                caller_augmentation_excluded=stage in ('memory-compose', 'memory-compose-repair'))
            require(sum(row['component_delta_bytes'].values()) == size(final)-size(before), 'NONADDITIVE_ACCOUNTING')
        except Exception as error:
            # Exception bodies may contain source text or a schema; never copy them.
            row.update(status='UNMEASURED', reason=str(error) if isinstance(error, Unmeasured) else type(error).__name__)
            for key in ('after_encoding_bytes', 'reduction_bytes', 'reduction_from_r9_bytes'):
                row[key] = None
        require(sha(path) == source_hash, 'SOURCE_CHANGED_DURING_DIAGNOSTIC')
        rows.append(row)
    require(all(sha(code / p) == h for p, h in files.items()), 'CODE_CHANGED_DURING_DIAGNOSTIC')
    measured = [row for row in rows if row['status'] == 'MEASURED']
    before_total = sum(row['before_request_bytes'] for row in measured)
    after_total = sum(row['after_encoding_bytes'] for row in measured)
    result = {'schema_version': 'adr1047-saved-encoding-check-v1', 'kind': 'saved_payload_representation_diagnostic',
        'external_model_calls': 0, 'source_database_opened': False, 'service_started': False,
        'tokens_saved': None, 'speed_effect': None, 'quality_effect': None,
        'method': 'Compact outer HTTP JSON UTF-8 bytes including escaped user JSON, complete schema, alias legends and all retained/new instructions. Exact r10 preview_request is the cost function.',
        'limitations': ['One historical question, A0/A1 only; includes rejected HTTP429.',
            'Existing wire IDs and generation decisions stay fixed; no new choices or canonical IDs are invented.',
            'Saved schema already passed the old minimal-output/provider projection. Only independently reversed key aliases and root local factoring are reconstructed.',
            'COMPOSE caller augmentation omission is excluded; no missing caller input is inferred.',
            'Unmeasured rows have no estimated byte reduction. These are serialization checks, not live tokens, latency, semantic quality or a future-product trajectory.'],
        'source_ledger': ref(LEDGER), 'r9_comparison': ref(R9), 'script': ref(Path(__file__)),
        'candidate': ref(manifest_path), 'candidate_root': str(code.relative_to(ROOT)), 'candidate_files': files,
        'old_helper_sources': [ref(OLD / REL / name) for name in ('wire_schema.py', 'output_key_aliases.py',
            'navigation_input.py', 'minimal_output.py', 'buffered_external_transport.py', 'structure_selection.py', 'decision_projection.py')],
        'totals': {'requests': len(rows), 'measured_requests': len(measured), 'unmeasured_requests': len(rows)-len(measured),
            'before_measured_request_bytes': before_total, 'after_measured_request_bytes': after_total,
            'measured_reduction_bytes': before_total-after_total,
            'measured_reduction_percent': round(100*(before_total-after_total)/before_total, 3) if before_total else None},
        'assess_comparison': [{k: row.get(k) for k in ('cell', 'call', 'status', 'reason', 'before_request_bytes',
            'r9_after_encoding_bytes', 'after_encoding_bytes', 'reduction_from_r9_bytes', 'full_request_cost')}
            for row in rows if row.get('stage') in ('memory-assess', 'memory-assess-repair')], 'calls': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'totals': result['totals'], 'assess': result['assess_comparison'],
        'output': ref(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
