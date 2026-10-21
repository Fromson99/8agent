"""Actual API and bounded adapter failure injection; no real model calls."""
from copy import deepcopy
from dataclasses import replace
import json
import sqlite3
from types import SimpleNamespace
import pytest
from jsonschema import Draft202012Validator, ValidationError
from semantic_runtime.legal_agent.bounded_source_session import BoundedSourceSession
from semantic_runtime.legal_agent.errors import BudgetExhausted, DeadlineExceeded, ContractError
from semantic_runtime.legal_agent import output_contract as oc
from test_legal_agent_double_harness import work, PROFILE, ROOT, wire
from test_investigation_completion_adr0678 import completed_app, tree


def adapter(work, responses, *, ceiling=6400):
    calls=[]
    class Transport:
        binding=PROFILE['model_binding']
        def send_once(self, *, body, ticket):
            calls.append(deepcopy(body))
            response=wire({'ok':True})
            response['body_json']['choices'][0]['finish_reason']=responses[len(calls)-1]
            response['body_json']['usage']={'completion_tokens':body['max_tokens']}
            return response
    s=object.__new__(BoundedSourceSession)
    s.profile={**PROFILE,'max_output_tokens':ceiling,'candidate_navigation':{'completion_contract':True,'length_recovery_max_tokens':ceiling}}
    s.work=work;s.context=work.context;s.gateway=SimpleNamespace(domain={},transport=Transport())
    s.selection_views={}
    return s,calls


SCHEMA={'type':'object','properties':{'ok':{'const':True}},'required':['ok'],'additionalProperties':False}
PHASE='source-law-navigation-2'


def call(s,data=None,phase=PHASE):
    return s.structured('same system',data or {'question':'synthetic','sources':[]},SCHEMA,phase,60)


@pytest.mark.parametrize('second',['stop','length','content_filter'])
def test_length_uses_profile_headroom_only_for_one_owner_correction(work,second):
    s,calls=adapter(work,['length',second])
    with pytest.raises(oc.OutputContractError) as failed:call(s)
    payload={'question':'synthetic','sources':[],
        'repair_contract':{'validation':oc.diagnostics(failed.value),'response_mode':'FULL_DECISION'}}
    if second=='stop':assert call(s,payload,PHASE+'-repair')=={'ok':True}
    else:
        with pytest.raises(oc.OutputContractError) as final:call(s,payload,PHASE+'-repair')
        assert not final.value.repairable
    assert [x['max_tokens'] for x in calls]==[1536,6400]
    assert calls[0]['response_format']==calls[1]['response_format']
    assert s.work.budget()['model_reserved']==2 and not s.work.heads('finding')
    assert s.profile['max_output_tokens']==6400


@pytest.mark.parametrize('reason',['stop','content_filter','refusal'])
def test_normal_and_refused_calls_keep_original_budget(work,reason):
    s,calls=adapter(work,[reason])
    if reason=='stop':assert call(s)=={'ok':True}
    else:
        with pytest.raises(oc.OutputContractError) as failed:call(s)
        assert not failed.value.repairable
    assert len(calls)==1 and calls[0]['max_tokens']==1536


@pytest.mark.parametrize('ceiling',[512,1536])
def test_no_headroom_is_terminal_without_same_cap_retry(work,ceiling):
    s,calls=adapter(work,['length'],ceiling=ceiling)
    with pytest.raises(oc.OutputContractError) as failed:call(s)
    assert not failed.value.repairable and failed.value.issues[0]['code']=='OUTPUT_LENGTH'
    assert len(calls)==1


def test_nonlength_schema_repair_keeps_original_budget(work):
    s,calls=adapter(work,['stop'])
    payload={'repair_contract':{'validation':{'category':'OUTPUT_SHAPE_INVALID',
        'issues':[oc.issue('SCHEMA_REQUIRED')]}}}
    assert call(s,payload,PHASE+'-repair')=={'ok':True}
    assert calls[0]['max_tokens']==1536


