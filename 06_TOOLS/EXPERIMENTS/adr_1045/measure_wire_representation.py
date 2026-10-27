"""Measure saved payload representation only; never replay product decisions.

No HTTP client, model, service app, source database or evaluator is instantiated.
The input is the 17 already saved ADR1043 requests. Only exact local-reference
unfolding whose provider refactoring reproduces the saved schema is permitted.
Tokens, speed, decision quality and provider tokenization remain unknown.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-1045-ontology-mvp-terminal-frame/artifacts'
SOURCE_ROOT = ROOT / '04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/artifacts/matrix'
OLD_CODE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1043/compiler-r6/revisions/rev-001/snapshot'
NAVIGATION_FILE = '02_BACKEND/semantic_runtime/legal_agent/navigation_input.py'
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_SCHEMA_NODES = 200000
MAX_SCHEMA_BYTES = 4 * 1024 * 1024
MAPS = ('properties', 'patternProperties', 'dependentSchemas')
SINGLE = ('items', 'additionalProperties', 'unevaluatedProperties', 'not',
          'if', 'then', 'else', 'contains', 'propertyNames')
ARRAYS = ('anyOf', 'oneOf', 'allOf', 'prefixItems')
REFERENCE_KEYS = {'$ref', '$id', '$defs', 'definitions', '$anchor', '$dynamicRef',
                  '$dynamicAnchor', '$recursiveRef', '$recursiveAnchor'}
AUDIT_FIELDS = {'query_fingerprint', 'index_sha256', 'source_artifact_sha256',
                'source_artifact_hash', 'span_hash', 'block_hash', 'text_hash',
                'source_hash', 'decision_hash', 'request_hash', 'schema_sha256'}
SHORT_ID = re.compile(r'^[A-Z][0-9]+$')
LOCAL_REF = re.compile(r'^#/\$defs/(D[0-9]+)$')
LIMITATION = ('saved payload representation diagnostic; tokens/speed unknown; '
              'does not replay product decisions')


class Unmeasurable(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require_equal(actual, expected, message):
    if canonical(actual) != canonical(expected):
        raise Unmeasurable(message)


def strict_parse(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Unmeasurable('duplicate key in saved JSON')
            result[key] = value
        return result
    def constant(_):
        raise Unmeasurable('nonfinite JSON literal')
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    canonical(value)  # Reject nonfinite exponent results and invalid Unicode.
    return value


def strict_load(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise Unmeasurable('saved input exceeds the diagnostic resource limit')
    return strict_parse(path.read_text(encoding='utf-8'))


def candidate_files(code):
    result = {}
    for path in sorted(code.rglob('*')):
        if path.is_file():
            if path.is_symlink():
                raise Unmeasurable('candidate contains a symlink')
            result[str(path.relative_to(code))] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    return result


def old_expander(path):
    """Load exactly the old pure expansion function, without importing old runtime."""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    instruction = None
    function = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'INSTRUCTIONS'
                                              for t in node.targets):
            instruction = ast.literal_eval(node.value)
        if isinstance(node, ast.FunctionDef) and node.name == 'expand_cards':
            function = node
    if not isinstance(instruction, str) or function is None or function.decorator_list:
        raise Unmeasurable('old instruction or pure card expander cannot be identified')
    # The selected frozen function only uses deepcopy and builtins. Do not load
    # its module or any historical runtime dependencies into the current process.
    namespace = {'deepcopy': deepcopy}
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
    return instruction, namespace['expand_cards']


def schema_children(node, transform):
    result = deepcopy(node)
    for key in MAPS:
        if key in node:
            if not isinstance(node[key], dict):
                raise Unmeasurable('unsupported schema child map')
            result[key] = {name: transform(value) for name, value in node[key].items()}
    for key in SINGLE:
        if key in node:
            result[key] = ([transform(value) for value in node[key]]
                           if isinstance(node[key], list) else transform(node[key]))
    for key in ARRAYS:
        if key in node:
            if not isinstance(node[key], list):
                raise Unmeasurable('unsupported schema branch array')
            result[key] = [transform(value) for value in node[key]]
    return result


def unfold_local_schema(schema):
    """Only invert provider-generated standalone #/$defs/Dn references."""
    if not isinstance(schema, dict):
        raise Unmeasurable('saved response schema is not an object')
    definitions = schema.get('$defs', {})
    if not isinstance(definitions, dict) or any(not re.fullmatch(r'D[0-9]+', k) for k in definitions):
        raise Unmeasurable('non-provider definition names')
    visited = [0]
    def walk(node, stack=(), depth=0, root=False):
        visited[0] += 1
        if visited[0] > MAX_SCHEMA_NODES or depth > 128:
            raise Unmeasurable('local schema expansion resource bound')
        if isinstance(node, bool):
            return node
        if not isinstance(node, dict):
            raise Unmeasurable('unsupported schema node')
        if '$ref' in node:
            match = LOCAL_REF.fullmatch(node['$ref']) if isinstance(node['$ref'], str) else None
            if set(node) != {'$ref'} or match is None:
                raise Unmeasurable('external reference or reference with sibling constraints')
            name = match.group(1)
            if name not in definitions or name in stack:
                raise Unmeasurable('missing or cyclic local definition')
            return walk(definitions[name], stack + (name,), depth + 1)
        forbidden = (set(node) & REFERENCE_KEYS) - ({'$defs'} if root else set())
        if forbidden:
            raise Unmeasurable('unsupported nested reference scope')
        result = {key: deepcopy(value) for key, value in node.items() if key != '$defs'}
        return schema_children(result, lambda child: walk(child, stack, depth + 1))
    result = walk(schema, root=True)
    if len(canonical(result)) > MAX_SCHEMA_BYTES:
        raise Unmeasurable('expanded schema exceeds diagnostic resource bound')
    return result


