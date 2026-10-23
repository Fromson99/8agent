from copy import deepcopy
import json
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent.wire_schema import factor_schema
from semantic_runtime.legal_agent.gateway import compact_wire_view
from semantic_runtime.legal_agent.law_navigation import decision_schema, _strings


def expand(schema):
    defs=schema.get('$defs',{})
    def walk(v):
        if isinstance(v,list):return [walk(x) for x in v]
        if isinstance(v,dict):
            if set(v)=={'$ref'}:return walk(defs[v['$ref'].split('/')[-1]])
            return {k:walk(x) for k,x in v.items() if k!='$defs'}
        return v
    return walk(schema)


def union_schema():
    item={'type':'object','properties':{'id':{'type':'string','enum':['evidence-'+str(i) for i in range(30)]},'text':{'type':'string'}},'required':['id','text'],'additionalProperties':False}
    return {'type':'object','anyOf':[{'type':'object','properties':{'next_action':{'const':a},'evidence':{'type':'array','items':deepcopy(item)}},'required':['next_action','evidence'],'additionalProperties':False} for a in ['READ','FINISH','RETURN']]}


def test_factor_expands_to_exact_original_without_mutation():
    original=union_schema();before=deepcopy(original);wire=factor_schema(original)
    assert original==before and expand(wire)==original and '$defs' in wire
    Draft202012Validator.check_schema(wire)
    assert len(json.dumps(wire))<len(json.dumps(original))


@pytest.mark.parametrize('value',[{'next_action':'READ','evidence':[]},{'next_action':'FINISH','evidence':[{'id':'evidence-2','text':'원문'}]},{'next_action':'DROP','evidence':[]},{'next_action':'FINISH','evidence':[{'id':'unoffered','text':'가짜'}]},{'next_action':'READ'},{'next_action':'READ','evidence':[], 'extra':True}])
def test_factor_preserves_allowed_and_rejected_language(value):
    schema=union_schema()
    assert Draft202012Validator(schema).is_valid(value)==Draft202012Validator(factor_schema(schema)).is_valid(value)


def test_schema_literals_are_never_interpreted_as_schema_nodes():
    s=union_schema();literal={'type':'object','properties':{'text':{'type':'string'}}};s['anyOf'][0]['properties']['literal']={'enum':[literal,literal]}
    assert expand(factor_schema(s))==s


@pytest.mark.parametrize('schema',[{'$ref':'#/$defs/x','$defs':{'x':{'type':'string'}}},{'$id':'https://example.invalid/schema','type':'string'},{'type':'boolean'}])
def test_existing_scope_and_small_schema_unchanged(schema):
    assert factor_schema(schema)==schema


def test_wire_keeps_every_original_and_selectable_quote_with_source_identity():
    text='① 승인한다. 다만 예외에는 적용하지 않는다.\n② 통지해야 한다.'
    source={'source_id':'public:a','text':text,'spans':[{'block_id':'1','evidence_id':'E1','start_cp':0,'end_cp':len(text),'text':text,'span_hash':'a'*64}]}
    option={'id':'S1','source_id':'public:a','block_id':'1','start_cp':0,'end_cp':len(text),'text':text,'text_hash':'b'*64}
    v={'input_projection':'compact-selection-source-v2','sources':[source],'evidence_options':[option,{**option,'id':'S2','source_id':'different:a'}]};before=deepcopy(v)
    w=compact_wire_view(v,'investigate');assert v==before
    assert w['sources'][0]['text']==text and w['evidence_options'][1]['text']==text
    ref=w['evidence_options'][0]['text_ref'];assert w['sources'][0]['text'][ref['start']:ref['end']]==text
    assert w['evidence_options'][0]['id']=='S1' and 'text_hash' not in w['evidence_options'][0]
    assert w['sources'][0]['spans'][0]['start_cp']==0


def menu():
    v={'presentation_id':'p','laws':[],'basis':[],'branches':[],'issues':[{'id':'Q1'}]}
    a={n:{'id':n,'action':'SEARCH_STRUCTURE','identity':{'document_id':d}} for n,d in [('global',None),('doc','d')]}
    return decision_schema(v,a,set())


def decision(target,queries,filters=None):
    d={'presentation_id':'p','law_decisions':[],'branch_decisions':[],'next_action':'SEARCH_STRUCTURE','targets':[target],'queries':queries,'issue_refs':['Q1'],'basis_refs':[],'reason':'원문 확인','notes':'','evidence_sufficient':False,'sufficiency_reason':''}
    if filters is not None:d['structure_filter']=filters
    return d


@pytest.mark.parametrize('target,queries,filters,valid',[
 ('global',['규정'],None,True),('doc',['제1조'],None,True),
 ('doc',[],{'coordinate':'제1조','title':'','coordinate_scope':'body'},True),
 ('global',[],{'coordinate':'제1조','title':'','coordinate_scope':'body'},False),
 ('doc',['중복'],{'coordinate':'제1조','title':'','coordinate_scope':'body'},False),
 ('global',[],None,False),('unknown',['규정'],None,False)])
