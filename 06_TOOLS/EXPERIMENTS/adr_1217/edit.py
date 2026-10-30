from common import *
S=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1217/compatible/snapshot'
p=S/'02_BACKEND/semantic_runtime/legal_agent/wire_schema.py';s=p.read_text();s=s.replace("VERSION = 'schema-factor-wire-v2'",'''# This exact ID regex is used by domain-profile v1. Some structured-output
# backends reject its large variable repetition even in an otherwise tiny schema.
# Concatenating identical character classes with zero minima preserves precisely
# the same language (32 + 32 + 32 + 32 + 31 = 159), including anchor semantics.
REF_PATTERN = '^[A-Za-z][A-Za-z0-9_:-]{0,159}$'
PORTABLE_REF_PATTERN = '^[A-Za-z]' + '[A-Za-z0-9_:-]{0,32}' * 4 + '[A-Za-z0-9_:-]{0,31}$'


def portable_patterns(schema):
    """Rewrite only the known equivalent pattern at actual schema locations."""
    count = 0
    def visit(node):
        nonlocal count
        if not isinstance(node, dict):
            return deepcopy(node)
        result = deepcopy(node)
        if result.get('pattern') == REF_PATTERN:
            result['pattern'] = PORTABLE_REF_PATTERN
            count += 1
        for key in MAPS + ('$defs', 'definitions'):
            if isinstance(result.get(key), dict):
                result[key] = {name: visit(value) for name, value in result[key].items()}
        for key in SINGLE:
            if isinstance(result.get(key), dict):
                result[key] = visit(result[key])
            elif isinstance(result.get(key), list):
                result[key] = [visit(value) for value in result[key]]
        for key in ARRAYS:
            if isinstance(result.get(key), list):
                result[key] = [visit(value) for value in result[key]]
        return result
    return visit(schema), count


VERSION = 'schema-factor-wire-v3' ''')
s=s.replace('    wire = factor_schema(original)','    compatible, pattern_count = portable_patterns(original)\n    wire = factor_schema(compatible)')
s=s.replace("        'changed': original != wire}","        'changed': original != wire, 'equivalent_ref_pattern_count': pattern_count}")
p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/ontology_work/authoring_model.py';s=p.read_text()
s=s.replace("    choices = raw.get('choices') if isinstance(raw, dict) else None", "    if isinstance(raw, dict) and raw.get('error'):\n        raise AuthoringFailure('INCOMPLETE_RESPONSE', receipt)\n    choices = raw.get('choices') if isinstance(raw, dict) else None")
s=s.replace("    if choice.get('finish_reason') in ('length', 'refusal', 'content_filter'):","    # A provider can report an error inside HTTP200, even with JSON-looking text.\n    # Preserve the response and stop before the workflow's semantic repair path.\n    receipt['finish_reason'] = choice.get('finish_reason')\n    if choice.get('error') or choice.get('finish_reason') not in (None, 'stop'):")
s=s.replace("    message = choice.get('message') or {}\n    if isinstance(message.get('content'), str)","    message = choice.get('message') or {}\n    if not isinstance(message, dict):\n        raise AuthoringFailure('INVALID_RESPONSE', receipt)\n    if message.get('refusal'):\n        raise AuthoringFailure('INCOMPLETE_RESPONSE', receipt)\n    if isinstance(message.get('content'), str)")
p.write_text(s)
print('Edited2candidate product files only')