def permitted_audit_projection(view):
    """Independent narrow copy of the already approved model-only omissions."""
    result = deepcopy(view)
    context = result.get('read_judgments')
    if isinstance(context, dict) and context.get('version') == 'read-judgment-v1':
        context.pop('request_key', None)
        context.pop('state_hash', None)
        for row in context.get('current_originals', []):
            if isinstance(row, dict): row.pop('material', None)
        for row in context.get('judgments', []):
            if isinstance(row, dict): row.pop('seen_material', None)
        for conflict in context.get('conflicts', []):
            if isinstance(conflict, dict):
                for row in conflict.get('opinions', []):
                    if isinstance(row, dict): row.pop('seen_material', None)
    def strip(value):
        if isinstance(value, dict):
            return {key: strip(child) for key, child in value.items() if key not in AUDIT_FIELDS}
        if isinstance(value, list): return [strip(child) for child in value]
        return deepcopy(value)
    return strip(result)


def inventory(value):
    """Small audit hashes of all strings and ordered array extents, no body copies."""
    strings = hashlib.sha256()
    arrays = hashlib.sha256()
    counts = {'strings': 0, 'arrays': 0, 'string_utf8_bytes': 0}
    def walk(item, path=()):
        if isinstance(item, str):
            strings.update(canonical([path, item]) + b'\n')
            counts['strings'] += 1
            counts['string_utf8_bytes'] += len(item.encode('utf-8'))
        elif isinstance(item, list):
            arrays.update(canonical([path, len(item)]) + b'\n')
            counts['arrays'] += 1
            for index, child in enumerate(item): walk(child, path + (index,))
        elif isinstance(item, dict):
            for key in sorted(item): walk(item[key], path + (key,))
    walk(value)
    return {**counts, 'string_paths_sha256': strings.hexdigest(),
            'ordered_array_lengths_sha256': arrays.hexdigest(), 'full_value_sha256': digest(value)}


def restore_schema_id_literals(schema, references):
    def restore_literal(value, path):
        wrapped = deepcopy(value)
        for key in reversed(path): wrapped = {key: wrapped}
        restored = references.restore(wrapped)
        for key in path: restored = restored[key]
        return restored
    def walk(node, path=()):
        if isinstance(node, list): return [walk(item, path) for item in node]
        if not isinstance(node, dict): return deepcopy(node)
        result = {}
        for key, value in node.items():
            if key == 'properties':
                result[key] = {name: walk(child, path + (name,)) for name, child in value.items()}
            elif key == 'enum': result[key] = [restore_literal(item, path) for item in value]
            elif key == 'const': result[key] = restore_literal(value, path)
            else: result[key] = walk(value, path)
        return result
    return walk(schema)


def restore_output_schema_keys(schema, reverse):
    if not isinstance(schema, dict): return deepcopy(schema)
    result = schema_children(schema, lambda child: restore_output_schema_keys(child, reverse))
    if 'properties' in result:
        renamed = {reverse.get(key, key): value for key, value in result['properties'].items()}
        if len(renamed) != len(result['properties']):
            raise Unmeasurable('output field collision during independent restoration')
        result['properties'] = renamed
    if 'required' in result:
        result['required'] = [reverse.get(key, key) for key in result['required']]
    return result


