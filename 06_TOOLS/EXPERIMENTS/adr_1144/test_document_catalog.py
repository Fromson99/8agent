from copy import deepcopy
import pytest
from semantic_runtime.legal_agent import stable_references as sr,compact_model_input as cm
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.errors import ContractError
from test_stable_recovery_isolated import RefRepo,view,bound

@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('restart',[False,True])
def test_authoritative_catalogue_ignores_display_alias_order(tmp_path,reverse,restart):
 path=tmp_path/'refs';repo=RefRepo(path);raw=view();raw['read_candidates'][0]['document_name']='짧은 별칭';raw['document_structures']=[{'document_id':'d1','name':'다른 화면 표시'}]
 if reverse:raw=dict(reversed(list(raw.items())))
 original=deepcopy(raw);data=cm.bind(raw,{},stable=True,document_names={'d1':'공식 카탈로그 문서명','unused':'이 문서는 노출되면 안 됨'})
 first=bound(repo,data);assert raw==original
 assert first[sr.FIELD]['documents']==[{'document_id':'d1','name':'공식 카탈로그 문서명','id':'D1'}]
 if restart:repo.db.close();repo=RefRepo(path)
 second=bound(repo,cm.bind(view(name='나중의 표시명'),{},stable=True,document_names={'d1':'공식 카탈로그 문서명'}));assert first[sr.FIELD]['documents']==second[sr.FIELD]['documents'];sr.verify(repo,first[sr.FIELD])
 wire=cm.project(NavigationReferences(second).view(second));assert wire['sources'][0]['document']=='D1';assert wire['documents']==[{'id':'D1','name':'공식 카탈로그 문서명'}];assert 'minimal_input_binding' not in wire

def test_authoritative_catalogue_name_drift_still_rejected(tmp_path):
 repo=RefRepo(tmp_path/'refs');bound(repo,cm.bind(view(),{},stable=True,document_names={'d1':'원래 문서'}))
 with pytest.raises(ContractError):bound(repo,cm.bind(view(),{},stable=True,document_names={'d1':'바뀐 문서'}))

def test_missing_catalogue_keeps_existing_conflict_guard(tmp_path):
 raw=view();raw['read_candidates'][0]['document_name']='불명확한 이름'
 with pytest.raises(ContractError):cm.bind(raw,{},stable=True,document_names={})
