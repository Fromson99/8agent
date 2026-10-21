"""Model-output contract upgrade; legacy state remains loadable."""
import copy
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent import query_scope as qs,structure_selection as ss,request_entry as entry
from semantic_runtime.legal_agent import source_query_planning as planning
from test_model_structure_selection import choose,matcher

@pytest.mark.parametrize('operator,expected',[('LT',['1','2','3']),('LTE',['1','2','3','4']),('GT',['5','6','7']),('GTE',['4','5','6','7'])])
def test_explicit_bound_operator(operator,expected):
    value=choose([{'kind':'BOUND','operator':operator,'value':{'n':4}}])
    assert ss.resolve(value,matcher(),'d',['d'])['unit_ids']==expected

def test_bound_endpoint_still_requires_stored_member():
    with pytest.raises(ss.SelectionError,match='범위의 번호'):
        ss.resolve(choose([{'kind':'BOUND','operator':'LTE','value':{'n':99}}]),matcher(),'d',['d'])

@pytest.mark.parametrize('scoped',[False,True])
def test_current_entry_requires_scope_without_breaking_legacy_admission(scoped):
    old=entry.schema(scoped)['properties']['command']['anyOf'][0]
    new=entry.schema(scoped,model=True)['properties']['command']['anyOf'][0]
    assert 'search_scope_change' not in old['required']
    assert 'search_scope_change' in new['required']
    target=new['properties']['search_scope_change']['properties']['targets']['items']
    assert 'selection' in target['required']
    validate({'document':'규정','structure':None,'selection':choose()},target)
    validate({'document':'규정','structure':None,'selection':None},target)
    with pytest.raises(ValidationError):validate({'document':'규정','structure':'제6조'},target)

def test_legacy_target_can_still_resolve_while_new_model_must_declare_selection():
    old={'operation':'REPLACE','targets':[{'document':'모의규정','structure':'제6-3조'}],'user_quote':'모의규정 제6-3조'}
    validate(old,qs.CHANGE)
    with pytest.raises(ValidationError):validate(old,qs.model_change_schema())
    new=copy.deepcopy(old);new['targets'][0]['selection']=None
    validate(new,qs.model_change_schema())
    assert qs.resolve(new,None,matcher(),['d'],old['user_quote'])==qs.resolve(old,None,matcher(),['d'],old['user_quote'])

def test_catalogue_output_cannot_omit_set_judgment():
    assert 'structure_selections' in planning.catalogue_schema(['모의규정'],model=True)['required']
    assert 'structure_selections' not in planning.catalogue_schema(['모의규정'])['required']