def metrics(request):
    messages = request.get('messages', [])
    result = {'total_request_utf8_bytes': len(canonical(request)),
              'response_format_utf8_bytes': len(canonical(request.get('response_format'))),
              'messages_utf8_bytes': len(canonical(messages)),
              'system_utf8_bytes': 0, 'user_utf8_bytes': 0, 'other_message_utf8_bytes': 0,
              'request_sha256': digest(request)}
    for message in messages:
        content = message.get('content')
        if not isinstance(content, str):
            raise Unmeasurable('non-text message content is outside this diagnostic')
        key = message.get('role')
        key = key + '_utf8_bytes' if key in ('system', 'user') else 'other_message_utf8_bytes'
        result[key] += len(content.encode('utf-8'))
    return result


def snapshot_stage(name, request, previous=None):
    measured = metrics(request)
    return {'stage': name, **measured,
            'delta_from_previous_utf8_bytes': ({key: measured[key] - previous[key]
                for key in measured if key.endswith('_utf8_bytes')} if previous else None)}


def replace_view(request, user_index, payload, view):
    result = deepcopy(request)
    payload = {**deepcopy(payload), 'view': deepcopy(view)}
    result['messages'][user_index]['content'] = canonical(payload).decode('utf-8')
    return result


def measure(path, old_instruction, expand_old, navigation, output_keys, provider_request,
            preview_buffered_request, validator):
    saved = strict_load(path)
    original_hash = digest(saved)
    messages = saved.get('messages')
    if not isinstance(messages, list): raise Unmeasurable('saved messages are missing')
    users = [i for i, row in enumerate(messages) if row.get('role') == 'user']
    systems = [i for i, row in enumerate(messages) if row.get('role') == 'system']
    if len(users) != 1 or len(systems) != 1:
        raise Unmeasurable('expected one saved system and one view message; repair chat needs separate binding')
    ui, si = users[0], systems[0]
    payload = strict_parse(messages[ui]['content'])
    if not isinstance(payload, dict) or not isinstance(payload.get('view'), dict):
        raise Unmeasurable('saved user payload has no model view')
    wire_view = payload['view']
    schema = saved['response_format']['json_schema']['schema']
    validator.check_schema(schema)
    unfolded = unfold_local_schema(schema)
    validator.check_schema(unfolded)
    unfactored = deepcopy(saved)
    unfactored['response_format']['json_schema']['schema'] = unfolded
    refactored = provider_request(unfactored)
    require_equal(refactored, saved, 'unfold/provider-refactor does not reproduce exact saved request')
    proof = {'provider_refactor_exact': True, 'saved_schema_sha256': digest(schema),
             'unfolded_schema_sha256': digest(unfolded), 'unfolded_schema_utf8_bytes': len(canonical(unfolded)),
             'provider_refactored_schema_sha256': digest(refactored['response_format']['json_schema']['schema']),
             'scope': 'saved provider grammar only; omitted runtime constraints are not reconstructed'}
    stages = [snapshot_stage('saved_request', saved)]
    request = deepcopy(unfactored)
    compact_enabled = wire_view.get('input_projection') == 'compact-selection-source-v3'
    projection = {'enabled': compact_enabled, 'existing_short_handles_reinterpreted': False}
    if compact_enabled:
        expanded = expand_old(wire_view)
        expected = permitted_audit_projection(expanded)
        references = navigation.NavigationReferences(expanded)
        if any(SHORT_ID.fullmatch(ident) for ident in references.forward):
            raise Unmeasurable('new codec tried to reinterpret a saved short handle')
        identity_view = references.view(expanded)
        compacted = navigation.compact_cards(identity_view)
        restored = references.restore(navigation.expand_cards(compacted))
        require_equal(restored, expected, 'view did not roundtrip after permitted audit projection')
        require_equal(inventory(restored), inventory(expected), 'source/text/array extent inventory changed')
        mapped_schema = references.schema(unfolded)
        validator.check_schema(mapped_schema)
        require_equal(restore_schema_id_literals(mapped_schema, references), unfolded,
                      'schema values or typed path binding did not roundtrip')
        request = replace_view(request, ui, payload, compacted)
        request['response_format']['json_schema']['schema'] = mapped_schema
        projection.update({'receipt': references.receipt(expanded),
                           'old_expanded_view_utf8_bytes': len(canonical(expanded)),
                           'identity_projected_view_utf8_bytes': len(canonical(identity_view)),
                           'new_compacted_view_utf8_bytes': len(canonical(compacted)),
                           'original_wire_view_utf8_bytes': len(canonical(wire_view)),
                           'permitted_audit_projection_changed': digest(expanded) != digest(expected),
                           'roundtrip_inventory': inventory(restored), 'exact_roundtrip': True})
    else:
        # Actual gateway does not add navigation aliases/tables to request-entry
        # or ordinary final composition. Do not invent that extra optimization.
        projection['reason'] = 'actual saved view does not enable compact-selection-source-v3'
        require_equal(json.loads(request['messages'][ui]['content']), payload, 'inactive input projection changed')
    represented = provider_request(request)
    stages.append(snapshot_stage('input_identity_and_cards', represented, stages[-1]))
    if compact_enabled:
        system = request['messages'][si]['content']
        if system.count(old_instruction) != 1:
            raise Unmeasurable('old navigation instruction does not occur exactly once')
        request['messages'][si]['content'] = system.replace(old_instruction, navigation.INSTRUCTIONS, 1)
    represented = provider_request(request)
    stages.append(snapshot_stage('navigation_instruction_replacement', represented, stages[-1]))
    before_alias = deepcopy(request['response_format']['json_schema']['schema'])
    request, key_codec = output_keys.prepare_request(request)
    validator.check_schema(request['response_format']['json_schema']['schema'])
    require_equal(restore_output_schema_keys(request['response_format']['json_schema']['schema'],
                                           key_codec.reverse), before_alias,
                  'output key schema constraints did not roundtrip')
    require_equal(request['messages'][ui], represented['messages'][ui], 'output key codec changed input values')
    represented = provider_request(request)
    stages.append(snapshot_stage('output_keys_legend_and_provider_refactor', represented, stages[-1]))
    final = preview_buffered_request(represented)
    require_equal(final['response_format'], represented['response_format'], 'reception preview changed schema')
    require_equal(final['messages'][ui], represented['messages'][ui], 'reception preview changed view')
    require_equal(preview_buffered_request(final), final, 'reception preview is not idempotent')
    if any(key in final for key in ('max_tokens', 'max_completion_tokens', 'max_output_tokens')):
        raise Unmeasurable('saved request or projection has an output cap')
    require_equal(saved, strict_load(path), 'source changed while measuring')
    if digest(saved) != original_hash: raise Unmeasurable('saved in-memory input was mutated')
    stages.append(snapshot_stage('buffered_preview_final', final, stages[-1]))
    return {'status': 'MEASURED', 'source_stage': wire_view.get('source_stage'),
            'schema_name': saved['response_format']['json_schema']['name'],
            'source_request_sha256': original_hash, 'schema_proof': proof,
            'input_projection': projection, 'output_key_codec': key_codec.receipt,
            'stages': stages, 'before': stages[0], 'after': stages[-1],
            'net_utf8_bytes_saved': stages[0]['total_request_utf8_bytes'] - stages[-1]['total_request_utf8_bytes'],
            'serialized_request_metric': 'canonical compact JSON UTF8; source pretty-print file size is separate',
            'tokens': None, 'speed': None, 'product_decisions_replayed': False}


