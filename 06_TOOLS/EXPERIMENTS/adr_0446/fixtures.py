"""Synthetic source adapter only. Same data/graph feed both arms; no gold access."""
import hashlib,json,sqlite3
from types import SimpleNamespace

def build(path):
    rows=json.loads(path.read_text());sources={s['id']:s for s in rows};documents={s['document_id']:s['document_name'] for s in rows}
    db=sqlite3.connect(':memory:');db.executescript('CREATE TABLE occurrence(term_id,source_id);CREATE TABLE reference(id,json);CREATE TABLE reference_end(source_id,reference_id);CREATE TABLE document(document_id,name);')
    db.executemany('insert into document values (?,?)',documents.items())
    terms={k:{'id':k,'label':label} for k,label in [('incentive','인센티브'),('performance','성과급'),('points','적립금')]}
    e={'id':'mock-edge-incentive-performance','source':'incentive','target':'performance','code':'mock-related'}
    edges={'incentive':[e],'performance':[e],'points':[]}
    db.executemany('insert into occurrence values (?,?)',[('performance','article:mock-staff'),('points','article:mock-customers')])
    units={(s['document_id'],str(s['unit_id'])):{'parent':None,'family':'kr_article','surface':s['heading'].split()[0],'title':s['heading'],'ordinal':int(s['unit_id'])} for s in rows}
    def validate(scope):
        if not scope or set(scope)-documents.keys():raise ValueError('empty/unknown allowed scope')
        return sorted(set(scope))
    tools=SimpleNamespace(terms=terms,edges=edges,db=db,sources=sources,validate_scope=validate)
    def starts(q,scope):
        span=lambda text:[{'text':text,'start':q.index(text),'end':q.index(text)+len(text)}]
        return {'documents':[{'id':d,'name':name,'question_spans':span(name)} for d,name in documents.items() if name in q], 'terms':[{'id':k,'question_spans':span(t['label'])} for k,t in terms.items() if t['label'] in q], 'structures':[{'id':'structure:'+d+':1','document_id':d,'kind':'LOCATOR','family':'kr_article','question_spans':span('제1조')} for d in scope if '제1조' in q]}
    matcher=SimpleNamespace(tools=tools,sources=sources,documents=documents,units=units,starts=starts,_unit_sources=lambda d,u:[s['id'] for s in rows if s['document_id']==d and str(s['unit_id'])==u])
    glossary=SimpleNamespace(connections=SimpleNamespace(_definitions=lambda source,node,end:[{'text':terms[node]['label']+'의 모의 사전 항목. 원문 기준은 별도 확인.','id':'definition:'+node}]))
    manifest={'generation_id':'synthetic-446-v1','store_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'data_status':'EXAMPLE','scope':{'document_version_ids':sorted(documents)}}
    return SimpleNamespace(db=db,manifest=manifest),matcher,glossary
