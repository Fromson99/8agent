"""Factor repeated schema nodes in the external transport, without relaxing validation.

Only schema locations are visited: enum/const/default are data, not schemas.
GENOS's adapter keeps its existing grammar until field compatibility is verified.
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
    def rewrite(n,root=False):
        if not isinstance(n,dict):return n
        raw=key(n);value=children(deepcopy(n),rewrite)
        if not root and counts[raw]>1 and len(raw)>=180:
            name='D'+hashlib.sha256(raw.encode()).hexdigest()[:16]
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