def test_length_correction_does_not_reset_deadline(work):
    s,calls=adapter(work,['length','stop'])
    with pytest.raises(oc.OutputContractError) as failed:call(s)
    s.context=replace(s.context,deadline=0)
    with pytest.raises(DeadlineExceeded):
        call(s,{'repair_contract':{'validation':oc.diagnostics(failed.value)}},PHASE+'-repair')
    assert len(calls)==1 and work.budget()['model_reserved']==1


def test_legacy_profile_keeps_existing_length_repair_contract(work):
    s,calls=adapter(work,['length'])
    s.profile['candidate_navigation'].pop('length_recovery_max_tokens')
    with pytest.raises(oc.OutputContractError) as failed:call(s)
    assert failed.value.repairable and calls[0]['max_tokens']==1536


@pytest.mark.parametrize('value',[-1,True,80001,'12800',None])
def test_invalid_recovery_policy_is_rejected(value):
    from semantic_runtime.legal_agent.law_candidates import validate_policy
    with pytest.raises(ContractError,match='length recovery'):
        validate_policy({'length_recovery_max_tokens':value})


def test_length_correction_uses_existing_physical_call_budget(work):
    s,calls=adapter(work,['length','stop'])
    with pytest.raises(oc.OutputContractError) as failed:call(s)
    before=work.budget()['model_reserved']
    limit=work.budget()['model_limit']
    work.db.execute('UPDATE budget SET model_reserved=model_limit WHERE singleton=1')
    with pytest.raises(BudgetExhausted):
        call(s,{'repair_contract':{'validation':oc.diagnostics(failed.value)}},PHASE+'-repair')
    assert len(calls)==before==1 and work.budget()['model_reserved']==limit


def test_durable_owner_replays_accepted_result_without_new_call(work):
    s,calls=adapter(work,['length','stop'])
    data={'question':'synthetic','sources':[]}
    def invoke(payload,attempt):return call(s,payload,PHASE+('-repair' if attempt else ''))
    def run():return oc.bounded_decision(work,'law-navigation',data,SCHEMA,invoke,
        lambda value:oc.validate_shape(value,SCHEMA))
    assert run()==run()=={'ok':True}
    assert len(calls)==2 and work.budget()['model_reserved']==2


def test_durable_owner_does_not_restart_failed_length_budget(work):
    s,calls=adapter(work,['length','length'])
    data={'question':'synthetic','sources':[]}
    def invoke(payload,attempt):return call(s,payload,PHASE+('-repair' if attempt else ''))
    def run():return oc.bounded_decision(work,'law-navigation',data,SCHEMA,invoke,
        lambda value:oc.validate_shape(value,SCHEMA))
    for _ in range(2):
        with pytest.raises(oc.OutputContractError):run()
    assert len(calls)==2 and work.budget()['model_reserved']==2


