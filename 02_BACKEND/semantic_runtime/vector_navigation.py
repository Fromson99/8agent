"""Bridge vector coordinates into existing authorized READ actions and pagination."""
from .contracts import digest
from .initial_vector import mode,VectorUnavailable,VectorError

def discover(session,queries,terms,query_origin):
 from .legal_agent import law_candidates as lc,query_scope as qs
 retriever=getattr(session.matcher,'initial_vector',None)
 if retriever is None or mode()=='keyword' or getattr(session,'law_search_queries',None):return None
 # Keep explicit structure/subtree semantics; this first version vectorizes
 # only whole-document scopes, never broadens a selected chapter or paragraph.
 if qs.fulltext(session):return None
 question=session.context.request['question']
 try:result=retriever.search(question,qs.documents(session))
 except VectorUnavailable as exc:
  session.repo.event('INITIAL_VECTOR_DEGRADED',{'status':'KEYWORD_FALLBACK','reason':str(exc)})
  if mode()=='vector' and 'NOT_PUBLISHED' in str(exc):raise
  return None
 if not result['rows']:
  session.repo.event('INITIAL_VECTOR_EMPTY',{'publication_id':result['publication_id']});return None
 rows=[]
 for item in result['rows']:
  sid=item['SOURCE_ID'];source=session.tools.sources[sid]
  if source['document_id']!=item['DOC_ID'] or source['document_id'] not in qs.documents(session):raise VectorError('VECTOR_COORDINATE: current source mismatch')
  rows.append({'source_id':sid,'document_id':source['document_id'],'unit_id':str(source['unit_id']),'source_sha256':digest(source),'rank':len(rows)+1,'distance':float(item['DISTANCE'])})
 laws=[]
 for did in dict.fromkeys(r['document_id'] for r in rows):
  laws.append({'document_id':did,'article_count':sum(r['document_id']==did for r in rows),'unit_count':None})
 idx,_=lc.index(session)
 catalogue={'contract':lc.CONTRACT,'terms':terms,'queries':queries,'route_queries':queries,'query_origin':query_origin,'law_page':{'items':laws,'total':len(laws),'next_cursor':None},'query_fingerprint':digest([question,sorted(session.scope),result['publication_id'],qs.active(session)]),'index_sha256':idx.manifest['index_sha256'],'search_policy':'vector-initial-v1','vector_candidates':rows,'vector_publication':result['publication_id'],'vector_truncated':result['truncated']}
 session.repo.event('INITIAL_VECTOR_CANDIDATES',{'publication_id':result['publication_id'],'count':len(rows),'embedding_calls':result['embedding_calls'],'truncated':result['truncated']})
 return [],{'discovery_mode':'fulltext','law_navigation':catalogue,'unit_hits':[],'unit_index_sha256':idx.manifest['index_sha256'],'selected_for_read':[],'discovered':[],'routes':{},'queries':[],'structure_query':{'status':'NO_MATCH','pairs':[],'source_ids':[]},'parent_selections_preserved':True}

def attach(inv,data,offer):
 from .legal_agent import query_scope as qs
 catalogue=inv.p['catalogue']
 if inv.p.get('window')!='search' or catalogue.get('search_policy')!='vector-initial-v1':return
 rows=[]
 for item in catalogue['vector_candidates']:
  sid=item['source_id'];source=inv.s.tools.sources[sid]
  if source['document_id'] not in qs.documents(inv.s) or digest(source)!=item['source_sha256']:raise VectorError('VECTOR_COORDINATE: saved candidate source/scope changed')
  if any(r['source_id']==sid for r in inv.p['selected'].values()):continue
  target=offer('READ_ARTICLES',{'source_id':sid,'document_id':item['document_id']},source.get('heading','')+' 전체 원문 읽기')
  rows.append({'document_id':item['document_id'],'document_name':source['document_name'],'article':source.get('heading',''),'read_action':target,'retrieval_order':item['rank']})
 data['initial_vector_candidates']=rows
 data['initial_retrieval_status']={'mode':'vector','publication':catalogue['vector_publication'],'truncated':catalogue['vector_truncated'],'note':'검색 후보는 근거가 아닙니다. 원문과 필요한 참조를 읽어 확인합니다. 추가 대상은 기존 재검색/구조 조회로 찾을 수 있습니다.'}
