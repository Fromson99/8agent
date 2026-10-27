#!/usr/bin/env python3
"""Read saved ADR1045 JSON only; record hashes/counts, never payload text.

No application imports, model, service, database, or product replay occurs.
"""
import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / '04_EXPERIMENTS/ADR/ADR-1045-ontology-mvp-terminal-frame/artifacts'
MIN_BYTES = 32
REF_KEYS = {'basis_refs', 'evidence_refs', 'judgment_refs', 'issue_refs', 'claim_refs',
            'claim_ids', 'source_ref', 'target', 'previous_gap_key'}
ID_KEYS = {'id', 'claim_id', 'judgment_id', 'material_id'}
STATE_KEYS = {'choice', 'status', 'operation', 'use', 'disposition', 'kind', 'mode',
              'format', 'relation', 'method_id', 'source_category', 'content_contract',
              'suggested_action'}
QUOTE_KEYS = {'quote', 'user_quote', 'request_quote', 'source_quote', 'exact_quote'}


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                      sort_keys=True, allow_nan=False).encode('utf-8')


def fingerprint(value):
    return type(value).__name__, hashlib.sha256(packed(value)).hexdigest()


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), {'path': str(path.relative_to(ROOT)),
                            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def pointer(parts):
    return '/' + '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in parts) if parts else ''


def walk(value, path=()):
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, path + (index,))


def unalias(value, reverse):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = reverse.get(key, key)
            if name in result:
                raise ValueError('alias decoding would collide')
            result[name] = unalias(item, reverse)
        return result
    if isinstance(value, list):
        return [unalias(item, reverse) for item in value]
    return value


def field_category(parts):
    fields = [part for part in parts if isinstance(part, str)]
    key = fields[-1] if fields else ''
    if key in QUOTE_KEYS:
        return 'explicit_quote_contract'
    if key in REF_KEYS:
        return 'reference_or_target_selection'
    if key in ID_KEYS:
        return 'identifier_binding'
    if key in STATE_KEYS:
        return 'state_or_action_selection'
    if key in {'reason', 'finding', 'explanation', 'text', 'missing_need', 'missing_target',
               'purpose', 'question', 'subject', 'scope', 'value', 'missing'}:
        return 'meaning_or_explanation_text'
    return 'other'


def source_category(parts):
    names = {part for part in parts if isinstance(part, str)}
    if 'system' in names or 'response_format' in names:
        return 'format_or_policy_instruction'
    if names & {'sources', 'user_fact_sources', 'question', 'current_request'}:
        return 'source_or_request_container'
    return 'state_or_other_input'


def ref(call, path, value, origin, category=None):
    return {'call': call, 'field_path': pointer(path), 'origin': origin,
            'kind': type(value).__name__, 'value_sha256': fingerprint(value)[1],
            'category': category or source_category(path)}


def schema_leaves(schema, parts, root, depth=0):
    """Read declared same-path choices only; this is not schema validation."""
    if depth > 64 or not isinstance(schema, dict):
        return []
    if '$ref' in schema:
        target = schema['$ref']
        if set(schema) != {'$ref'} or not target.startswith('#/$defs/'):
            return [None]
        return schema_leaves(root.get('$defs', {}).get(target[8:]), parts, root, depth + 1)
    found = []
    for branch_key in ('anyOf', 'oneOf'):
        for branch in schema.get(branch_key, []):
            found.extend(schema_leaves(branch, parts, root, depth + 1))
    if not parts:
        if 'const' in schema:
            found.append([schema['const']])
        elif 'enum' in schema:
            found.append(schema['enum'])
        elif not any(key in schema for key in ('anyOf', 'oneOf')):
            found.append(None)
    elif isinstance(parts[0], int):
        if 'items' in schema:
            found.extend(schema_leaves(schema['items'], parts[1:], root, depth + 1))
    elif parts[0] in schema.get('properties', {}):
        found.extend(schema_leaves(schema['properties'][parts[0]], parts[1:], root, depth + 1))
    return found