@pytest.mark.parametrize('recover',[True,False])
def test_native_api_navigation_length_and_publication(completed_app,monkeypatch,recover):
    api,t,runtime=completed_app;original=t.send_once;sent=[]
    api.app.state.pipeline.term_agent.profile['candidate_navigation']['length_recovery_max_tokens']=12800
    def send(**kw):
        body=kw['body'];view=json.loads(body['messages'][1]['content'])['view']
        response=original(**kw)
        if view.get('source_stage','').startswith('source-law-navigation-2'):
            sent.append(deepcopy(body))
            if len(sent)==1 or not recover:
                response['body_json']['choices'][0]['finish_reason']='length'
                # A truncated JSON object must never be salvaged or executed.
                response['body_json']['choices'][0]['message']['content']='{"next_action":"FINISH",'
        return response
    monkeypatch.setattr(t,'send_once',send)
    body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'s','request_id':'length-api'}
    result=api.post('/v1/rag/ask',json=body)
    if recover:
        assert result.status_code==200,result.text
        assert result.json()['answer']['text']=='모의 승인 기준과 예외를 적용한다.'
    else:
        assert result.status_code>=400,result.text
        assert not result.json().get('answer')
    assert [r['max_tokens'] for r in sent]==[6400,12800]
    journals=list((runtime/'legal-agent/runs').glob('*/*/journal.sqlite'));assert journals
    with sqlite3.connect(journals[-1]) as db:
        rows=[json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='LENGTH_RECOVERY_POLICY'")]
        assert any(r['action']=='FULL_DECISION' for r in rows)
        assert db.execute("SELECT count(*) FROM model_attempt WHERE response_json LIKE '%length%'").fetchone()[0]>=1


@pytest.mark.parametrize('extension',['ad_management','document_build','genos_operator_paths','shortcut_v4'])
def test_pipeline_extensions_are_typed_and_closed(extension):
    schema=json.loads((ROOT/'00_SYSTEM/SCHEMAS/pipeline-v1.schema.json').read_text())
    value=json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_text())
    Draft202012Validator(schema).validate(value)
    bad=deepcopy(value);bad.setdefault(extension,{})['unknown']=True
    errors=list(Draft202012Validator(schema).iter_errors(bad))
    assert any(e.validator=='additionalProperties' and list(e.absolute_path)==[extension] for e in errors)

    bad=deepcopy(value);bad[extension]=False
    with pytest.raises(ValidationError):Draft202012Validator(schema).validate(bad)


def test_engine_research_boundary_uses_dependency_path_not_checkout_name(tmp_path):
    import importlib.util,hashlib
    # Test the checked-in host under a checkout whose parent is called research.
    spec=importlib.util.spec_from_file_location('portable_host',ROOT/'02_BACKEND/PIPELINE/engine_host.py')
    host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
    root=tmp_path/'research'/'checkout';(root/'00_SYSTEM/SCHEMAS').mkdir(parents=True)
    for n in ('pipeline-engine-v1.schema.json',):
        (root/'00_SYSTEM/SCHEMAS'/n).write_bytes((ROOT/'00_SYSTEM/SCHEMAS'/n).read_bytes())
    original=json.loads((ROOT/'02_BACKEND/ENGINES/legal_agent/1.0.0/retrieve.json').read_text())
    original.update(inputs={},outputs={},files={})
    target=root/'02_BACKEND/ENGINES/legal_agent/1.0.0/retrieve.json';target.parent.mkdir(parents=True)
    for name,allowed in [('02_BACKEND/runtime.py',True),('02_BACKEND/lawrag/research/hidden.py',False)]:
        source=root/name;source.parent.mkdir(parents=True,exist_ok=True);source.write_text('VALUE = 1\n')
        manifest=deepcopy(original);manifest['files']={name:host.sha(source)};manifest['entrypoint']={'path':name,'function':'run'}
        target.write_text(json.dumps(manifest))
        config={'engines':{manifest['id']:{'manifest':str(target.relative_to(root)),'sha256':host.sha(target)}}}
        if allowed:assert host.engine(config,manifest['id'],'tool',root)['files']==manifest['files']
        else:
            with pytest.raises(host.ContractError,match='research code'):host.engine(config,manifest['id'],'tool',root)
    # A normal-looking alias cannot disguise a resolved research dependency.
    alias=root/'02_BACKEND/alias.py';alias.symlink_to(root/'02_BACKEND/lawrag/research/hidden.py')
    manifest=deepcopy(original);manifest['files']={'02_BACKEND/alias.py':host.sha(alias)}
    manifest['entrypoint']={'path':'02_BACKEND/alias.py','function':'run'};target.write_text(json.dumps(manifest))
    config['engines'][manifest['id']]['sha256']=host.sha(target)
    with pytest.raises(host.ContractError,match='research code'):host.engine(config,manifest['id'],'tool',root)