def main():
    parser = argparse.ArgumentParser(description=LIMITATION)
    parser.add_argument('--code-root', type=Path, required=True,
                        help='Explicit final frozen r7 revisions/rev-*/snapshot path')
    parser.add_argument('--source-root', type=Path, default=SOURCE_ROOT)
    parser.add_argument('--old-code-root', type=Path, default=OLD_CODE)
    parser.add_argument('--output', type=Path, default=ART / 'wire-representation-diagnostic.json')
    args = parser.parse_args()
    code = args.code_root.resolve()
    if code.name != 'snapshot' or code.parent.parent.name != 'revisions':
        raise SystemExit('--code-root must be an explicit frozen revision snapshot')
    output = args.output.resolve()
    if output.is_relative_to(code) or output.is_relative_to(args.source_root.resolve()):
        raise SystemExit('output must not overwrite candidate or source records')
    if any(name.split('.')[0] in ('semantic_runtime', 'lawrag') for name in sys.modules):
        raise SystemExit('diagnostic must start in a fresh Python process')
    sys.dont_write_bytecode = True
    os.environ['LAWRAG_WORKSPACE_ROOT'] = str(ROOT)
    os.environ['LAWRAG_TOOL_WORKSPACE_ROOT'] = str(ROOT)
    sys.path[:0] = [str(code / '02_BACKEND'), str(code)]
    before_files = candidate_files(code)
    navigation = importlib.import_module('semantic_runtime.legal_agent.navigation_input')
    keys = importlib.import_module('semantic_runtime.legal_agent.output_key_aliases')
    transport = importlib.import_module('semantic_runtime.legal_agent.buffered_external_transport')
    local = importlib.import_module('semantic_runtime.legal_agent.local_gemma')
    from jsonschema import Draft202012Validator
    if navigation.AUDIT_FIELDS != AUDIT_FIELDS:
        raise SystemExit('candidate changed the approved audit omission set')
    old_path = args.old_code_root.resolve() / NAVIGATION_FILE
    old_instruction, expand_old = old_expander(old_path)
    paths = sorted(args.source_root.resolve().glob('*/model/call-*/request.json'))
    if len(paths) != 17:
        raise SystemExit('expected exactly 17 saved ADR1043 requests; found ' + str(len(paths)))
    rows = []
    for path in paths:
        source = {'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size}
        try:
            result = measure(path, old_instruction, expand_old, navigation, keys,
                             local.provider_request, transport.preview_buffered_request,
                             Draft202012Validator)
            if sha(path) != source['sha256']:
                raise Unmeasurable('source file bytes changed during diagnostic')
        except Exception as error:
            # Preserve the inability to prove a representation. Never substitute
            # a guessed saving or extrapolate from another request.
            result = {'status': 'UNMEASURABLE', 'error_type': type(error).__name__,
                      'reason': str(error)[:2000], 'before': None, 'after': None,
                      'net_utf8_bytes_saved': None, 'tokens': None, 'speed': None,
                      'product_decisions_replayed': False}
        rows.append({'source_file': source, **result})
    imports = {name: str(Path(module.__file__).resolve()) for name, module in list(sys.modules.items())
               if name.split('.')[0] in ('semantic_runtime', 'lawrag') and getattr(module, '__file__', None)}
    leaks = {name: path for name, path in imports.items() if not Path(path).is_relative_to(code)}
    drift = candidate_files(code) != before_files
    measured = [row for row in rows if row['status'] == 'MEASURED']
    integrity = not leaks and not drift
    report = {'schema_version': 'adr1045-wire-representation-diagnostic-v1',
              'limitation': LIMITATION, 'candidate_root': str(code),
              'measurement_is_valid': integrity, 'product_decisions_replayed': False,
              'live_model_calls': 0, 'source_database_opened': False,
              'tokens': None, 'speed': None,
              'method': ['expand the old saved card representation without restoring historical short IDs',
                         'unfold standalone provider local refs; require exact provider-refactor identity first',
                         'apply navigation IDs/cards only where the saved runtime projection is enabled',
                         'replace the exact old navigation instruction; alias output keys before provider refactoring',
                         'apply buffered preview including exact optional instruction removal and added stream instructions'],
              'limits': ['The saved provider grammar is not the richer original runtime validation schema.',
                         'Source strings, evidence metadata and row counts are compared after permitted audit-only omissions.',
                         'No new decisions, retrieval, product execution, token estimates or timing comparisons are performed.',
                         'Subset totals are not estimates for unmeasurable requests.'],
              'script': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)},
              'old_navigation_file': {'path': str(old_path), 'sha256': sha(old_path)},
              'candidate_files': before_files, 'candidate_files_sha256': digest(before_files),
              'actual_runtime_imports': imports, 'production_import_leaks': leaks,
              'candidate_changed_during_diagnostic': drift, 'rows': rows,
              'summary': {'saved_requests': len(rows), 'measured_requests': len(measured),
                          'unmeasurable_requests': len(rows) - len(measured),
                          'all_17_measured': len(measured) == 17 and integrity,
                          'subset_before_utf8_bytes': sum(row['before']['total_request_utf8_bytes'] for row in measured) if integrity and measured else None,
                          'subset_after_utf8_bytes': sum(row['after']['total_request_utf8_bytes'] for row in measured) if integrity and measured else None,
                          'subset_net_utf8_bytes_saved': sum(row['net_utf8_bytes_saved'] for row in measured) if integrity and measured else None}}
    raw = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if output.read_bytes() != raw:
            raise SystemExit('existing diagnostic differs; choose a new output path')
    else:
        with output.open('xb') as target:
            target.write(raw)
    print(json.dumps({'output': str(output), 'sha256': sha(output),
                      'measurement_is_valid': integrity, **report['summary'],
                      'tokens': None, 'speed': None, 'product_decisions_replayed': False}, ensure_ascii=False))
    return 0 if integrity else 2


if __name__ == '__main__':
    raise SystemExit(main())
