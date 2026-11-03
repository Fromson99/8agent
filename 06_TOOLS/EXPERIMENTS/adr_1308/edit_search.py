from pathlib import Path
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized/snapshot'
B=S/'02_BACKEND/semantic_runtime'
p=B/'unit_fulltext.py';s=p.read_text();pos=s.index('\n\nclass ArticleProjection:')
helper='''

def search_page(index,db,terms,allowed,*,bounds=None,offset=0,limit=16):
    """Deduplicate navigation identities before reading this page's bodies.

    Preserve the old dict semantics: first occurrence determines order, last
    matching occurrence determines the hit shown for a shared navigation node.
    """
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
        raise ValueError('invalid fulltext navigation page')
    metadata=index.search_metadata(db,terms,allowed)
    selected={}
    for row in metadata:
        if bounds and not any(bounds[0]<=int(b)<bounds[1] for b in row['block_ids']):continue
        uid=row['unit_id']
        identity=(row['document_id'],str(uid) if uid is not None else None,row['source_id'] if uid is None else None)
        selected[identity]=row
    total=len(selected);page=list(selected.values())[offset:offset+limit]
    bodies=index.search_bodies(db,[r['key'] for r in page])
    items=[]
    for row in page:
        body=bodies[row['key']]
        if any(body[k]!=row[k] for k in ('key','document_id','source_id','unit_id','block_ids')):
            raise ValueError('fulltext metadata differs from selected body')
        items.append({**body,'score':row['score'],'query_terms':list(terms)})
    index.check_unchanged()
    return {'items':items,'total':total,'next_offset':offset+len(items) if offset+len(items)<total else None}
'''
s=s[:pos]+helper+s[pos:]
pos=s.index('    def rank_page(')
methods='''    def search_metadata(self,db,terms,allowed):
        self.check_unchanged()
        if allowed is not None and set(allowed)-self.source_ids:raise ValueError('unit FTS does not cover requested article scope')
        if not terms or allowed is not None and not allowed:return []
        where='unit_fts MATCH ?';params=[expression(terms)]
        if allowed is not None:
            where+=' AND u.source_id IN (SELECT value FROM json_each(?))';params.append(json.dumps(sorted(allowed)))
        rows=db.execute("SELECT u.key,u.document_id,u.source_id,json_extract(u.json,'$.unit_id'),json_extract(u.json,'$.block_ids'),f.rank FROM unit_fts f JOIN unit u ON u.key=f.key WHERE "+where+' ORDER BY f.rank,f.key',params)
        result=[];size=0
        for key,did,sid,uid,blocks,score in rows:
            row={'key':key,'document_id':did,'source_id':sid,'unit_id':uid,'block_ids':json.loads(blocks),'score':score}
            size+=len(json.dumps(row,ensure_ascii=False).encode())
            if size>64*1024*1024:raise ValueError('fulltext navigation metadata budget exceeded')
            result.append(row)
        self.check_unchanged()
        return result

    def search_bodies(self,db,keys):
        if not keys:return {}
        rows=db.execute('SELECT key,json FROM unit WHERE key IN (SELECT value FROM json_each(?))',(json.dumps(keys),))
        bodies={key:json.loads(raw) for key,raw in rows}
        if set(bodies)!=set(keys):raise ValueError('unit FTS selected body missing')
        return bodies

    def search_page(self,db,terms,allowed=None,**kwargs):
        return search_page(self,db,terms,allowed,**kwargs)

'''
s=s[:pos]+methods+s[pos:];p.write_text(s)
p=B/'oracle_query_fulltext.py';s=p.read_text();pos=s.index('    def rank_page(')
methods='''    def search_metadata(self,db,terms,allowed):
        from .oracle_query_cache import for_request,key
        from .oracle_query_db import Connection
        self.check_unchanged()
        scope=sorted(allowed.document_ids) if hasattr(allowed,'document_ids') else None if allowed is None else sorted(set(allowed))
        cache=for_request(self.request);cache_key=key('fts-navigation',terms=list(terms),scope=scope)
        found,result=cache.get(cache_key)
        if found:return result
        result=[];cursor=None;size=0
        with Connection(self.request,self.asset) as relation:
            relation.set_progress_handler(lambda:self.check_unchanged(),1)
            while True:
                page=self._page(terms,allowed,'rank_keys',cursor=cursor,limit=100)
                keys=[r['key'] for r in page['items']]
                rows=relation.execute("SELECT key,json_extract(json,'$.unit_id') AS unit_id,json_extract(json,'$.block_ids') AS block_ids FROM unit WHERE key IN (SELECT value FROM json_each(?))",(json.dumps(keys),)) if keys else []
                metadata={r[0]:{'unit_id':r[1],'block_ids':json.loads(r[2])} for r in rows}
                if set(metadata)!=set(keys):raise DPError('QUERY_FTS_BODY: navigation metadata missing')
                for row in page['items']:
                    value={**row,**metadata[row['key']]}
                    size+=len(json_body(value).encode())
                    if size>64*1024*1024:raise DPError('QUERY_FTS_RESULT_BUDGET: navigation metadata exceeds memory budget')
                    result.append(value)
                cursor=page['next_cursor']
                if cursor is None:break
        self.check_unchanged();cache.put(cache_key,result)
        return result

    def search_bodies(self,db,keys):
        values=self.records.page(self.kinds['unit'],lookup_ids=keys,limit=len(keys))['rows'] if keys else []
        bodies={v['key']:json.loads(v['json']) for v in values}
        if set(bodies)!=set(keys):raise DPError('QUERY_FTS_BODY: selected hit body set differs')
        return bodies

    def search_page(self,db,terms,allowed=None,**kwargs):
        from .unit_fulltext import search_page
        return search_page(self,db,terms,allowed,**kwargs)

'''
s=s[:pos]+methods+s[pos:];p.write_text(s)
p=B/'legal_agent/exploration_tools.py';s=p.read_text()
start=s.index("            if hasattr(self.matcher.fulltext, 'rank_units'):")
end=s.index("            ids = self.matcher.fulltext.rank",start)
old=s[start:end]
# The existing legacy fallback remains for older non-unit indexes.
new='''            if hasattr(self.matcher.fulltext,'search_page'):
                sources=self.matcher.sources
                allowed=(sources.ids_for_documents(docs) if hasattr(sources,'ids_for_documents') else set(self.sources_in(args['target'])))
                result=self.matcher.fulltext.search_page(self.matcher.fulltext_db,terms,allowed,
                    bounds=bounds,offset=offset,limit=self.profile['page_size'])
                for hit in result['items']:
                    card=self.node_card(hit['document_id'],hit['unit_id'],
                        **({'source_id':hit['source_id']} if hit['unit_id'] is None else {}),route=route)
                    card.update(fulltext_hit={'unit_id':hit['unit_id'],'block_ids':hit['block_ids'],
                        'source_id':hit['source_id'],'score':hit['score'],'match_extent':'own_blocks'},
                        read_action={'tool':'read','args':{'target':card['target'],'extent':'exact','cursor':None},'reason':'검색된 최소 구조 단위 원문 확인'})
                    items.append(card)
                return items,result['next_offset'],[],{'search_receipt':{'mode':mode,'query':query,'query_terms':terms,
                    'searched_target':args['target'],'document_ids':docs,'bounds':bounds,
                    'total_status':'exact','total':result['total'],'granularity':'stored-own-block-owner',
                    'tokenizer':self.matcher.fulltext.manifest['tokenizer'],'ranking':self.matcher.fulltext.manifest['ranking']}}
'''
s=s[:start]+new+old+s[end:]
p.write_text(s)
print('exact metadata-first navigation paging written')
