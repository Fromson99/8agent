from copy import deepcopy
import itertools
import pytest
from jsonschema import Draft202012Validator as V
from semantic_runtime.legal_agent.minimal_output import Projection,_intersection
from semantic_runtime.legal_agent.errors import ProposalError
def obj(props,required=None):return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}

@pytest.mark.parametrize('extra',[False,True])
@pytest.mark.parametrize('reason',['ok','toolong'])
def test_closed_properties_and_parent_bounds(extra,reason):
    s=obj({'action':{'type':'string'},'filter':{'type':'string'},'reason':{'type':'string','maxLength':4}},['action','reason'])
    a=obj({'action':{'type':'string','const':'A'},'reason':{'type':'string','maxLength':8}})
    b=deepcopy(s);b['properties']['action']={'type':'string','const':'B'};s['anyOf']=[a,b]
    p=Projection(s);raw={'action':'A','reason':reason}
    if extra:raw['filter']='x'
    valid=not extra and len(reason)<=4
    assert V(s).is_valid(raw)==V(p.wire).is_valid(raw)==valid
    if valid:assert p.expand(raw)==raw
    else:
        with pytest.raises(ProposalError):p.expand(raw)

def test_ambiguous_fixed_variant_is_a_model_selection():
    s=obj({'action':{'type':'string'},'revision':{'type':'integer'}})
    s['anyOf']=[obj({'action':{'type':'string','const':a},'revision':{'const':r}}) for a,r in [('A',1),('A',2),('B',3)]]
    p=Projection(s)
    assert not V(p.wire).is_valid({'action':'A'})
    for value in ({'action':'A','revision':1},{'action':'A','revision':2},{'action':'B','revision':3}):
        raw=p.project(value);V(p.wire).validate(raw);assert p.expand(raw)==value

def test_finite_intersection_census():
    schemas=[True,False,{}, {'type':'string'}, {'type':['string','null']}, {'type':'number'}, {'type':'integer'},
      {'type':'string','maxLength':4},{'type':'string','minLength':2},{'enum':['a','ab','longer'],'maxLength':4},
      {'const':'ab'},{'type':'array','items':{'type':'string'},'maxItems':0},
      {'type':'array','items':{'type':'string'},'minItems':1,'maxItems':2},
      {'type':'array','items':{'enum':['a','b']},'uniqueItems':True},
      obj({'a':{'type':'string'}},[]),obj({'b':{'type':'string'}},[]),
      {'type':'object','properties':{'a':{'type':'string'}},'additionalProperties':{'type':'integer'}},
      {'type':'object','patternProperties':{'^x':{'type':'string'}},'additionalProperties':False},
      {'type':'integer','minimum':0,'maximum':4},{'type':'integer','minimum':2,'maximum':8},
      {'type':'string','pattern':'a'},{'type':'string','pattern':'b'}]
    values=[None,False,True,-1,0,1,1.5,3,5,'','a','b','ab','longer',[],['a'],['b','b'],['a','b'],[1],{},
            {'a':'a'},{'b':'b'},{'a':'a','b':2},{'x':'a'},{'x':2}]
    for left,right in itertools.product(schemas,repeat=2):
        s=_intersection(left,right);V.check_schema(s)
        for v in values:assert V(s).is_valid(v)==(V(left).is_valid(v) and V(right).is_valid(v)),(left,right,v,s)

def test_typed_structure_filter_not_advertised_for_untyped_search():
    from semantic_runtime.legal_agent.law_navigation import decision_schema
    from semantic_runtime.legal_agent.decision_projection import prepare
    from semantic_runtime.legal_agent import completion_contracts as cc
    v={'presentation_id':'v','laws':[],'basis':[],'branches':[],'issues':[{'id':'Q1','request_quote':'질문'}],
       'completion_contract':cc.V8,'investigation_scope':{'request':'질문'},'sources':[],'state_version':1}
    actions={'T1':{'id':'T1','action':'SEARCH_STRUCTURE','identity':{'document_id':'doc'},'label':'구조'},'T2':{'id':'T2','action':'READ_ARTICLES','identity':{},'label':'읽기'}}
    schema,expand,_=prepare(decision_schema(v,actions,set()),v);p=Projection(schema)
    base={'next_action':'SEARCH_STRUCTURE','targets':['T1'],'reason':'원문 찾기','evidence_sufficient':False,'sufficiency_reason':'조사 중','exploration':[{'target':'T1','issue_id':'Q1','missing_need':'원문','relation':'DIRECT'}]}
    typed={**base,'structure_filter':{'coordinate':'제1조','title':'','coordinate_scope':''}}
    untyped={**base,'queries':['질문']}
    for raw in (typed,untyped):V(p.wire).validate(raw);expand(p.expand(raw))
    assert not V(p.wire).is_valid({**typed,'queries':['질문']})
