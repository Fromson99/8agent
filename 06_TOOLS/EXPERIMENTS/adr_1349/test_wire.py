from copy import deepcopy
from types import SimpleNamespace
import json, time
import httpx, pytest
from test_wiki_workspace import env, ws
from semantic_runtime.ontology_work import authoring_model, wiki_contracts as wc
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from jsonschema import Draft202012Validator

def test_actual_authoring_transport_compatible_wire_and_local_duplicate_repair(env,ws,monkeypatch):
    from semantic_runtime import genos
    from lawrag.core import request_deadline
    raw=ws.import_payload('원기록',event_id='wire',run_id='synthetic');requests=[];seen_schemas=[];receipts=[]
    endpoint=SimpleNamespace(headers={},url=lambda p:'https://synthetic.invalid'+p)
    monkeypatch.setattr(genos,'from_env',lambda kind:(endpoint,'synthetic'))
    monkeypatch.setattr(genos,'advertised_model',lambda *a:'synthetic')
    good={'operations':[{'op':'ADD_STATEMENT','target':'@s','value':{'text':env.source['text'],
          'origin_refs':[raw['bundle_id']],'source_basis':[{'source_ref':env.source['id'],'quote':env.source['text'],'occurrence':0}]}}]}
    bad=deepcopy(good);bad['operations'][0]['value']['origin_refs']*=2
    def visit(v):
        if isinstance(v,dict):
            assert 'uniqueItems' not in v
            for child in v.values():visit(child)
        elif isinstance(v,list):
            for child in v:visit(child)
    def post(url,**kwargs):
        req=kwargs['json_body'];visit(req['response_format']['json_schema']['schema'])
        assert not {'max_tokens','max_output_tokens','max_completion_tokens'}&req.keys()
        requests.append(req);return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(bad if len(requests)==1 else good)}}]})
    monkeypatch.setattr(request_deadline,'post_json',post)
    def generate(prompt,context,schema):
        original=deepcopy(schema);seen_schemas.append(original)
        value,receipt=authoring_model.generate(ws.store,prompt,context,schema)
        assert schema==original and receipt['authoring_contract']['validation_schema_sha256']==digest(original)
        receipts.append(receipt);return value,receipt
    ws.generate=generate
    proposal=ws.propose(change_id='wire',raw_ids=[raw['bundle_id']],originals=[env.source])
    assert len(requests)==2 and ws.list_items()['items']==[]
    assert list(Draft202012Validator(seen_schemas[0]).iter_errors(bad))
    assert not list(Draft202012Validator(seen_schemas[0]).iter_errors(good))
    assert json.loads(requests[1]['messages'][1]['content'])['repair']['previous']['response']==bad
    ws.apply(**proposal);assert ws.apply(**proposal)['reused'] and len(requests)==2

def test_shared_adapter_preserves_literal_uniqueitems_property_and_enum(monkeypatch,env):
    from semantic_runtime import genos
    from lawrag.core import request_deadline
    schema={'type':'object','properties':{'uniqueItems':{'type':'string','enum':['uniqueItems']},
        'values':{'type':'array','uniqueItems':True,'items':{'type':'string'}}},'required':['uniqueItems','values'],'additionalProperties':False}
    before=deepcopy(schema);captured=[]
    endpoint=SimpleNamespace(headers={},url=lambda p:'https://synthetic.invalid'+p)
    monkeypatch.setattr(genos,'from_env',lambda kind:(endpoint,'synthetic'));monkeypatch.setattr(genos,'advertised_model',lambda *a:'synthetic')
    def post(url,**kwargs):
        captured.append(kwargs['json_body']);return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"uniqueItems":"uniqueItems","values":["a","a"]}'}}]})
    monkeypatch.setattr(request_deadline,'post_json',post)
    value,_=authoring_model.generate(env.w.store,'prompt',{'call_budget':{'absolute_deadline':time.time()+180}},schema)
    wire=captured[0]['response_format']['json_schema']['schema'];assert schema==before
    assert wire['properties']['uniqueItems']==schema['properties']['uniqueItems']
    assert 'uniqueItems' not in wire['properties']['values']
    with pytest.raises(ContractError):wc.validate(value,schema)
