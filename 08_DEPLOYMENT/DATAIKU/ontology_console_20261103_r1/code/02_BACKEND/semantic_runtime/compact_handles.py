"""Request-local, reversible ID encoding. Neither an alias store nor authorization."""
import re
from jsonschema import Draft202012Validator

# Free text must never be altered, even when it coincides with an encoded ID.
FREE_TEXT={'question','expression','reason','title_query','clarification','query','label','text','quote','claim','content'}
def transform(value,mapping,key=None):
    if key in FREE_TEXT:return value
    if isinstance(value,dict):return {k:transform(v,mapping,k) for k,v in value.items()}
    if isinstance(value,list):return [transform(v,mapping,key) for v in value]
    return mapping.get(value,value) if isinstance(value,str) else value

def schema_handles(value):
    found=set()
    if isinstance(value,dict):
        found.update(x for x in value.get('enum',[]) if isinstance(x,str) and re.fullmatch(r'KH[0-9a-f]{20}',x))
        for v in value.values():found.update(schema_handles(v))
    elif isinstance(value,list):
        for v in value:found.update(schema_handles(v))
    return found

class CompactHandlesProvider:
    def __init__(self,provider):self.provider=provider
    def call(self,role,system,data,schema):
        encode={h:f'E{i}' for i,h in enumerate(sorted(schema_handles(schema)),1)};decode={v:k for k,v in encode.items()}
        wire_schema=transform(schema,encode);wire_data=transform(data,encode)
        value,receipt=self.provider.call(role,system,wire_data,wire_schema)
        # Validate before decoding: raw server IDs and invented wire IDs are rejected.
        Draft202012Validator(wire_schema).validate(value)
        original=transform(value,decode);Draft202012Validator(schema).validate(original)
        return original,{**receipt,'handle_encoding':{'version':'request-local-short-kh-v1','wire_to_stored':decode}}
    def record_local(self,value):return self.provider.record_local(value)
