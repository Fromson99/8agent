"""Exact same-payload size counterfactual for the added decision field."""
import copy
import json

def compact(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))

def without_new_field(value):
    if isinstance(value,list):return [without_new_field(v) for v in value]
    if not isinstance(value,dict):return value
    return {k:without_new_field(v) for k,v in value.items() if k!='need_resolution'}

def metrics(body):
    chars=sum(len(m.get('content','')) for m in body.get('messages',[]))
    schema_chars=len(compact(body.get('response_format',{})))
    schema_added=schema_chars-len(compact(without_new_field(body.get('response_format',{}))))
    message_added=0
    for m in body.get('messages',[]):
        try:v=json.loads(m.get('content',''))
        except (ValueError,TypeError):continue
        message_added+=len(compact(v))-len(compact(without_new_field(v)))
    return {'message_chars':chars,'system_chars':sum(len(m.get('content','')) for m in body.get('messages',[]) if m.get('role')=='system'),
        'schema_chars':schema_chars,'provider_bytes':len(compact(body).encode()),
        'added_continuity_metadata_chars':message_added+schema_added,
        'added_resolution_schema_chars':schema_added,'added_resolution_message_chars':message_added,
        'metadata_fraction_of_messages':(message_added+schema_added)/max(1,chars+schema_chars),
        'size_definition':'Unicode chars, exact same-payload removal of need_resolution only (schema+messages). Static instruction delta measured separately. Provider usage is the sole token authority.'}
