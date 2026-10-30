from copy import deepcopy
import pytest
from semantic_runtime.legal_agent import compact_model_input as cm,stable_references as sr
from semantic_runtime.legal_agent.errors import ContractError
from test_stable_recovery_isolated import RefRepo,view,bound
@pytest.mark.parametrize('fault',['wrong_name','extra_id','bad_type','not_stable'])
def test_catalogue_receipt_preserves_durable_identity(tmp_path,fault):
 repo=RefRepo(tmp_path/'refs');v=bound(repo,cm.bind(view(),{},stable=True,document_names={'d1':'공식 문서'}));sr.verify_document_catalogue(v)
 bad=deepcopy(v);b=bad['minimal_input_binding']
 if fault=='wrong_name':b['document_names']['d1']='위조 문서'
 elif fault=='extra_id':b['document_names']['unknown']='미확보 문서'
 elif fault=='bad_type':b['document_names']=[]
 else:b['stable_references']=False
 with pytest.raises(ContractError):sr.verify_document_catalogue(bad)
 sr.verify(repo,v[sr.FIELD])
