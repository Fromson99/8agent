from types import SimpleNamespace
from copy import deepcopy
import pytest
from semantic_runtime.legal_agent import query_scope as qs
from lawrag.core.legal_coordinate import LegalCoordinate

def matcher(body=True, duplicate=False):
    co=LegalCoordinate('조',2);units={};coordinates={}
    for uid,scope,title in [('a','addendum','경과조치'),*([('b','body','정의')] if body else []),*([('c','body','중복')] if duplicate else [])]:
        units[('d',uid)]={'parent':None,'surface':'제2조','title':title,'family':'kr_article',
            'coordinate_scope':scope,'coordinate_key':scope+':제2조','coordinate_binding':{'mode':'stored'},'span':[0,1]}
        coordinates[('d',uid)]=co
    return SimpleNamespace(documents={'d':'범위검사법'},document_context={'d':{'document_title':'범위검사법'}},
        document_aliases={},units=units,stored_coordinates=coordinates)

def resolve(m,structure='제2조',selection=None,authorized=('d',)):
    return qs.resolve({'operation':'REPLACE','targets':[{'document':'범위검사법','structure':structure,'selection':selection}],
        'user_quote':'범위검사법 제2조'},None,m,authorized,'범위검사법 제2조',model_resolved=True)

@pytest.mark.parametrize('surface',['제2조','제 2 조'])
def test_legacy_article_uses_body(surface):
    assert resolve(matcher(),surface)['targets'][0]['unit_id']=='b'

@pytest.mark.parametrize('body,duplicate',[(False,False),(True,True)])
def test_missing_or_duplicate_body_does_not_pick_addendum(body,duplicate):
    with pytest.raises(qs.UnresolvedScope):resolve(matcher(body,duplicate))

@pytest.mark.parametrize('branch,expected',[('body','b'),('addendum','a')])
def test_typed_branch_stays_explicit(branch,expected):
    selection={'coordinate_scope':branch,'groups':[{'parent_path':[],'unit':'조',
        'include':[{'kind':'SINGLE','value':{'n':2}}],'exclude':[]}]}
    assert resolve(matcher(),None,selection)['targets'][0]['unit_id']==expected

def test_scope_does_not_escape_authorization():
    with pytest.raises(qs.UnresolvedScope):resolve(matcher(),authorized=())

def test_unresolved_body_is_not_readable():
    m=matcher();m.units[('d','b')]['coordinate_binding']['mode']='unresolved'
    with pytest.raises(qs.UnresolvedScope):resolve(m)

def test_explicit_addendum_title_does_not_become_body():
    assert resolve(matcher(),'경과조치')['targets'][0]['unit_id']=='a'
