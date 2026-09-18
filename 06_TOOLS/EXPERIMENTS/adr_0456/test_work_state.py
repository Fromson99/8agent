from pathlib import Path
import sys,os,importlib,json
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from runtime import *

@pytest.fixture
def env(tmp_path):
    mod,old,multi,mods,root,b=load(bool(os.getenv('ADR456_FROZEN')));store,m,g=build(multi)
    yield mod,m,store,g,mods,root,tmp_path
    store.db.close()
def session(env,scope=None,bindings=None):
    mod,m,store,g,*_=env;bound=mod.BoundMatcher(m,bindings or []);bound.navigation_store=store
    return mod.WorkSession(bound,bound.tools,g,'성과급과 휴직이 겹치면 지급 기준, 기준일과 예외 승인 요건은?',scope or list(m.documents),{'max_calls':13,'wall_seconds':180,'max_actions':56,'active_chars':18000,'context_chars':60000})
def set_requirements(s):s.requirements=s.issues={'Q1':'지급 기준','Q2':'기준일','Q3':'예외 승인 요건'}
def read_source(s,sid):
    s.context();h=s.source_card(sid)['read_handle'];s.offered_handles.add(h);s.read_batch([h])
def review(s,status='adopted',requirements=None):
    out={'reviews':[{'segment_id':k,'status':status,'requirement_ids':requirements or ['Q1'],'quote_ref':s.read_segments[k]['quote_refs'][0]['id'],'claim':'원문 확인'} for k in s.pending_review()]};s.apply_reviews(out)

def test_candidates_survive_unrelated_tool_results_and_keep_handles(env):
    s=session(env);set_requirements(s);before=s.context()['candidates']['items'];s.execute_work({'tool':'GRAPH','args':{'term_id':'leave','hops':1},'reason':'check'})
    after=s.context()['candidates']['items'];assert {x['read_handle'] for x in before}=={x['read_handle'] for x in after}
    assert {x['id'] for x in after}==set(s.initial_pool_ids) and s.context()['next_actions']

def test_read_and_review_are_different_states(env):
    s=session(env);set_requirements(s);read_source(s,'article:pay-base');assert s.pending_review() and 'article:pay-base' in s.waiting()
    review(s);assert not s.pending_review() and 'article:pay-base' not in s.waiting()

def test_required_reference_stays_visible_until_reviewed(env):
    s=session(env);set_requirements(s);read_source(s,'article:leave-exception');review(s,requirements=['Q3']);d=s.context()
    ref=next(x for x in d['reference_tasks'] if x['from_source_id']=='article:leave-exception')
    assert ref['origin_adopted'] and 'article:approval-rule' in ref['pending_target_ids']
    assert next(x for x in d['candidates']['items'] if x['id']=='article:approval-rule')['reference_priority']
    read_source(s,'article:approval-rule');review(s,requirements=['Q3']);assert not s.reference_rows()[0]['pending_target_ids']

def test_type_identity_no_document_term_collision(env):
    s=session(env);d=s.context();entities=s.work.entities
    assert entities['document:leave']['type']=='document' and entities['term:leave']['type']=='term'
    assert s.wire({'document_id':'leave','term_id':'leave'})=={'document_id':'leave','term_id':'leave'}

def test_alias_applies_only_to_validated_term_and_preserves_receipt(env):
    s=session(env,bindings=[{'expression':'상여','target':{'type':'term','identity':'performance'}}]);r=s.legal_search('휴직 상여',mode='tokens')
    assert r['query_transform']['executed']=='휴직 성과급' and r['total']==1
    assert s.expand_query('상여금 지급')[0]=='상여금 지급'
    assert s.expand_query('상여와 휴직')[0]=='성과급와 휴직'

def test_scoped_search_and_batch_cannot_escape(env):
    s=session(env,scope=['pay']);set_requirements(s)
    with pytest.raises(ValueError):s.legal_search('휴직',document_id='leave')
    assert s.legal_search('휴직')['total']==0
    s.context();h=s.source_card('article:pay-base')['read_handle'];s.offered_handles.add(h)
    with pytest.raises(ValueError):s.read_batch([h,'RHforged'])
    assert not s.read_segments

def test_review_validation_is_atomic(env):
    s=session(env);set_requirements(s);read_source(s,'article:pay-base');read_source(s,'article:pay-date')
    out={'reviews':[{'segment_id':k,'status':'adopted','requirement_ids':['Q1'],'quote_ref':s.read_segments[k]['quote_refs'][0]['id'],'claim':'근거'} for k in s.pending_review()]};out['reviews'][-1]['quote_ref']='forged'
    with pytest.raises(ValueError):s.apply_reviews(out)
    assert not s.judgments

