import copy,json,hashlib,time
from types import SimpleNamespace as N
import pytest
from semantic_runtime.initial_vector import *
from semantic_runtime.vector_publish import segments

def cfg():return {'schema_version':'legal-vector-profile-v1','model':'fixture','revision':'weights-sha-test','dimensions':4,'endpoint_sha256':hashlib.sha256(b'https://example.invalid/api/gateway/rep/serving/3').hexdigest(),'chunk_chars':800,'overlap_chars':100,'normalization':'l2','metric':'COSINE'}
def env():return {'GENOS_BASE_URL':'https://example.invalid','GENOS_EMBED_SERVING_ID':'3','GENOS_EMBED_KEY':'test-key'}
def response(rows,status=200):return N(status_code=status,json=lambda:{'data':rows})
@pytest.mark.parametrize('bad',[[0,0,0,0],[1,2,3],[1,2,3,float('nan')],[1,2,3,float('inf')],[True,2,3,4],None])
def test_numeric(bad):
 with pytest.raises(VectorError):normalize(bad,4)
@pytest.mark.parametrize('rows',[[{'index':0,'embedding':[1,0,0,0]}]*2,[{'index':1,'embedding':[1,0,0,0]},{'index':2,'embedding':[1,0,0,0]}],[],[{'index':'0','embedding':[1,0,0,0]}]])
def test_indices(rows):
 with pytest.raises(VectorError):Encoder(cfg(),env=env(),post=lambda *a,**kw:response(rows)).encode(['a','b'])
def test_order_one_http_and_no_model_probe():
 calls=[]
 def post(url,**kw):calls.append((url,kw));return response([{'index':1,'embedding':[0,2,0,0]},{'index':0,'embedding':[4,0,0,0]}])
 enc=Encoder(cfg(),env=env(),post=post);assert enc.encode(['a','b'])==[[1,0,0,0],[0,1,0,0]];assert enc.calls==1 and len(calls)==1;assert calls[0][0].endswith('/3/embeddings');assert calls[0][1]['allow_redirects'] is False
@pytest.mark.parametrize('status',[401,403,404,429,500,503])
def test_http_no_retry(status):
 enc=Encoder(cfg(),env=env(),post=lambda *a,**k:response([],status))
 with pytest.raises(VectorError):enc.encode(['a'])
 assert enc.calls==1
@pytest.mark.parametrize('key,value',[('dimensions',0),('revision',''),('normalization','none'),('metric','L2'),('endpoint_sha256','bad')])
def test_profile_mismatch(key,value):
 p=cfg();p[key]=value
 with pytest.raises(VectorError):profile(p)
def test_endpoint_mismatch():
 e=env();e['GENOS_EMBED_SERVING_ID']='4'
 with pytest.raises(VectorError,match='binding|differs'):Encoder(cfg(),env=e)
def test_no_secret_fallback():
 e=env();e.pop('GENOS_EMBED_KEY');e['GENOS_LLM_KEY']='not-an-embed-credential'
 with pytest.raises(VectorError):Encoder(cfg(),env=e)
def test_chunk_coverage_and_partition():
 source={'id':'sid','document_id':'d','unit_id':'2','document_name':'법','heading':'부칙 제2조','blocks':[{'block_id':'1'}]}
 body='가'*1901
 request=N(snapshot=N(manifest={'navigation':{'path':'navigation'}}),release_id='a'*64,sources=N(allowed={'d'},sources=lambda d,ids:[{'block_id':'1','text':body}]),records=N(page=lambda *a,**k:{'rows':[{'json':json.dumps(source)}],'next':None}))
 result=list(segments(request));assert len(result)==3;assert result[-1]['meta']['end']==1901;assert all('부칙 제2조' in x['text'] for x in result);assert set().union(*(set(range(x['meta']['start'],x['meta']['end'])) for x in result))==set(range(len(body)))
def test_query_sql_scope_before_top_and_grouping():
 class SQL:
  def query(self,q,b,limit):self.q=q;return [{'DOC_ID':'d','SOURCE_ID':'sid','DISTANCE':0.1}]
 sql=SQL();repo=Repository(sql);repo.read=lambda p:{'STATUS':'READY','PROFILE_JSON':cfg()};assert repo.search('a'*64,[1,0,0,0],{'d'})[0]['SOURCE_ID']=='sid';assert sql.q.index('WHERE')<sql.q.index('GROUP BY')<sql.q.index('FETCH FIRST');assert "DOC_ID IN ('d')" in sql.q
 with pytest.raises(VectorError):repo.search('a'*64,[1,0,0,0],{'other'})
def test_paging_reuses_embedding_and_release_pin():
 request=N(sources=N(allowed={'d'}),release_id='a'*64,sql=N(deadline=time.monotonic()+60))
 calls=[]
 class Enc:
  def __init__(self,*a,**k):self.calls=0
  def encode(self,t):calls.append(t);self.calls+=1;return [[1,0,0,0]]
 r=Retriever(request,encoder_factory=Enc);r.repo=N(active=lambda q:{'PUB_ID':'b'*64,'REVISION':1},read=lambda p:{'STATUS':'READY','QUERY_ID':'a'*64,'PROFILE_JSON':cfg()},search=lambda *a:[{'DOC_ID':'d','SOURCE_ID':'sid','DISTANCE':0.1}])
 assert r.search('question',{'d'})==r.search('question',{'d'});assert len(calls)==1
 with pytest.raises(VectorError):r.search('q',{'forbidden'})
def test_vector_rows_precede_keywords_and_page():
 from semantic_runtime.legal_agent.decision_projection import read_candidate_rows
 from semantic_runtime.legal_agent.read_candidate_pages import page_view
 rows=[{'document_id':'d','read_action':'V'+str(i),'article':'조'+str(i)} for i in range(25)]
 candidates={x['read_action']:{'identity':{'document_id':'d'},'label':'읽기'} for x in rows};candidates['K']={'identity':{'document_id':'d'},'label':'keyword'}
 data={'initial_vector_candidates':rows,'laws':[{'document_id':'d','article_matches':[{'read_action':'K'}]}]}
 actual=read_candidate_rows(data,candidates);assert [r['target'] for r in actual[:20]]==['V'+str(i) for i in range(20)]
 schema={'anyOf':[{'properties':{'choice':{'const':'READ'},'selections':{'items':{'properties':{'target':{}}}}}}]}
 page,_=page_view({'read_candidates':actual},schema,1,20);assert page['read_candidates'][0]['target']=='V20'
def test_silver_sql_has_no_legacy_source_access():
 from semantic_runtime.physical_mapping import SchemaMap
 from semantic_runtime.oracle_silver_reads import rewrite
 from pathlib import Path
 import os
 root=Path(os.environ['VECTOR_CODE_ROOT']);m=SchemaMap.load(root/'00_SYSTEM/ORACLE/physical_mapping.yaml')
 text=rewrite("SELECT r.VALUE_JSON FROM SIDDA.LEGAL_RAG_QUERY_ROW_A r WHERE r.DOCUMENT_ID=:d",m)
 assert 'SIDDS.LGL_SRCH_ROW_S' in text and 'SIDDA.LEGAL_RAG_QUERY_ROW_A' not in text and ':d' in text
