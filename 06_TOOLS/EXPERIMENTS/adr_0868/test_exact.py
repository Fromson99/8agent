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
    schemas=[True,False,{}, {'const':True},{'const':1},{'type':'boolean'}, {'type':'string'}, {'type':['string','null']}, {'type':'number'}, {'type':'integer'},
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
       'completion_contract':cc.V8,'control_contract':'v1','investigation_scope':{'request':'질문'},'sources':[],'state_version':1}
    actions={'T1':{'id':'T1','action':'SEARCH_STRUCTURE','identity':{'document_id':'doc'},'label':'구조'},'T2':{'id':'T2','action':'READ_ARTICLES','identity':{},'label':'읽기'}}
    schema,expand,_=prepare(decision_schema(v,actions,set()),v);p=Projection(schema)
    base={'next_action':'SEARCH_STRUCTURE','targets':['T1'],'reason':'원문 찾기','evidence_sufficient':False,'sufficiency_reason':'조사 중','exploration':[{'target':'T1','issue_id':'Q1','missing_need':'원문','relation':'DIRECT'}]}
    typed={**base,'structure_filter':{'coordinate':'제1조','title':'','coordinate_scope':''}}
    untyped={**base,'queries':['질문']}
    for raw in (typed,untyped):
        wire=p.project(p.expand(raw));V(p.wire).validate(wire);expand(p.expand(wire))
    assert not V(p.wire).is_valid({**typed,'queries':['질문']})


def test_nested_anyof_restores_shared_issue_id():
    row=obj({'relation':{'enum':['DIRECT','DEPENDENCY']},'issue_id':{'const':'Q1'},'reason':{'type':'string'}})
    row['anyOf']=[obj({'relation':{'const':kind},'issue_id':{'const':'Q1'},'reason':{'type':'string'}}) for kind in ['DIRECT','DEPENDENCY']]
    branch=deepcopy(row);branch['properties']['reason']['minLength']=1
    branch['anyOf'][0]['properties']['reason']['maxLength']=12
    merged=_intersection(row,branch);p=Projection(merged)
    for kind in ['DIRECT','DEPENDENCY']:
        canonical={'relation':kind,'issue_id':'Q1','reason':'needed'}
        raw=p.project(canonical)
        assert 'issue_id' not in raw
        V(p.wire).validate(raw);assert p.expand(raw)==canonical
    for value in [{'relation':'DIRECT','issue_id':'Q1','reason':''},{'relation':'DIRECT','issue_id':'Q2','reason':'needed'}]:
        assert not V(merged).is_valid(value)


def test_nested_anyof_census_and_expansion_cap():
    alternatives=[{'anyOf':[{'type':'string','minLength':2},{'type':'integer','minimum':2}]},
                  {'anyOf':[{'type':'string','maxLength':3},{'type':'integer','maximum':3}]},
                  {'anyOf':[{'const':True},{'const':1}]},
                  {'anyOf':[{'const':n} for n in range(9)]}]
    values=[None,False,True,0,1,2,3,4,8,'','a','ab','abcd',{},[]]
    for left,right in itertools.product(alternatives,repeat=2):
        combined=_intersection(left,right);V.check_schema(combined)
        for value in values:assert V(combined).is_valid(value)==(V(left).is_valid(value) and V(right).is_valid(value))
    other={'anyOf':[{'const':n} for n in range(1,10)]}
    assert 'allOf' in _intersection(alternatives[-1],other)


def test_impossible_required_property_branch_is_false():
    a=obj({'kind':{'const':'A'},'issue':{'const':'Q1'}})
    b=obj({'kind':{'const':'B'},'issue':{'const':'Q1'}})
    assert _intersection(a,b) is False
    merged=_intersection({'type':'object','anyOf':[a,b]}, {'type':'object','anyOf':[dict(a,description='branch'),b]})
    assert len(merged['anyOf'])==2
    p=Projection(merged)
    assert p.expand({'kind':'A'})=={'kind':'A','issue':'Q1'}
    assert p.expand({'kind':'B'})=={'kind':'B','issue':'Q1'}


def test_one_sided_properties_intersect_additional_rules():
    rules=[{'type':'object','properties':{'a':{'type':'string'}}},
           {'additionalProperties':False}, {'additionalProperties':{'type':'integer'}},
           obj({'a':{'type':'string'}},[])]
    for a,b in itertools.product(rules,repeat=2):
        merged=_intersection(a,b)
        for value in [{},{'a':'x'},{'a':1},{'b':1},1,None]:
            assert V(merged).is_valid(value)==(V(a).is_valid(value) and V(b).is_valid(value))


