"""Comparison-only proof of two V aliases; no request/response substitution."""
from copy import deepcopy
import json
import re
import sqlite3
from native_transport import require, digest, domain_record, validate_domain_records

def recorded_view(journal, ordinal, body, codec):
    db=sqlite3.connect(journal.resolve().as_uri()+'?mode=ro')
    try:
        db.execute('PRAGMA query_only=ON')
        row=db.execute('SELECT a.attempt_id,a.request_json,v.body_json,v.body_hash '
            'FROM model_attempt a JOIN model_view v ON v.view_id=a.view_id '
            'ORDER BY a.rowid LIMIT 1 OFFSET ?',(ordinal-1,)).fetchone()
        require(row is not None and json.loads(row[1])==body,'Wire request differs from native attempt')
        stored=json.loads(row[2]);require(digest(stored)==row[3],'Canonical view hash changed')
        events=db.execute("SELECT payload_json,payload_hash FROM event WHERE kind='NUMBERED_REFERENCES' "
            "AND json_extract(payload_json,'$.attempt_id')=?",(row[0],)).fetchall()
        require(len(events)==1,'Native alias receipt missing or ambiguous')
        receipt=json.loads(events[0][0]);require(digest(receipt)==events[0][1],'Alias event hash changed')
        reconstructed=codec(stored).receipt(stored)
        require(all(receipt[k]==v for k,v in reconstructed.items()),'Alias mapping cannot be reconstructed from canonical view')
        require(receipt['wire_view_hash']==digest(json.loads(body['messages'][1]['content'])['view']), 'Alias receipt is not bound to transmitted view')
        return stored,reconstructed['mapping']
    finally:db.close()

def validated_roles(old_view,new_view,old_mapping,new_mapping):
    old_id,new_id=old_view['view_id'],new_view['view_id']
    require(all(re.fullmatch(r'V[0-9a-f]{32}',value) for value in (old_id,new_id)), 'Current view is not a native UUID')
    old_v={k:v for k,v in old_mapping.items() if k.startswith('V')}
    new_v={k:v for k,v in new_mapping.items() if k.startswith('V')}
    require(len(old_v)==len(new_v)==2 and old_id in old_v and new_id in new_v,
            'Expected exactly current view and one preview V identity')
    old_preview=set(old_v)-{old_id};new_preview=set(new_v)-{new_id}
    require(old_preview==new_preview and len(old_preview)==1,'Canonical preview identity changed')
    preview=next(iter(old_preview))
    require(set(old_v.values())==set(new_v.values())=={'V1','V2'},'Unexpected V namespace')
    old_copy=deepcopy(old_view);new_copy=deepcopy(new_view)
    for value in (old_copy,new_copy):
        value.pop('view_id');value['domain_choice'].pop('choice_id')
    require(old_copy==new_copy,'Canonical content differs beyond separately verified generated identities')
    return {old_v[old_id]:'__CURRENT_VIEW__',old_v[preview]:preview}, {
        new_v[new_id]:'__CURRENT_VIEW__',new_v[preview]:preview}

def normalized_request(body, mapping, codec):
    # Native journal/projection proof above protects text and canonical content.
    # Only whole alias tokens in comparison copies are mapped; no actual payload
    # or literal response is changed.
    references=object.__new__(codec)
    references.forward=mapping
    result=deepcopy(body)
    user=json.loads(result['messages'][1]['content'])
    result['messages'][1]['content']=json.dumps(references.view(user),ensure_ascii=False,sort_keys=True,separators=(',',':'))
    envelope=result['response_format']['json_schema']
    envelope['schema']=references.schema(envelope['schema'])
    return result

def check_literal_aliases(literal, changed):
    def inspect(value):
        if isinstance(value,str):
            require(not any(re.search(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])',value) for name in changed),
                    'Literal response refers to a changed alias; response rewrite is forbidden')
        elif isinstance(value,list):
            for item in value:inspect(item)
        elif isinstance(value,dict):
            for key,item in value.items():inspect(key);inspect(item)
    inspect(json.loads(literal))

def prove_aliases(expected,actual,response,old_journal,new_journal,codec):
    old_view,old_map=recorded_view(old_journal,36,expected,codec)
    new_view,new_map=recorded_view(new_journal,36,actual,codec)
    require(old_view['source_stage']==new_view['source_stage']=='source-law-navigation-35', 'Alias exception outside frozen final navigation call')
    domain=validate_domain_records(domain_record(old_journal,old_view['domain_choice']['choice_id']),
        domain_record(new_journal,new_view['domain_choice']['choice_id']),allowed_stage='SELECT')
    before,after=validated_roles(old_view,new_view,old_map,new_map)
    changed={name for name in before if before[name]!=after[name]}
    literal=response['choices'][0]['message']['content']
    check_literal_aliases(literal,changed)
    from jsonschema import Draft202012Validator
    Draft202012Validator(actual['response_format']['json_schema']['schema']).validate(json.loads(literal))
    return normalized_request(expected,before,codec),normalized_request(actual,after,codec),{
        'ordinal':36,'canonical_content_exact':True,'canonical_preview_id':next(v for v in before.values() if v!='__CURRENT_VIEW__'),
        'expected_roles':before,'actual_roles':after,'changed_aliases':sorted(changed),
        'native_mapping_reconstructed':True,'native_domain_proof':domain,
        'literal_response_changed_alias_references':0,'literal_response_valid_for_current_schema':True,
        'comparison_only':True,'request_rewritten':False,'response_rewritten':False}
