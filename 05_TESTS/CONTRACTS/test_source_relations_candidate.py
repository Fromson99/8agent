"""Synthetic typed relation/proposal contracts; no authenticated human review claims."""
from copy import deepcopy
from types import SimpleNamespace
import sqlite3
import pytest
from semantic_runtime.legal_agent.source_relations import RelationStore, verify_anchor, read_target
from semantic_runtime.legal_agent.source_tools import SourceSession
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.legal_agent.errors import ContractError

@pytest.fixture
def data(tmp_path):
    texts={'1':'모의 규정 단서','2':'모의 세칙 위임 구체화','3':'모의 세칙 두 번째 경우'}
    raw=lambda d,b:{'text':texts[b],'source_artifact_sha256':'b'*64}
    section=lambda d,u:{'blocks':[{'block_id':b,'text':texts[b]} for b in (['1'] if u=='1' else ['2','3'])]}
    store=SimpleNamespace(manifest={'generation_id':'g','store_sha256':'a'*64},source=raw,section=section)
    sources=SimpleNamespace(scope=['d'],context=SimpleNamespace(query={'generation_id':'g'}),store=store,
        tools=SimpleNamespace(sources={'reg':{'document_id':'d','blocks':[{'block_id':'1'}]},
                                      'rule':{'document_id':'d','blocks':[{'block_id':'2'},{'block_id':'3'}]}}))
    sources.verify=lambda e:SourceSession.verify(sources,e)
    def anchor(i,sid,uid,blocks):
        return {'id':i,'generation_id':'g','store_sha256':'a'*64,'document_id':'d','source_id':sid,
            'unit_id':uid,'coordinate':'합성 '+uid,'selector':{'kind':'subtree','source_artifact_hash':'b'*64,
            'spans':[{'block_id':b,'start_cp':0,'end_cp':len(texts[b]),'text':texts[b],
                      'block_hash':text_hash(texts[b]),'span_hash':text_hash(texts[b])} for b in blocks]}}
    a=anchor('A','reg','1',['1']);b=anchor('B','rule','2',['2','3'])
    relation={'id':'R1','relation_id':'R','revision':1,'relation_type':'SPECIFIES_DELEGATED_CASES_OF',
              'from_anchor':'B','to_anchor':'A','qualifiers':{'target_role':'proviso'},
              'witness':{'anchor_id':'B','span':b['selector']['spans'][0]},
              'origin':'experiment_fixture','supersedes':None}
    db=RelationStore(tmp_path/'relations.sqlite')
    db.seed_experiment('fixture',relation,[b,a],sources)
    yield db,sources,a,b,relation
    db.close()

def test_reverse_relation_precise_target_and_no_citation(data):
    db,s,*_=data
    hit=db.lookup('reg',s,release_id='fixture',allow_experiment=True)['items'][0]
    assert hit['target']['unit_id']=='2' and len(hit['target']['selector']['spans'])==2
    assert not hit['content_read'] and not hit['citation_eligible']

def test_forward_relation_keeps_original_direction(data):
    db,s,*_=data
    hit=db.lookup('rule',s,release_id='fixture',allow_experiment=True,direction='outgoing')['items'][0]
    assert hit['from_anchor']=='B' and hit['to_anchor']=='A' and hit['target']['id']=='A'

def test_fixture_requires_explicit_nonproduction_permission(data):
    db,s,*_=data
    with pytest.raises(ValueError):db.lookup('reg',s,release_id='fixture')

@pytest.mark.parametrize('mutation',['scope','generation','store_hash','span','extent','block_hash'])
def test_stale_or_wrong_anchors_rejected(data,mutation):
    db,s,a,b,r=data;a=deepcopy(a)
    if mutation=='scope':s.scope=[]
    elif mutation=='generation':a['generation_id']='other'
    elif mutation=='store_hash':a['store_sha256']='c'*64
    elif mutation=='span':a['selector']['spans'][0]['text']='조작'
    elif mutation=='extent':a['unit_id']='2'
    else:a['selector']['spans'][0]['block_hash']='c'*64
    with pytest.raises((ValueError,ContractError)):verify_anchor(a,s)

def proposal(db,**kw):
    return db.propose(action='MISSING',from_anchor='A',reason='대상 미상, 검토 요청',producer_kind='llm',
        producer_id='synthetic-model',run_id='synthetic-run',idempotency_key='same',**kw)

def test_missing_target_proposal_idempotent_and_inactive(data):
    db,s,*_=data
    before=db.lookup('reg',s,release_id='fixture',allow_experiment=True)
    first=proposal(db,candidate={'target_locator':'시행규칙 미상'})
    assert first==proposal(db,candidate={'target_locator':'시행규칙 미상'})
    assert db.db.execute('SELECT count(*) FROM proposal').fetchone()[0]==1
    assert before==db.lookup('reg',s,release_id='fixture',allow_experiment=True)
    assert db.db.execute('SELECT count(*) FROM review_event').fetchone()[0]==0
    with pytest.raises(ValueError):proposal(db,candidate={'target_locator':'다른 대상'})

def test_wrong_link_report_cannot_remove_link(data):
    db,s,*_=data
    db.propose(action='REMOVE',from_anchor='A',reason='의심',producer_kind='llm',producer_id='mock',
        run_id='mock-run',idempotency_key='remove',base_revision='R1')
    assert len(db.lookup('reg',s,release_id='fixture',allow_experiment=True)['items'])==1

def test_correction_requires_existing_revision(data):
    db,s,*_=data
    with pytest.raises(ValueError):
        db.propose(action='CORRECT',from_anchor='A',reason='의심',producer_kind='llm',producer_id='mock',
            run_id='mock-run',idempotency_key='x')
    with pytest.raises(sqlite3.IntegrityError):
        db.propose(action='CORRECT',from_anchor='A',reason='의심',producer_kind='llm',producer_id='mock',
            run_id='mock-run',idempotency_key='x',base_revision='absent')

def test_model_cannot_submit_approval_field(data):
    db,*_=data
    with pytest.raises(ValueError):proposal(db,candidate={'approved':True})

def test_publication_membership_requires_exact_review(data):
    db,*_=data
    db.db.execute('INSERT INTO relation_release VALUES(?,?,?,?,?)',('published','g','a'*64,'published','x'))
    with pytest.raises(sqlite3.IntegrityError):
        db.db.execute('INSERT INTO release_member VALUES(?,?,NULL)',('published','R1'))

def test_unknown_release_is_not_silent_empty_result(data):
    db,s,*_=data
    with pytest.raises(ValueError):db.lookup('reg',s,release_id='absent',allow_experiment=True)

def test_span_only_target_not_silently_widened(data):
    db,s,a,b,r=data;a=deepcopy(a);a['selector']['kind']='span'
    with pytest.raises(ValueError,match='exact-span READ'):
        read_target({'target':a,'revision_id':'R1'},s)

def test_general_read_together_type_rejected(data,tmp_path):
    _,s,a,b,r=data;r=dict(r,relation_type='READ_TOGETHER')
    db=RelationStore(tmp_path/'other.sqlite')
    try:
        with pytest.raises(ValueError):db.seed_experiment('fixture',r,[a,b],s)
    finally:db.close()

def test_changed_relation_payload_rejected(data):
    db,s,*_=data
    db.db.execute("UPDATE relation_revision SET qualifiers_json='{}'")
    with pytest.raises(ValueError,match='integrity'):db.lookup('reg',s,release_id='fixture',allow_experiment=True)