@pytest.mark.parametrize('bounds',[{'minProperties':2,'maxProperties':2},{'minProperties':1,'maxProperties':3}])
def test_object_counts_exclude_host_literals_on_wire(bounds):
    schema={**obj({'id':{'const':'host'},'reason':{'type':'string'}},['id','reason']),**bounds}
    p=Projection(schema);raw=p.project({'id':'host','reason':'why'})
    assert raw=={'reason':'why'};V(p.wire).validate(raw)
    assert p.expand(raw)=={'id':'host','reason':'why'}


def test_navigation_target_is_selected_once_and_host_deduplicates():
    from semantic_runtime.legal_agent.law_navigation import decision_schema
    from semantic_runtime.legal_agent.decision_projection import prepare
    from semantic_runtime.legal_agent import completion_contracts as cc
    from semantic_runtime.legal_agent.output_contract import OutputContractError
    view={'presentation_id':'v','laws':[],'basis':[],'branches':[],
          'issues':[{'id':'Q1','request_quote':'첫 질문'},{'id':'Q2','request_quote':'둘째 질문'}],
          'completion_contract':cc.V8,'control_contract':'v1','investigation_scope':{'request':'첫 질문 둘째 질문'},'sources':[],'state_version':1}
    actions={k:{'id':k,'action':'READ_ARTICLES','identity':{},'label':'읽기'} for k in ['T1','T2']}
    canonical=decision_schema(view,actions,set());schema,expand,receipt=prepare(canonical,view);p=Projection(schema)
    raw={'next_action':'READ_ARTICLES','reason':'필요 원문 읽기','evidence_sufficient':False,'sufficiency_reason':'조사 중',
         'exploration':[{'target':t,'issue_id':i,'missing_need':'원문','relation':'DIRECT'} for t,i in [('T1','Q1'),('T1','Q2'),('T2','Q2')]]}
    raw=p.project(p.expand(raw))
    V(p.wire).validate(raw)
    restored=p.expand(raw);value=expand(restored);V(canonical).validate(value)
    assert value['targets']==['T1','T2'] and value['issue_refs']==['Q1','Q2']
    assert all(r['request_quote']=={'Q1':'첫 질문','Q2':'둘째 질문'}[r['issue_id']] for r in value['exploration'])
    assert 'targets' in receipt['system_derived_fields']
    assert not V(p.wire).is_valid({**raw,'targets':['T1','T2']})
    assert expand({**restored,'targets':['T1','T2']})==value
    assert expand({**restored,'targets':['T2','T1']})['targets']==['T2','T1']
    with pytest.raises(OutputContractError,match='targets conflict'):
        expand({**restored,'targets':['T1']})
    bad=deepcopy(raw);bad['exploration'][0]['target']='unoffered'
    assert not V(p.wire).is_valid(bad)
    with pytest.raises(ProposalError):p.expand(bad)


@pytest.mark.parametrize('action',['RESEARCH','SEARCH_STRUCTURE','READ_PARENT'])
def test_single_target_keeps_cardinality_and_never_repeats_target(action):
    from semantic_runtime.legal_agent.law_navigation import decision_schema
    from semantic_runtime.legal_agent.decision_projection import prepare
    from semantic_runtime.legal_agent import completion_contracts as cc
    from semantic_runtime.legal_agent.output_contract import OutputContractError
    view={'presentation_id':'v','laws':[],'basis':[],'branches':[],'issues':[{'id':'Q1','request_quote':'질문'}],
          'completion_contract':cc.V8,'control_contract':'v1','investigation_scope':{'request':'질문'},'sources':[],'state_version':1}
    actions={k:{'id':k,'action':action,'identity':{},'label':'조사'} for k in ['T1','T2']}
    canonical=decision_schema(view,actions,set());schema,expand,receipt=prepare(canonical,view);p=Projection(schema)
    legacy={'next_action':action,'targets':['T2'],'reason':'필요 원문','evidence_sufficient':False,'sufficiency_reason':'조사 중',
            'exploration':[{'target':'T2','issue_id':'Q1','missing_need':'원문','relation':'DIRECT'}]}
    if action in ('RESEARCH','SEARCH_STRUCTURE'):legacy['queries']=['원문']
    raw=p.project(p.expand(legacy));assert raw['targets']==['T2'] and 'target' not in raw['exploration'][0]
    V(p.wire).validate(raw);restored=p.expand(raw);value=expand(restored)
    V(canonical).validate(value);assert value['exploration'][0]['target']=='T2'
    assert not V(p.wire).is_valid({**raw,'targets':['T1','T2']})
    assert expand(legacy)==value
    contradictory=deepcopy(legacy);contradictory['exploration'][0]['target']='T1'
    with pytest.raises(OutputContractError,match='targets conflict'):expand(contradictory)
