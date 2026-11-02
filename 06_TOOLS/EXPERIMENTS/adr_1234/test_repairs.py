from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace as S
import json,gzip,pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_assessment as oa, ontology_context as oc
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.errors import ContractError
R=Path('/home/jin/8-AGENT');P=R/'04_EXPERIMENTS/ADR/ADR-1233-gold-ontology-on-live/artifacts/run-001/live/gold-369'
@pytest.mark.parametrize('n',['006','007'])
def test_actual_generated_claims_keep_distinct_ids(n):
 v=json.load(gzip.open(P/'canonical'/f'{n}.json.gz','rt'))['view'];raw=json.loads(json.load(gzip.open(P/'raw'/n/'response.json.gz','rt'))['choices'][0]['message']['content'])
 refs=NavigationReferences(v);assert refs.reverse['C1']=='C3'
 out=refs.restore(raw);assert [c['claim_id'] for c in out['claims']]==['C1','C2','C3']
 assert out['read_judgment_review']['judgments'][0]['claim_refs']==['C1','C2','C3']
 assert out['claims'][0]['evidence_refs']!=raw['claims'][0]['evidence_refs']
 assert out['claims'][0]['rule']['norms'][0]['text']==raw['claims'][0]['rule']['norms'][0]['text']
 assert refs.restore({'claim_refs':['C1']})=={'claim_refs':['C3']}

def fixture(monkeypatch):
 text='검증된 원문이다.';anchor={'document_id':'d','version':'a'*64,'unit_id':'1','label':'조문','content_sha256':oa.compiler.content_hash(text)}
 b={'schema_version':'ontology-bundle-v0','bundle_id':'cb-test','revision':1,'status':'APPROVED','concept':{'label':'합성','glossary_ref':None,'kind':'NEW_CONCEPT_CANDIDATE'},'provisions':[{'anchor':anchor,'role':'SCOPE','value':None,'note':''}],'relations':[],'review_notes':[],'evidence_judgments':[],'proposed_by':{'model':None,'run_id':'synthetic','at':'2026-10-30T00:00:00Z'},'history':[]}
 snapshot={'schema_version':'ontology-snapshot-v0','bundles':[b]};settings={'mode':'A1','snapshot':snapshot,'snapshot_sha256':digest(snapshot)};profile={'candidate_navigation':{'ontology_enabled':True,'ontology_direct_assessment':True,'completion_contract':True,'ontology_context':settings}}
 plan={'id':digest(['bind',settings['snapshot_sha256'],b['bundle_id']]),'bundle_id':b['bundle_id'],'status':'ACQUIRED','unresolved':[],'remaining_connections':[],'scan':{},'fragments':[{'anchor':anchor,'source_id':'s','block_ids':['1'],'evidence_ids':['old-read']} ]}
 state={'binding':'bind','ontology_context':{'version':oc.VERSION,'snapshot_sha256':settings['snapshot_sha256'],'plans':{'p':plan}}}
 span={'block_id':'1','start_cp':0,'end_cp':len(text),'text':text,'evidence_id':'new-read'};src={'source_id':'s','document_id':'d','adopted_spans':[span]};opt={**span,'id':'S-current','source_id':'s','document_id':'d'}
 session=S(profile=profile,store=S(source=lambda did,bid:{'text':text}))
 monkeypatch.setattr(oc,'resolve',lambda sess,a:(({'source_id':'s'},{'block_ids':['1']}),None))
 return session,state,[src],[opt]

def test_equivalent_new_read_receipt_rebinds(monkeypatch):
 args=fixture(monkeypatch);card=oa.project(*args)['ontology_bundles'][0]['payload'];assert card['status']=='COMPLETE';assert card['provisions'][0]['source_refs']==['S-current']
@pytest.mark.parametrize('mode',['missing','partial','other-receipt','changed-text','wrong-document','stale-anchor'])
def test_missing_changed_or_unbound_original_still_blocked(monkeypatch,mode):
 session,state,sources,options=fixture(monkeypatch)
 if mode=='missing':sources[0]['adopted_spans']=[]
 if mode=='partial':sources[0]['adopted_spans'][0]['end_cp']-=1;sources[0]['adopted_spans'][0]['text']=sources[0]['adopted_spans'][0]['text'][:-1]
 if mode=='other-receipt':options[0]['evidence_id']='unbound'
 if mode=='changed-text':sources[0]['adopted_spans'][0]['text']='위조된 원문이다.'
 if mode=='wrong-document':sources[0]['document_id']='other'
 if mode=='stale-anchor':monkeypatch.setattr(oc,'resolve',lambda *a:(None,'SOURCE_VERSION_CHANGED'))
 if mode in ('changed-text','wrong-document','stale-anchor'):
  with pytest.raises(ContractError):oa.project(session,state,sources,options)
 else:
  card=oa.project(session,state,sources,options)['ontology_bundles'][0]['payload'];assert card['status']=='PARTIAL' and card['provisions'][0]['source_refs']==[]
