import json
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.errors import ProposalError, TransportError
from semantic_runtime.legal_agent.output_contract import validate_shape
from test_legal_agent_double_harness import work, PROFILE, DOMAIN, wire, seed
from test_genos_output_unlimited import adapter


def obj(props):
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}


@pytest.fixture
def numbered_work(work,tmp_path):
    from semantic_runtime.legal_agent.relations_repository import RelationsRepository
    repo=RelationsRepository(tmp_path/'numbered.sqlite',work.context,PROFILE)
    yield repo
    repo.close()


@pytest.mark.parametrize('constant',['omitted','exact','conflict'])
@pytest.mark.parametrize('arity',[0,1,3])
def test_numbered_source_restoration_uses_full_schema(numbered_work,constant,arity):
    work=numbered_work
    s=obj({'revision':{'const':9},'evidence_ids':{'type':'array','items':{'type':'string'}},'quote':{'type':'string'}})
    seen=[];raw={'evidence_ids':list(range(1,arity+1)),'quote':'정확한 원문 😀'}
    if constant!='omitted':raw['revision']=9 if constant=='exact' else 10
    class T:
        binding=PROFILE['model_binding']
        def send_once(self,*,body,ticket):
            seen.append(body);return wire(raw)
    protocol=NS(schema=lambda _:deepcopy(s),validate=lambda _,v:validate_shape(v,s))
    p={**PROFILE,'numbered_references_enabled':True,'max_schema_repairs':0}
    g=ModelGateway(work,work.context,p,DOMAIN,T(),message_protocol=protocol,prompts={'investigate':'판단'})
    for i in range(arity):seed(work,ident=f'E{i+1}')
    cards=[{'evidence':f'E{i+1}',**work.evidence(f'E{i+1}')} for i in range(arity)]
    view=work.save_view('investigate',{'exact_evidence':cards},[f'E{i+1}' for i in range(arity)])
    if constant=='conflict':
        with pytest.raises(ProposalError):g.generate('investigate',view,'Synthetic')
    else:
        assert g.generate('investigate',view,'Synthetic')=={'revision':9,'evidence_ids':[f'E{i+1}' for i in range(arity)],'quote':raw['quote']}
    assert len(seen)==1
    stored=json.loads(work.db.execute('SELECT response_json FROM model_attempt').fetchone()[0])
    assert json.loads(stored['body_json']['choices'][0]['message']['content'])==raw


@pytest.mark.parametrize('protocol_name',['TurnDecision','SourceSelectionDecision'])
@pytest.mark.parametrize('reply',['complete','partial'])
def test_legacy_partial_consumer_keeps_ownership(work,protocol_name,reply):
    s=obj({'actions':{'type':'array','items':obj({'tool':{'type':'string'},'args':{'type':'object'}})}})
    raw={'actions':[{'tool':'read','args':{}}]}
    if reply=='partial':raw['actions'].append({'tool':'read','args':'malformed sibling'})
    seen=[];consumed=[]
    class T:
        binding=PROFILE['model_binding']
        def send_once(self,*,body,ticket):seen.append(body);return wire(raw)
    protocol=NS(schema=lambda _:deepcopy(s),validate=lambda _,v:consumed.append(deepcopy(v)))
    g=ModelGateway(work,work.context,{**PROFILE,'max_schema_repairs':0},DOMAIN,T(),message_protocol=protocol,prompts={'investigate':'판단'})
    view=work.save_view('investigate',{},[])
    assert g.generate('investigate',view,protocol_name)==raw
    assert consumed==[raw] and len(seen)==1
    assert seen[0]['response_format']['json_schema']['schema']==Projection(s,partial_contract=True).wire


@pytest.mark.parametrize('enabled',[False,True])
def test_existing_exact_duplicate_owner_precedes_reconstruction(work,enabled):
    s=obj({'revision':{'const':3},'law_decisions':{'type':'array','uniqueItems':True,'items':obj({'choice':{'type':'string'}})}})
    raw={'law_decisions':[{'choice':'read'},{'choice':'read'}]}
    session,calls=adapter(work,values=[raw])
    session.profile['candidate_navigation']['completion_policy_version']='investigation-completion-v8' if enabled else 'old'
    if enabled:
        assert session.structured('system',{},s,'source-law-navigation-1',60)=={'revision':3,'law_decisions':[{'choice':'read'}]}
        assert work.db.execute("SELECT COUNT(*) FROM event WHERE kind='MODEL_OUTPUT_NORMALIZED'").fetchone()[0]==1
    else:
        with pytest.raises(ProposalError):session.structured('system',{},s,'source-law-navigation-1',60)
    assert len(calls)==1


@pytest.mark.parametrize('state',['success','unknown'])
def test_transport_outcome_does_not_trigger_codec_calls(work,state):
    s=obj({'revision':{'const':2},'reason':{'type':'string'}});calls=[]
    class T:
        binding=PROFILE['model_binding']
        def send_once(self,*,body,ticket):
            calls.append(body)
            if state=='unknown':raise TransportError('synthetic',unknown=True,retryable=True)
            return wire({'reason':'필요한 근거'})
    protocol=NS(schema=lambda _:deepcopy(s),validate=lambda _,v:validate_shape(v,s))
    g=ModelGateway(work,work.context,{**PROFILE,'max_transport_retries':0},DOMAIN,T(),message_protocol=protocol,prompts={'investigate':'판단'})
    view=work.save_view('investigate',{},[])
    if state=='unknown':
        with pytest.raises(TransportError):g.generate('investigate',view,'Synthetic')
    else:assert g.generate('investigate',view,'Synthetic')=={'revision':2,'reason':'필요한 근거'}
    assert len(calls)==1 and work.budget()['model_reserved']==1
