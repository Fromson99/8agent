"""Research candidate's explicit export boundary, without external calls."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from lawrag.legal_knowledge.contracts import digest, KnowledgeError

ROOT=Path(__file__).resolve().parents[3]
PATH=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0958/integrated/snapshot/02_BACKEND/semantic_runtime/legal_agent/knowledge_bridge.py'
spec=importlib.util.spec_from_file_location('e2e_knowledge_bridge',PATH)
bridge=importlib.util.module_from_spec(spec)
previous=sys.dont_write_bytecode;sys.dont_write_bytecode=True
try:spec.loader.exec_module(bridge)
finally:sys.dont_write_bytecode=previous


@pytest.fixture
def bundle():
    who={'tenant_id':'tenant','team_id':'risk','user_id':'u'}
    source={'generation':'g','store_sha256':'a'*64,'unit_index_sha256':None}
    definition={'title':'Public test guide'}
    service=SimpleNamespace(definition=lambda ref,who:{'definition':definition,'document_ids':['d']})
    plan={'items':[{'ref':{'id':'guide'}}]}
    grant={'schema_version':'knowledge-export-grant-v1','principal':who,'source_binding':source,
           'question_hashes':[digest('public question')],'definition_hashes':[digest(definition)]}
    transport=SimpleNamespace(public_scope=['d'],knowledge_export_grant=grant)
    return transport,service,plan,who,source,definition


def test_exact_public_definition_is_admitted(bundle):
    t,s,p,w,b,_=bundle
    bridge.authorize_export(t,s,p,w,'public question',b)


@pytest.mark.parametrize('change',['missing_grant','question','tenant','source','definition','private_source'])
def test_nonreviewed_inputs_fail_closed(bundle,change):
    t,s,p,w,b,d=bundle;q='public question'
    if change=='missing_grant':t.knowledge_export_grant=None
    if change=='question':q='unreviewed internal question'
    if change=='tenant':w={**w,'tenant_id':'other'}
    if change=='source':b={**b,'generation':'new'}
    if change=='definition':d['title']='edited after approval'
    if change=='private_source':t.public_scope=[]
    with pytest.raises(KnowledgeError) as exc:
        bridge.authorize_export(t,s,p,w,q,b)
    assert exc.value.code=='KNOWLEDGE_EXTERNAL_EXPORT_DISABLED'
