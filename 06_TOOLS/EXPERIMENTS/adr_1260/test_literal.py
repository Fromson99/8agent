from copy import deepcopy
import pytest
from test_domain_profile_workflow import env
from semantic_runtime.legal_agent.errors import ContractError


def offered(env,monkeypatch):
 reader=env.w.glossary.reader
 reader.dbs['lookup'].execute('INSERT INTO label VALUES (?,?)',('dictionary','term2'))
 exact={**reader.card('dictionary','term1'),'match':'EXACT_SURFACE'}
 broad={**reader.card('dictionary','term2'),'match':'LABEL_TOKEN_CANDIDATE'}
 def lookup(label,**kwargs):
  return {'concepts':[deepcopy(exact if label=='exact' else broad)],'total':1,'next_offset':None}
 monkeypatch.setattr(reader,'lookup',lookup)
 original=env.w.glossary.restore;seen=[]
 def restore(source,node):seen.append(node);return original(source,node)
 monkeypatch.setattr(env.w.glossary,'restore',restore)
 return reader,seen


def test_automatic_fragments_do_not_hydrate_broad_matches(env,monkeypatch):
 reader,seen=offered(env,monkeypatch)
 v=env.w.glossary.candidates(['exact','broad'],exact_only=True)
 assert seen==['term1']
 assert [r['node_id'] for r in v['candidates']]==['term1']
 assert v['unsearched'] is True and v['query_policy']=='AUTOMATIC_EXACT_SURFACE_ONLY'
 assert v['queries'][1]['deferred_token_candidates']==1
 assert env.w.glossary.verify_candidates(v)==v
 assert seen==['term1','term1'] # A new validation re-reads the retained current source.


def test_explicit_lookup_preserves_full_candidates_and_fresh_validation(env,monkeypatch):
 reader,seen=offered(env,monkeypatch)
 v=env.w.glossary.candidates(['exact','broad'])
 assert seen==['term1','term2']
 assert len(v['candidates'])==2 and not v['unsearched']
 assert 'query_policy' not in v
 reader.changed=True
 with pytest.raises(ContractError,match='changed'):env.w.glossary.verify_candidates(v)


def test_deferred_is_not_a_claim_that_no_glossary_match_exists(env,monkeypatch):
 offered(env,monkeypatch)
 v=env.w.glossary.candidates(['broad'],exact_only=True)
 assert not v['candidates'] and v['unsearched'] and v['queries'][0]['total']==1


@pytest.mark.parametrize('labels',[None,['explicit']])
def test_normalization_distinguishes_automatic_and_explicit_queries(env,monkeypatch,labels):
 calls=[];fn=env.w.glossary.candidates
 def candidates(q,**kwargs):calls.append(kwargs['exact_only']);return fn(q,**kwargs)
 monkeypatch.setattr(env.w.glossary,'candidates',candidates)
 r=env.w.import_payload('가상 용어 기록',run_id='literal',event_id='literal')
 result=env.w.normalize(r['bundle_id'],profile_id=env.profile_id,profile_work_hash=env.profile_work_hash,labels=labels)
 value=env.w.load(result['bundle_id'])['normalized']['glossary_candidates']
 assert calls==[labels is None]
 assert value['query_origin']==('BOUNDED_LITERAL_CANDIDATES' if labels is None else 'EXPLICIT_LABEL_QUERIES')