def test_structure_schema_only_offers_executable_target_shape(target,queries,filters,valid):
    schema=menu();assert Draft202012Validator(schema).is_valid(decision(target,queries,filters)) is valid


@pytest.mark.parametrize('field', ['basis_refs', 'issue_refs', 'targets'])
def test_reference_grammar_bounds_distinct_offered_ids(field):
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    from semantic_runtime.legal_agent.errors import ProposalError
    ids=['E'+'a'*24, 'E'+'b'*24]
    refs=NavigationReferences({'basis':[{'id':x} for x in ids]})
    schema={'type':'object','properties':{field:_strings(set(ids))},'required':[field]}
    before=deepcopy(schema);wire=refs.schema(schema);node=wire['properties'][field]
    assert schema==before and node['maxItems']==2 and node['uniqueItems'] is True
    values=[refs.forward[x] for x in ids]
    assert refs.decode({field:values},wire)=={field:ids}
    with pytest.raises(ProposalError): refs.decode({field:[values[0]]*3},wire)
    with pytest.raises(ProposalError): refs.decode({field:[values[0]]*2},wire)


def test_reference_bound_preserves_tighter_action_budget():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    schema={'properties':{'targets':{**_strings({'A1','A2'}),'maxItems':1}}}
    assert NavigationReferences({}).schema(schema)['properties']['targets']['maxItems']==1


def test_reference_bounds_do_not_touch_text_sequences():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    schema={'properties':{'queries':{'type':'array','items':{'type':'string','enum':['원문','원문']}}}}
    assert NavigationReferences({}).schema(schema)==schema


def test_empty_offered_reference_set_remains_empty():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    schema={'properties':{'basis_refs':_strings(set())}}
    assert NavigationReferences({}).schema(schema)['properties']['basis_refs']['maxItems']==0


def test_native_reference_grammar_is_bounded_after_factoring():
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    schema=NavigationReferences({}).schema(menu());wire=factor_schema(schema)
    assert Draft202012Validator(wire).is_valid(decision('global',['규정']))
    duplicate=decision('global',['규정']);duplicate['issue_refs']=['Q1']*100
    assert not Draft202012Validator(wire).is_valid(duplicate)
    assert expand(wire)==schema


@pytest.mark.parametrize('mixed', [False, True])
def test_shared_navigation_metadata_roundtrip_keeps_originals_and_choices(mixed):
    from semantic_runtime.legal_agent.navigation_input import compact_cards, expand_cards
    location={'document_id':'d','unit_id':'12','path':'장/절/조/항의 정확한 위치 '*20}
    sources=[{'id':'E1','text':'① 원문이다. ② 단서를 보존한다.','spans':[{'block_id':'1','text':'① 원문이다.'}]}]
    rows=[{'id':'T'+str(i),'choice':'READ','location':deepcopy(location),'reason':'선택 가능'} for i in range(12)]
    if mixed:rows += [{'id':'F'+str(i),'choice':'FOLLOW_CONNECTION','selected_scope':deepcopy(location)} for i in range(12)]
    v={'tool_options':rows,'already_read':[deepcopy(location)]*5,'sources':sources,'exact_evidence':deepcopy(sources)}
    before=deepcopy(v);wire=compact_cards(v)
    assert v==before and expand_cards(wire)==before
    assert compact_cards(json.loads(json.dumps(v,sort_keys=True)))==wire
    assert wire['sources']==sources and wire['exact_evidence']==sources
    assert len(json.dumps(wire))<len(json.dumps(v))*.6
    assert 'shared_navigation_cards' in wire


def test_segmented_tables_preserve_mixed_action_order_and_absent_fields():
    from semantic_runtime.legal_agent.navigation_input import compact_cards, expand_cards
    rows=[{'action':'READ','scope':'scope'+str(i),'long_unique_location_field':'node'+str(i)} for i in range(9)]
    rows += [{'action':'RETURN','previous_frame_identifier':'frame'+str(i),'scope':None} for i in range(9)]
    v={'tool_options':rows};wire=compact_cards(v)
    assert 'navigation_segments' in wire['tool_options']
    assert expand_cards(wire)==v
    assert 'previous_frame_identifier' not in expand_cards(wire)['tool_options'][0]


@pytest.mark.parametrize('pool', [{}, {'N1':{'navigation_card_ref':'N1'}}])
def test_shared_navigation_card_rejects_missing_or_cyclic_reference(pool):
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    with pytest.raises(ValueError,match='shared navigation card'):
        expand_cards({'shared_navigation_cards':pool,'tool_options':{'navigation_card_ref':'N1'}})