def test_common_state_pagination_retains_exact_events(env):
    mod,*_=env;W=importlib.import_module(mod.__package__+'.navigation_work_state').WorkState;w=W('q',{'generation_id':'g','store_sha256':'h'},['d'])
    for i in range(27):w.put('term',str(i),{'label':str(i)})
    pages=[w.entities_page(offset=n) for n in [0,12,24]];assert sum(len(p['items']) for p in pages)==27 and pages[-1]['next_offset'] is None
    ident=w.event('LOOKUP',{'q':'x'},{'items':[{'id':i} for i in range(25)],'field':'title'})
    assert w.result_page(ident,24)['items']==[{'id':24}] and len(w.snapshot()['events'][0]['result']['items'])==25

def test_synthesis_rejects_unread_and_unrepresented_sources(env):
    s=session(env);set_requirements(s);read_source(s,'article:pay-base');review(s)
    draft={'findings':[{'text':'근거','source_ids':['article:approval-rule'],'requirement_ids':['Q1']}],'coverage':[{'requirement_id':q,'status':'partial','source_ids':[],'missing':'미확인'} for q in s.requirements]}
    with pytest.raises(ValueError,match='unselected'):s.validate_draft(draft)
    draft['findings']=[];draft['coverage'][0].update(status='complete',source_ids=['article:pay-base'],missing='')
    with pytest.raises(ValueError,match='represented'):s.validate_draft(draft)

def test_pending_stop_returns_to_work_once_then_partial(env):
    s=session(env);set_requirements(s);s.execute_work({'tool':'STOP','args':{'reason':'미확인'},'reason':'stop'})
    assert s.stop is None and s.recoveries==1
    s.execute_work({'tool':'STOP','args':{'reason':'여전히 확인 불가'},'reason':'stop'});assert s.stop['status']=='incomplete'

class ScriptedProvider:
    def __init__(self):self.requests=[]
    def call(self,role,system,d,schema):
        self.requests.append((role,d));sids=['article:pay-base','article:pay-date','article:leave-exception','article:approval-rule'];req={'article:pay-base':'Q1','article:pay-date':'Q2','article:leave-exception':'Q3','article:approval-rule':'Q3'}
        if role=='structured_navigation' and 'work_state' not in d:
            out={'action':{'tool':'INTERPRET_QUERY','args':{'intent':'content','scope':'current','bindings':[],'title_query':'','clarification':''},'reason':'content'}}
        elif role=='navigation_requirements':out={'requirements':[{'id':q,'text':t,'question_span':t} for q,t in [('Q1','지급 기준'),('Q2','기준일'),('Q3','예외 승인 요건')]]}
        elif role=='structured_navigation':
            pending=[c for c in d['candidates']['items'] if c['review_status']=='unreviewed'];chosen=[c['read_handle'] for c in pending if c['id'] in sids][:3]
            out={'action':{'tool':'READ_BATCH','args':{'read_handles':chosen},'reason':'read'}} if chosen else {'action':{'tool':'DISMISS','args':{'read_handles':[c['read_handle'] for c in pending],'reason':'대상/문서 목적 다름'},'reason':'exclude'}}
        elif role=='navigation_review':out={'reviews':[{'segment_id':x['id'],'status':'adopted','requirement_ids':[req[x['source_id']]],'quote_ref':x['quote_refs'][0]['id'],'claim':x['text']} for x in d['pending_review']]}
        elif role=='navigation_synthesis':out={'findings':[{'text':'확인한 복수 원문의 결론','source_ids':sids,'requirement_ids':['Q1','Q2','Q3']}],'coverage':[{'requirement_id':q,'status':'complete','source_ids':[s for s in sids if req[s]==q],'missing':''} for q in ['Q1','Q2','Q3']]}
        elif role=='navigation_verify':out={'requirements':[{'requirement_id':q,'status':'verified','missing':''} for q in ['Q1','Q2','Q3']],'findings':[{'index':0,'supported':True,'reason':'원문으로 확인'}],'search_queries':[]}
        else:raise AssertionError(role)
        return out,{'kind':'scripted','role':role}
    def record_local(self,v):return {'kind':'local'}

def test_full_pipeline_handoff_and_multi_source_synthesis(env):
    mod,m,store,g,mods,root,tmp=env;p=mods['pipeline'].Pipeline(root,store,ScriptedProvider());c=mod.Conversation(p,mod.MappedAgent(p,g,None,m,ledger=tmp/'ledger.sqlite',actor='test'),list(m.documents))
    out=c.run('성과급과 휴직이 겹치면 지급 기준, 기준일과 예외 승인 요건은?');s=out['retrieval']['term_agent']
    assert s['failure'] is None and s['status']=='FINISH' and len(s['selected_ids'])==4
    assert out['selection']['term_agent']['work_state']==out['assembly']['term_agent']['work_state']==s['work_state']
    assert len(out['answer']['claims'][0]['source_ids'])==4 and s['calls']<=14
    assert any(r[0]=='navigation_synthesis' for r in p.provider.requests) and any(r[0]=='navigation_verify' for r in p.provider.requests)