def summaries(rows):
    leaves = [leaf for row in rows for leaf in row['long_string_leaves']]
    result = {'calls': len(rows), 'output_raw_utf8_bytes': sum(r['output_raw_utf8_bytes'] for r in rows),
              'output_compact_json_utf8_bytes': sum(r['output_compact_json_utf8_bytes'] for r in rows),
              'output_short_alias_key_occurrences': sum(r['output_short_alias_key_occurrences'] for r in rows),
              'output_mapped_original_long_key_occurrences': sum(r['output_mapped_original_long_key_occurrences'] for r in rows),
              'long_string_leaves': len(leaves),
              'long_string_value_utf8_bytes': sum(x['value_utf8_bytes'] for x in leaves)}
    for criterion in ('exact_current_input_value', 'contained_in_current_input_string',
                      'exact_previous_output_value', 'exact_earlier_same_output_value', 'any_exact_or_contained_match'):
        matched = [x for x in leaves if x[criterion]]
        result[criterion] = {'leaves': len(matched), 'value_utf8_bytes': sum(x['value_utf8_bytes'] for x in matched)}
    for criterion in ('maximal_exact_matches', 'maximal_alias_normalized_matches'):
        selected = [x for r in rows for x in r[criterion]]
        result[criterion] = {'subtrees': len(selected),
                             'compact_json_value_utf8_bytes': sum(x['compact_json_value_utf8_bytes'] for x in selected)}
    result['control_leaves'] = dict(sum((Counter(r['control_leaf_summary']) for r in rows), Counter()))
    result['long_strings_by_field_category'] = {}
    for category in sorted({x['field_category'] for x in leaves}):
        selected = [x for x in leaves if x['field_category'] == category]
        result['long_strings_by_field_category'][category] = {
            'leaves': len(selected), 'value_utf8_bytes': sum(x['value_utf8_bytes'] for x in selected),
            'matching_leaves': sum(x['any_exact_or_contained_match'] for x in selected),
            'matching_value_utf8_bytes': sum(x['value_utf8_bytes'] for x in selected if x['any_exact_or_contained_match'])}
    return result


