"""Synthetic integrity tests, not a legal answer-quality experiment."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import pytest

spec = importlib.util.spec_from_file_location('lab_runner', Path(__file__).with_name('run_lab.py'))
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
workspace, baseline, snapshot = runner.load()
from knowledge_lab.demo import dataset, atom, SCOPE
from knowledge_lab.logic import solve, compose, check_proof, digest, validate, decompose_wiki
from knowledge_lab.storage import Sandbox, Catalogue, readonly
from knowledge_lab.app import create_app


def execute(data):
    return solve(data['kb'], data['facts'], data['goal'], data['context'])


def test_unseen_path_and_proof_roundtrip():
    d=dataset();result=execute(d)
    assert result['status']=='CONDITIONAL'
    assert {x['id'] for x in result['proof']['dependencies']} == {'wiki-1','wiki-2','wiki-4'}
    proof=json.loads(json.dumps(result['proof'],sort_keys=True))
    assert check_proof(d['kb'],proof,d['context'])


def test_no_reverse_implication():
    d=dataset();d['facts']=[{**d['facts'][0],'atom':atom('D','대상1')}];d['goal']=atom('A','대상1')
    assert execute(d)['status']=='UNKNOWN'


def test_missing_premise_is_obligation():
    d=dataset();d['facts']=d['facts'][:2]
    result=execute(d)
    assert result['status']=='UNKNOWN'
    assert atom('C','대상1') in result['missing']


@pytest.mark.parametrize('change',['subject','case','date','jurisdiction','generation'])
def test_fact_scope_isolation(change):
    d=dataset();f=d['facts'][-1]
    if change=='subject':f['atom']['args']=['대상2']
    elif change=='case':f['case_id']='different-case'
    elif change=='date':f['scope']['valid_to']='2025-01-01'
    else:f['scope'][change]='different'
    assert execute(d)['status']=='UNKNOWN'


def test_unreviewed_and_unknown_scope_block():
    for field,value in [('formalization','DRAFT'),('jurisdiction','UNKNOWN')]:
        d=dataset();u=d['kb']['units'][0]
        (u['assessments'] if field=='formalization' else u['scope'])[field]=value
        assert execute(d)['status']=='UNKNOWN'


def test_weak_rule_never_becomes_strong():
    d=dataset();d['kb']['units'][0]['kind']='HYPOTHESIS'
    result=execute(d)
    assert 'HYPOTHESIS:wiki-1' in result['proof']['assumptions']
    composed=compose(d['kb'],[atom('A'),atom('C')],atom('D'),d['context'])
    assert 'HYPOTHESIS:wiki-1' in composed['derived']['assumptions']


def test_exception_guard_required_and_positive():
    d=dataset();u=d['kb']['units'][0];u.update(exceptions=['special exception'],exceptions_resolved=False)
    assert execute(d)['status']=='UNKNOWN'
    u.update(exceptions_resolved=True,guards=[atom('Y')])
    assert execute(d)['proof']
    u['guards']=[atom('Y',negative=True)]
    assert execute(d)['status']=='UNKNOWN'


def test_conflict_blocks_dependents_without_explosion():
    d=dataset();d['facts'].append({**deepcopy(d['facts'][0]),'id':'contrary','atom':atom('A','대상1',True)})
    assert execute(d)['status']=='UNKNOWN'
    d['goal']=atom('A','대상1')
    assert execute(d)['status']=='CONFLICT'


def test_seedless_cycle_does_not_prove():
    d=dataset();d['kb']['units']=d['kb']['units'][:1]
    back={**deepcopy(d['kb']['units'][0]),'id':'back','body':[atom('B')],'head':atom('A')}
    d['kb']['units'].append(back);d['facts']=[];d['goal']=atom('A','대상1')
    assert execute(d)['status']=='UNKNOWN'


def test_access_intersection_and_no_disclosure():
    d=dataset();d['kb']['units'][0]['access']=['other']
    result=execute(d);assert result['status']=='UNKNOWN'
    assert 'wiki-1' not in json.dumps(result)
    d['kb']['units'][0]['access']=['local-operator','another']
    d['kb']['units'][0]['external_export_allowed']=False
    result=execute(d);assert result['proof']['access']==['local-operator']
    assert result['proof']['external_export_allowed'] is False


def test_proof_forgery_and_revocation_rejected():
    d=dataset();proof=execute(d)['proof'];bad=deepcopy(proof);bad['goal']=atom('X','대상2')
    bad['hash']=digest({k:v for k,v in bad.items() if k!='hash'})
    assert not check_proof(d['kb'],bad,d['context'])
    d['kb']['units'][0]['state']='RETIRED'
    assert not check_proof(d['kb'],proof,d['context'])


def test_definition_equivalence_and_not_reverse_effect():
    d=dataset();d['facts']=[{**d['facts'][0],'atom':atom('K','대상1')}]
    assert execute(d)['proof']
    d['facts'][0]['atom']=atom('D','대상1');d['goal']=atom('K','대상1')
    assert execute(d)['status']=='UNKNOWN'


def test_symbolic_composition_has_conditions_and_source_dependencies():
    d=dataset();r=compose(d['kb'],[atom('X'),atom('Y'),atom('C')],atom('D'),d['context'])
    assert r['derived']['head']==atom('D')
    assert len(r['derived']['dependencies'])==3
    assert r['derived']['assumptions']==[]


def test_no_case_fact_generalization():
    d=dataset();u=deepcopy(d['kb']['units'][0]);u.update(id='case-fact',kind='FACT',body=[],head=atom('D','대상1'),case_id='demo-case')
    d['kb']['units']=[u]
    assert not compose(d['kb'],[atom('A')],atom('D'),d['context']).get('derived')


def test_type_and_unsafe_variable_rejected():
    d=dataset();d['kb']['units'][0]['head']['args']=['?y']
    with pytest.raises(ValueError):validate(d['kb'])
    d=dataset();d['context']['entities']['대상1']='Person'
    with pytest.raises(ValueError):execute(d)


def test_binary_join_same_entity():
    d=dataset();d['kb']['predicates'].append({'id':'Owns','label':'owns','types':['Entity','Entity']})
    u=deepcopy(d['kb']['units'][0]);u.update(id='join',body=[{'predicate':'Owns','args':['?x','?y']},atom('C','?y')],head=atom('D','?x'))
    d['kb']['units']=[u]
    f=deepcopy(d['facts'][0]);f.update(id='owns',atom={'predicate':'Owns','args':['대상1','대상2']})
    d['facts']=[f,d['facts'][-1]]
    assert execute(d)['status']=='UNKNOWN'
    d['facts'][-1]['atom']['args']=['대상2']
    assert execute(d)['proof']


def test_structural_atomization_does_not_invent_rule():
    rows=decompose_wiki({'unit_id':'w','claims':[{'statement':'A then B','evidence_refs':['s']}],'core_evidence_route':{'targets':[]}})
    assert {x['kind'] for x in rows}=={'RULE','PROCEDURE'}
    assert all(x['formula'] is None and x['formalization']=='DRAFT' for x in rows)


def test_sandbox_revision_history_and_derived_withdrawal(tmp_path):
    s=Sandbox(tmp_path);d=dataset()
    for p in d['kb']['predicates']:s.put('predicate',p['id'],p,0)
    for u in d['kb']['units']:s.save_unit(u,0)
    u=s.kb()['units'][0]
    with pytest.raises(ValueError):s.save_unit(u,0)
    derived={**deepcopy(u),'id':'derived-unit','revision':1,'derivation_dependencies':[{'id':u['id'],'revision':1,'hash':digest(u)}]}
    s.put('unit','derived-unit',derived,0)
    s.put('unit',u['id'],{**u,'state':'RETIRED'},1)
    assert next(x for x in s.kb()['units'] if x['id']=='derived-unit')['state']=='STALE'
    assert len(s.history('unit',u['id']))==2


def test_real_catalogue_is_read_only():
    c=Catalogue(workspace,baseline);status=c.status();assert status['ontology']['term']>0
    rows=c.list('shortcuts',limit=1);assert rows['total']>=51
    detail=c.detail(rows['items'][0]['id']);assert detail['source_mode']=='READ_ONLY'
    with readonly(c.memory) as db:
        with pytest.raises(Exception):db.execute('CREATE TABLE illegal(x)')
    assert c.ontology('투자',limit=2)['items']


def test_api_security_storage_proof_and_public_gate(tmp_path):
    from fastapi.testclient import TestClient
    app=create_app(workspace,baseline,tmp_path,Path(__file__).with_name('run_lab.py'),token='test-token')
    headers={'X-Lab-Token':'test-token'}
    with TestClient(app) as api:
        assert api.get('/').status_code==200
        assert api.get('/api/status').status_code==403
        assert api.post('/api/demo',headers={**headers,'Origin':'https://evil.invalid'},json={}).status_code==403
        assert api.get('/api/status',headers={**headers,'Host':'evil.invalid'}).status_code==403
        assert api.post('/api/demo',headers=headers,json={}).status_code==200
        d=dataset();r=api.post('/api/prove',headers=headers,json={k:d[k] for k in ['facts','goal','context']})
        assert r.status_code==200 and r.json()['proof']
        request={'premises':[atom('X'),atom('Y'),atom('C')],'goal':atom('D'),'context':d['context']}
        derived=api.post('/api/derived',headers=headers,json=request)
        assert derived.status_code==200,derived.text
        assert api.get('/api/kb',headers=headers).json()['derived']
        again=api.post('/api/derived',headers=headers,json=request)
        assert again.json()['already_saved'] is True
        assert len(api.get('/api/kb',headers=headers).json()['derived'])==1
        d['facts'].append({**deepcopy(d['facts'][0]),'id':'not-B','atom':atom('B','대상1',True)})
        blocked=api.post('/api/prove',headers=headers,json={k:d[k] for k in ['facts','goal','context']})
        assert blocked.json()['status']=='UNKNOWN', 'A cached lemma must not bypass a contradiction in its intermediate proof'
        assert api.post('/api/ask',headers=headers,json={'question':'private','public_question':False}).status_code==422
        assert api.get('/v1/rag/memory/command',headers=headers).status_code==404


def test_main_and_working_bindings_unchanged():
    assert runner.sha(workspace.path('data')/'ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256']
    for name,expected in baseline['working_files'].items():assert runner.sha(workspace.root/name)==expected
