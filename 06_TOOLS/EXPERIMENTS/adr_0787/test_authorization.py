"""Network-free checks for exact user authorization and unchanged default denial."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from transport import AuthorizedQwen
from semantic_runtime.legal_agent.errors import ContractError
from workflow.contracts import request
R=Path(__file__).resolve().parents[3]
D=R/'04_EXPERIMENTS/ADR/ADR-0787-risk-compare-qwen-connected/artifacts/design'

def setup(tmp_path):
 p=tmp_path/'grant.json';p.write_bytes((D/'authorization.json').read_bytes())
 t=AuthorizedQwen(R,p,tmp_path/'model');g=t.grant
 req=request(json.loads((D/'request.json').read_text()),{**g['principal'],'document_ids':g['document_ids']})
 binding={k:g[k] for k in ('generation_id','store_sha256','generation_manifest_sha256','document_ids','principal')}
 binding['export_allowed']=False
 return t,req,binding

def test_exact_authorized_binding_and_context(tmp_path):
 t,r,b=setup(tmp_path)
 assert t.authorize_workflow(r,b)
 t.validate_authorization(SimpleNamespace(binding=b,request=r,query={'scope':{'document_version_ids':r['document_ids']}}))
 assert t.client is None and t.binding['trust_zone']=='external'

@pytest.mark.parametrize('change',['question','document_ids','principal','flag','generation','grant'])
def test_changed_authorization_fails_before_network(tmp_path,change):
 t,r,b=setup(tmp_path)
 if change=='question':r['question']+=' changed'
 elif change=='document_ids':r['document_ids']=r['document_ids'][:-1]
 elif change=='principal':r['principal']={'user_id':'someone','team_id':'risk_team'}
 elif change=='flag':b['export_allowed']=True
 elif change=='generation':b['generation_id']='changed'
 else:t.grant_path.write_text('{}')
 with pytest.raises(ContractError):t.authorize_workflow(r,b)
 assert t.client is None

def test_missing_authorization_fails_before_network(tmp_path):
 t,r,b=setup(tmp_path)
 with pytest.raises(ContractError):t.validate_authorization(SimpleNamespace(binding=b,request=r,query={}))
 assert t.client is None


def test_frozen_experiment_client_available():
 from lawrag.research.experiment_client import ExperimentClient
 assert callable(ExperimentClient.chat_completions)