def analyse(matrix):
    rows, omitted = [], []
    for cell in sorted(matrix.iterdir()):
        if not cell.is_dir():
            continue
        previous, previous_normal = defaultdict(list), defaultdict(list)
        for response_path in sorted((cell / 'model').glob('call-*/response.json')):
            response, response_source = read(response_path)
            if not response.get('choices'):
                omitted.append({'cell': cell.name, 'call': response_path.parent.name,
                                'reason': 'no_model_output', 'source': response_source})
                continue
            request, request_source = read(response_path.parent / 'request.json')
            call = response_path.parent.name
            contents = {m['role']: m['content'] for m in request['messages']}
            user = json.loads(contents['user'])
            schema = request['response_format']['json_schema']['schema']
            legend = re.search(r'Output keys only: (.*?)\. Input keys', contents['system'])
            forward = dict(item.split('=') for item in legend.group(1).split(', ')) if legend else {}
            reverse = {short: long for long, short in forward.items()}
            text = response['choices'][0]['message']['content']
            output = json.loads(text)
            normalized = unalias(output, reverse)
            inputs = {'system': contents['system'], 'user': user, 'response_format': request['response_format']}
            current, current_strings = defaultdict(list), []
            for path, value in walk(inputs):
                item = ref(call, path, value, 'current_input')
                current[fingerprint(value)].append(item)
                if isinstance(value, str):
                    current_strings.append((value, item))
            seen, seen_normal = defaultdict(list), defaultdict(list)
            long_strings, controls, candidates = [], [], []
            raw_nodes = list(walk(output))
            normal_nodes = dict(walk(normalized))
            alias_occurrences = sum(bool(path) and isinstance(path[-1], str) and path[-1] in reverse
                                    for path, _ in raw_nodes)
            original_alias_key_occurrences = sum(bool(path) and isinstance(path[-1], str) and path[-1] in forward
                                                 for path, _ in raw_nodes)
            for path, value in raw_nodes:
                norm_path = tuple(reverse.get(part, part) if isinstance(part, str) else part for part in path)
                norm_value = normal_nodes[norm_path]
                category = field_category(norm_path)
                fp, nfp = fingerprint(value), fingerprint(norm_value)
                same_current, same_previous, same_local = current.get(fp, []), previous.get(fp, []), seen.get(fp, [])
                size = len(packed(value))
                base = {'field_path': pointer(path), 'canonical_field_path': pointer(norm_path),
                        'kind': type(value).__name__, 'field_category': category,
                        'value_sha256': fp[1], 'compact_json_value_utf8_bytes': size}
                if isinstance(value, str):
                    if len(value.encode('utf-8')) >= MIN_BYTES:
                        contained = [item for source_text, item in current_strings if value in source_text]
                        flags = {'exact_current_input_value': bool(same_current),
                                 'contained_in_current_input_string': bool(contained),
                                 'exact_previous_output_value': bool(same_previous),
                                 'exact_earlier_same_output_value': bool(same_local)}
                        long_strings.append({**base, 'value_utf8_bytes': len(value.encode('utf-8')),
                            **flags, 'any_exact_or_contained_match': any(flags.values()),
                            'current_input_exact_matches': same_current,
                            'current_input_containment_matches': contained,
                            'previous_output_exact_matches': same_previous,
                            'earlier_same_output_exact_matches': same_local})
                    if category in {'reference_or_target_selection', 'identifier_binding', 'state_or_action_selection'}:
                        allowed = schema_leaves(schema, path, schema)
                        declared = [choice for choice in allowed if choice is not None]
                        unique = {packed(v) for choices in declared for v in choices}
                        all_restricted = bool(allowed) and all(choice is not None for choice in allowed)
                        controls.append({**base, 'value_utf8_bytes': len(value.encode('utf-8')),
                            'input_value_present': bool(same_current),
                            'input_data_value_present': any(x['field_path'].startswith('/user/') for x in same_current),
                            'previous_output_value_present': bool(same_previous),
                            'declared_schema_choices_at_same_field': len(unique) if all_restricted else None,
                            'same_field_single_declared_value': all_restricted and unique == {packed(value)},
                            'note': 'Existing reference or selected state is not automatically dispensable; no binding/selection consumer was changed.'})
                if isinstance(value, (str, dict, list)) and (len(value.encode('utf-8')) if isinstance(value, str) else size) >= MIN_BYTES:
                    raw_matches = same_current + same_previous + same_local
                    norm_matches = current.get(nfp, []) + previous_normal.get(nfp, []) + seen_normal.get(nfp, [])
                    candidates.append((path, {**base, 'exact_matches': raw_matches,
                                              'alias_normalized_matches': norm_matches}))
                # Include all nodes for equality; only the report threshold controls measured matches.
                seen[fp].append(ref(call, path, value, 'earlier_same_output', category))
                seen_normal[nfp].append(ref(call, norm_path, norm_value, 'earlier_same_output_alias_normalized', category))
            selections = {}
            for name, match_key in [('maximal_exact_matches', 'exact_matches'),
                                    ('maximal_alias_normalized_matches', 'alias_normalized_matches')]:
                selected_paths, selected = [], []
                for path, item in candidates:
                    if not item[match_key] or any(path[:len(parent)] == parent for parent in selected_paths):
                        continue
                    selected_paths.append(path)
                    selected.append({k: v for k, v in item.items() if k not in {'exact_matches', 'alias_normalized_matches'}} |
                                    {'matches': item[match_key]})
                selections[name] = selected
            control_summary = Counter({'total_leaves': len(controls),
                                       'total_value_utf8_bytes': sum(x['value_utf8_bytes'] for x in controls)})
            for key in ('input_value_present', 'input_data_value_present', 'previous_output_value_present', 'same_field_single_declared_value'):
                control_summary[key] = sum(x[key] for x in controls)
                control_summary[key + '_value_utf8_bytes'] = sum(x['value_utf8_bytes'] for x in controls if x[key])
            for category in ('reference_or_target_selection', 'identifier_binding', 'state_or_action_selection'):
                control_summary[category] = sum(x['field_category'] == category for x in controls)
            rows.append({'cell': cell.name, 'arm': cell.name[-2:], 'call': call,
                         'source_stage': user.get('view', {}).get('source_stage'),
                         'sources': {'request': request_source, 'response': response_source},
                         'output_raw_utf8_bytes': len(text.encode('utf-8')),
                         'output_compact_json_utf8_bytes': len(packed(output)),
                         'output_alias_mapping_count': len(forward),
                         'output_short_alias_key_occurrences': alias_occurrences,
                         'output_mapped_original_long_key_occurrences': original_alias_key_occurrences,
                         'long_string_leaves': long_strings, 'control_leaves': controls,
                         'control_leaf_summary': dict(control_summary), **selections})
            for path, value in raw_nodes:
                previous[fingerprint(value)].append(ref(call, path, value, 'previous_output', field_category(path)))
            for path, value in walk(normalized):
                previous_normal[fingerprint(value)].append(ref(call, path, value, 'previous_output_alias_normalized', field_category(path)))
    assert len(rows) == 10 and len(omitted) == 1
    return rows, omitted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ART / 'output-repetition-analysis.json')
    args = parser.parse_args()
    assert not args.output.exists(), 'Refuse to overwrite an existing analysis'
    rows, omitted = analyse(ART / 'matrix')
    report = {
        'schema_version': 'adr1045-output-repetition-analysis-v1',
        'scope': 'Ten saved normal outputs, compared only within their own cell and against their corresponding saved input; HTTP429 has no model output.',
        'script': read_script(),
        'method': {
            'long_value_threshold_utf8_bytes': MIN_BYTES,
            'strings': 'Exact decoded character equality; no case/whitespace/Unicode normalization. Containment is literal contiguous substring and is reported separately from whole-value equality.',
            'objects': 'Canonical compact JSON equality with sorted object keys; JSON value types and array ordering preserved. No semantic equivalence is inferred.',
            'input': 'Current saved system string, parsed user JSON, and response_format. Compact cards/tables are not expanded; raw saved paths remain auditable. This can undercount object-level equality.',
            'aliases': 'Known output-key legend is decoded only for a separately labelled alias-normalized object comparison and field-path classification. All values and short IDs remain unchanged; cross-request handle identity is not inferred.',
            'nonoverlap': 'Long string leaves never contain child leaves. Maximal subtree metrics select a matching parent first and exclude all descendants. Raw and alias-normalized subtree totals and individual match criteria overlap and must not be added.',
            'byte_denominators': 'String content uses unescaped UTF8 value bytes; subtree sizes use compact JSON value bytes including keys/quotes. Output raw bytes include formatting. These measures are not token estimates or directly additive.',
            'classification': 'Quote/ID/reference/state categories are path-based syntactic labels, not legal judgments. Rule text/finding/reason can contain necessary source wording; exact presence does not prove dispensability.',
            'schema_controls': 'Read same-field declared enum/const choices including local refs. A single declared value is a candidate for deterministic assembly, not proof that omitting it satisfies runtime/state consumers.',
            'data_minimization': 'Only field paths, sizes, hashes, source paths and descriptive status labels are written. No source text, output text, question, credential, organization identifier or error payload is copied.',
        },
        'limitations': [
            'No semantic repetition percentage, legal correctness, avoidable token count, quality or speed improvement is established.',
            'The same short ID may bind different original identities on different calls; repeated handle bytes do not establish repeated evidence identity.',
            'A repeated claim after investigation may be a necessary reaffirmation; a user quote may intentionally repeat the request.',
            'Input/object equality may be undercounted because compact tables/cards and embedded JSON strings are not expanded.',
            'Current-input and previous-output matches can overlap; union and maximal metrics prevent double counting only within each explicitly named metric.',
            'Only two cells and ten normal outputs are observed; the interrupted A1 cell has no final answer.',
        ],
        'calls': rows, 'omitted_responses': omitted, 'totals': summaries(rows),
        'by_arm': {arm: summaries([row for row in rows if row['arm'] == arm]) for arm in ('A0', 'A1')},
        'product_code_modified': False, 'model_calls': 0, 'database_opens': 0, 'service_calls': 0,
    }
    encoded = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as stream:
        stream.write(encoded)
    print(json.dumps({'path': str(args.output), 'sha256': hashlib.sha256(encoded).hexdigest(),
                      'bytes': len(encoded), 'totals': report['totals']}, ensure_ascii=False))


def read_script():
    raw = Path(__file__).read_bytes()
    return {'path': str(Path(__file__).resolve().relative_to(ROOT)),
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


if __name__ == '__main__':
    main()
