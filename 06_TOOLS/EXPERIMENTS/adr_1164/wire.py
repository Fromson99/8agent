from pathlib import Path
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_1164/integrated/snapshot'
def write(n,t):p=S/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t)
write('02_BACKEND/semantic_runtime/vector_navigation.py','''"""Bridge vector coordinates into existing authorized READ actions and pagination."""
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
 idx,_=lc.index(session)
 catalogue={'contract':lc.CONTRACT,'terms':terms,'queries':queries,'route_queries':queries,'query_origin':query_origin,'law_page':{'items':[],'total':0,'next_cursor':None},'query_fingerprint':digest([question,sorted(session.scope),result['publication_id'],qs.active(session)]),'index_sha256':idx.manifest['index_sha256'],'search_policy':'vector-initial-v1','vector_candidates':rows,'vector_publication':result['publication_id'],'vector_truncated':result['truncated']}
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
''')
p=S/'02_BACKEND/semantic_runtime/legal_agent/law_candidates.py';t=p.read_text();anchor="    page = idx.law_groups_page(db, terms, qs.search_sources(s), limit=policy(s)['law_page_size'], **qs.fulltext(s))";assert t.count(anchor)==1;t=t.replace(anchor,"    from ..vector_navigation import discover as vector_discover\n    vector_result=vector_discover(s,queries,terms,query_origin)\n    if vector_result is not None:return vector_result\n"+anchor);p.write_text(t)
p=S/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';t=p.read_text();anchor="        data['presentation_id'] = lc.token(self.s, 'P', digest(data))";assert t.count(anchor)==1;t=t.replace(anchor,"        from ..vector_navigation import attach as vector_attach\n        vector_attach(self,data,offer)\n"+anchor);p.write_text(t)
p=S/'02_BACKEND/semantic_runtime/legal_agent/decision_projection.py';t=p.read_text().replace("    walk(data.get('laws', []))","    walk(data.get('initial_vector_candidates', []))\n    walk(data.get('laws', []))");p.write_text(t)
p=S/'02_BACKEND/semantic_runtime/oracle_query_resources.py';t=p.read_text().replace('        yield index,tools,glossary,matcher',"        from .initial_vector import Retriever,mode\n        if mode()!='keyword':matcher.initial_vector=Retriever(tools.request)\n        yield index,tools,glossary,matcher");p.write_text(t)
p=S/'02_BACKEND/semantic_runtime/oracle_query_service.py';t=p.read_text().replace("names=('DP',","names=('GENOS_RAG_INITIAL_SEARCH','GENOS_EMBED_URL','GENOS_BASE_URL','GENOS_EMBED_SERVING_ID','GENOS_EMBED_KEY','DP',");p.write_text(t)
# Read-only source SQL mapping bridge. The validated source publication retains its
# logical keys; Dataiku's physical SIDDS names never leak into source identities.
write('02_BACKEND/semantic_runtime/oracle_silver_reads.py','''"""Map legacy read table references onto the approved SIDDS physical projection."""
from .physical_mapping import CONTRACT_COLUMNS
LEGACY={'SIDDA.LEGAL_SRC_DOCUMENT_A':'document','SIDDA.LEGAL_SRC_SOURCE_UNIT_A':'source_unit','SIDDA.LEGAL_SRC_BLOCK_PAYLOAD_A':'block_payload','SIDDA.LEGAL_RAG_QUERY_ROW_A':'query_row','SIDDA.LEGAL_RAG_QUERY_RELEASE_A':'query_release','SIDDA.LEGAL_RAG_QUERY_ACTIVE_A':'query_active','SIDDA.LEGAL_RAG_SOURCE_RELEASE_A':'source_release'}
def rewrite(text,mapping):
 if mapping is None:return text
 import sqlglot
 from sqlglot import exp
 tree=sqlglot.parse_one(text,read='oracle')
 for t in list(tree.find_all(exp.Table)):
  name=((t.db+'.') if t.db else '')+t.name;key=LEGACY.get(name.upper())
  if key is None:continue
  n=mapping.names(key);projection='SELECT '+n.select(*CONTRACT_COLUMNS[key].split())+' FROM '+n.table
  alias=t.alias or t.name
  sub=sqlglot.parse_one(projection,read='oracle').subquery(alias)
  t.replace(sub)
 return tree.sql(dialect='oracle')
''')
p=S/'02_BACKEND/semantic_runtime/oracle_query.py';t=p.read_text();anchor='    def event(self, status, **extra):';t=t.replace(anchor,"    def query(self,statement,binds=(),*,limit=100):\n        from .oracle_silver_reads import rewrite\n        return super().query(rewrite(statement,getattr(self.client,'schema_map',None)),binds,limit=limit)\n\n"+anchor);p.write_text(t)
p=S/'02_BACKEND/semantic_runtime/oracle_dp.py';t=p.read_text().replace('    try:return ORDSClient(**options)',"    try:\n        client=ORDSClient(**options)\n        if os.environ.get('GENOS_RAG_INITIAL_SEARCH','').strip().lower()=='vector':\n            from .physical_mapping import SchemaMap\n            client.schema_map=SchemaMap.load(Path(__file__).resolve().parents[2]/'00_SYSTEM/ORACLE/physical_mapping.yaml')\n        return client");p.write_text(t)
