"""Factor repeated schema nodes in the external transport, without relaxing validation.

Only schema locations are visited: enum/const/default are data, not schemas.
The original schema remains authoritative; only final transport copies are factored.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json

MAPS=('properties','patternProperties','dependentSchemas')
SINGLE=('items','additionalProperties','unevaluatedProperties','not','if','then','else','contains','propertyNames')
ARRAYS=('anyOf','oneOf','allOf','prefixItems')

def factor_schema(schema):
    original=deepcopy(schema)
    # Existing reference scopes need separate resolution; leave them untouched.
    def scoped(v):
        if isinstance(v,dict):return any(k in v for k in ('$ref','$id','$defs','definitions')) or any(scoped(x) for x in v.values())
        return isinstance(v,list) and any(scoped(x) for x in v)
    if scoped(original):return original
    key=lambda n:json.dumps(n,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    counts=Counter()
    def children(node,fn):
        for k in MAPS:
            for n,v in list(node.get(k,{}).items()):node[k][n]=fn(v)
        for k in SINGLE:
            if isinstance(node.get(k),dict):node[k]=fn(node[k])
            elif isinstance(node.get(k),list):node[k]=[fn(v) for v in node[k]]
        for k in ARRAYS:
            if isinstance(node.get(k),list):node[k]=[fn(v) for v in node[k]]
        return node
    def count(n):
        if not isinstance(n,dict):return n
        counts[key(n)]+=1
        return children(n,count)
    count(deepcopy(original));definitions={}
    # Request-local names are deterministic and contain no semantic source IDs.
    names={raw: "D"+str(i) for i,raw in enumerate(sorted(
        raw for raw,count in counts.items() if count>1 and len(raw)>=180))}
    def rewrite(n,root=False):
        if not isinstance(n,dict):return n
        raw=key(n);value=children(deepcopy(n),rewrite)
        if not root and counts[raw]>1 and len(raw)>=180:
            name=names[raw]
            if name in definitions and definitions[name]!=value:raise ValueError('schema reference hash collision')
            definitions[name]=value
            return {'$ref':'#/$defs/'+name}
        return value
    result=rewrite(original,True)
    if definitions:result['$defs']=definitions
    # A tiny schema may cost more with definitions; retain its exact original form.
    return result if len(key(result))<len(key(original)) else original


def navigation_shape(schema):
    """Keep action/target/required-field binding intact at the provider boundary.

    Repeated nodes may be factored by factor_schema, which preserves semantics.
    Removing alternatives cannot be reversed by the host without guessing.
    """
    return deepcopy(schema)


# This exact ID regex is used by domain-profile v1. Some structured-output
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


VERSION = 'schema-factor-wire-v3' 

def project_request(request):
    """Copy only the final JSON-schema envelope; never transform model output."""
    result = deepcopy(request)
    envelope = (result.get('response_format') or {}).get('json_schema')
    if not isinstance(envelope, dict) or not isinstance(envelope.get('schema'), dict):
        return result, None
    original = envelope['schema']
    compatible, pattern_count = portable_patterns(original)
    wire = factor_schema(compatible)
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    before, after = encode(original), encode(wire)
    envelope['schema'] = wire
    return result, {'version': VERSION,
        'validation_schema_sha256': hashlib.sha256(before.encode()).hexdigest(),
        'wire_schema_sha256': hashlib.sha256(after.encode()).hexdigest(),
        'validation_schema_chars': len(before), 'wire_schema_chars': len(after),
        'changed': original != wire, 'equivalent_ref_pattern_count': pattern_count}
