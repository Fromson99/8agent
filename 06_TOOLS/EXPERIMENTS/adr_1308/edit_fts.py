from pathlib import Path
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized/snapshot'
B=S/'02_BACKEND/semantic_runtime'
def replace(path,old,new):
 s=path.read_text();assert old in s,(path,old[:70]);path.write_text(s.replace(old,new,1))
p=B/'oracle_query_fulltext.py'
replace(p,'import sqlite3\n','import sqlite3\nimport math\nfrom functools import lru_cache\n')
replace(p,'    phrases=[]\n','    return [tuple(p) for p in _phrases(tuple(terms))]\n\n\n@lru_cache(maxsize=16)\ndef _phrases(terms):\n    phrases=[]\n')
replace(p,'    return phrases\n','    return tuple(phrases)\n')
replace(p,"        counts=[]\n",'''        # Published tf is the exact FTS5 occurrence count. Unigrams do not
        # need to expand occurrence positions; phrases still use adjacency.
        postings=(f"SELECT p.OWNER_ID AS k,p.LOOKUP_ID AS token,JSON_VALUE(p.VALUE_JSON,'$.tf' RETURNING NUMBER ERROR ON ERROR) AS tf FROM {ROW} p "
            "WHERE p.RELEASE_ID=:q_release AND p.KIND=:q_posting AND p.LOOKUP_ID IN ("+
            ','.join(':'+token_names[t] for t in tokens)+')')
        counts=[]
''')
replace(p,"        for i,phrase in enumerate(phrases):\n            joins=",'''        for i,phrase in enumerate(phrases):
            if len(phrase)==1:
                counts.append(f'SELECT {i} AS phrase,k,SUM(tf) AS tf FROM postings WHERE token=:{token_names[phrase[0]]} GROUP BY k')
                continue
            joins=''')
replace(p,'where.append("l.sid IN ', 'where.append("r.OWNER_ID IN ')
replace(p,"cte=('WITH positions AS ('+positions+'), frequencies AS ('", "cte=('WITH postings AS ('+postings+'), '+('positions AS ('+positions+'), ' if any(len(p)>1 for p in phrases) else '')+'frequencies AS ('")
anchor='    def _page(self,terms,allowed,kind,identity=None,*,cursor=None,limit=12,unit_keys=None):'
methods='''    def _projection(self,terms,allowed,unit_keys=None):
        """One bounded metadata result shared by law/article/hit pages."""
        from .oracle_query_cache import for_request, key
        self.check_unchanged()
        scope=(sorted(allowed.document_ids) if hasattr(allowed,'document_ids') else None if allowed is None else sorted(set(allowed)))
        cache=for_request(self.request)
        cache_key=key('fts-matches',terms=list(terms),scope=scope,
                      units=None if unit_keys is None else sorted(set(unit_keys)))
        found,value=cache.get(cache_key)
        if found:return value
        cte,binds=self._matches(terms,allowed,unit_keys)
        if cte is None:
            cache.put(cache_key,[]);return []
        # Never mirror the index. At most 2049 compact keys are considered;
        # overflow reuses the exact paged SQL below without truncating totals.
        statement=("SELECT COUNT(*) AS N,CASE WHEN COUNT(*)<=2048 THEN "
            "JSON_ARRAYAGG(JSON_ARRAY(k,did,sid,score NULL ON NULL RETURNING CLOB) RETURNING CLOB) END AS ITEMS FROM ("+
            cte+'SELECT k,did,sid,score FROM matches FETCH FIRST 2049 ROWS ONLY)')
        rows=self.sql.query(statement,binds,limit=1)
        if len(rows)!=1 or type(rows[0]['N']) is not int or not 0<=rows[0]['N']<=2049:
            raise DPError('QUERY_FTS_PROJECTION: invalid bounded match count')
        n=rows[0]['N']
        if n>2048:
            cache.put(cache_key,None);return None
        values=json.loads(rows[0]['ITEMS']) if n else []
        if not isinstance(values,list) or len(values)!=n:
            raise DPError('QUERY_FTS_PROJECTION: incomplete match metadata')
        seen=set()
        documents=self.request.sources.allowed if not hasattr(allowed,'document_ids') else allowed.document_ids
        for row in values:
            if (not isinstance(row,list) or len(row)!=4 or any(not isinstance(x,str) or not x for x in row[:3])
                    or row[1] not in documents or row[0] in seen
                    or not isinstance(row[3],(int,float)) or not math.isfinite(row[3])
                    or (allowed is not None and not hasattr(allowed,'document_ids') and row[2] not in allowed)
                    or (unit_keys is not None and row[0] not in unit_keys)):
                raise DPError('QUERY_FTS_PROJECTION: invalid identity, scope or score')
            seen.add(row[0])
        values.sort(key=lambda r:(r[3],r[0]))
        self.check_unchanged();cache.put(cache_key,values)
        return values

    def _project_page(self,projection,terms,kind,identity,binding,offset,limit):
        if kind in ('laws','articles'):
            groups={}
            for k,did,sid,score in projection:
                if kind=='articles' and did!=identity:continue
                ident=did if kind=='laws' else sid
                group=groups.setdefault(ident,{'score':score,'sources':set(),'units':0})
                group['score']=min(score,group['score']);group['sources'].add(sid);group['units']+=1
            ordered=sorted(groups,key=lambda v:(groups[v]['score'],v));total=len(ordered)
            items=[({'document_id':i,'article_count':len(groups[i]['sources']),'unit_count':groups[i]['units']}
                    if kind=='laws' else {'source_id':i,'unit_count':groups[i]['units']}) for i in ordered[offset:offset+limit]]
        else:
            selected=[r for r in projection if identity is None or r[2]==identity]
            total=len(selected);selected=selected[offset:offset+limit]
            if kind=='rank_keys':
                items=[{'key':k,'document_id':d,'source_id':s,'score':score} for k,d,s,score in selected]
            else:
                keys=[r[0] for r in selected]
                values=self.records.page(self.kinds['unit'],lookup_ids=keys,limit=len(keys))['rows'] if keys else []
                bodies={v['key']:json.loads(v['json']) for v in values}
                if set(bodies)!=set(keys):raise DPError('QUERY_FTS_BODY: selected hit body set differs')
                items=[]
                for k,did,sid,score in selected:
                    body=bodies[k]
                    if body['key']!=k or body['document_id']!=did or body['source_id']!=sid:
                        raise DPError('QUERY_FTS_BODY: hit identity differs from projection')
                    items.append({**body,'query_terms':list(terms),**({'score':score} if kind=='rank' else {})})
        if offset and offset>=total:raise DPError('QUERY_CURSOR: page offset outside completed query result')
        return {'items':items,'total':total,'next_cursor':{'binding':binding,'offset':offset+len(items)} if offset+len(items)<total else None}

    def rank_page(self,db,terms,allowed=None,*,cursor=None,limit=16,unit_keys=None):
        return self._page(terms,allowed,'rank',cursor=cursor,limit=limit,unit_keys=unit_keys)

'''
replace(p,anchor,methods+anchor)
replace(p,'        cte,binds=self._matches(terms,allowed,unit_keys)\n        if cte is None:\n            return', '''        projection=self._projection(terms,allowed,unit_keys)
        if projection is not None:
            return self._project_page(projection,terms,kind,identity,binding,offset,limit)
        cte,binds=self._matches(terms,allowed,unit_keys)
        if cte is None:
            return''')
replace(p,"        elif kind in ('hits','rank'):\n            selection='SELECT k,score FROM matches'+predicates", "        elif kind in ('hits','rank','rank_keys'):\n            selection=('SELECT k,did,sid,score FROM matches' if kind=='rank_keys' else 'SELECT k,score FROM matches')+predicates")
replace(p,"        else:\n            keys=[r['K'] for r in rows]", "        elif kind=='rank_keys':\n            items=[{'key':r['K'],'document_id':r['DID'],'source_id':r['SID'],'score':r['SCORE']} for r in rows]\n        else:\n            keys=[r['K'] for r in rows]")
replace(p,"        roots=list(dict.fromkeys(row['source_id'] for row in self.rank_units(db,terms,allowed)))\n        return roots if limit is None else roots[:limit]",'''        roots=[];seen=set();cursor=None
        while True:
            page=self._page(terms,allowed,'rank_keys',cursor=cursor,limit=100)
            for row in page['items']:
                sid=row['source_id']
                if sid not in seen:seen.add(sid);roots.append(sid)
                if limit is not None and len(roots)>=limit:return roots
            cursor=page['next_cursor']
            if cursor is None:return roots''')

p=B/'unit_fulltext.py'
replace(p,"        roots=list(dict.fromkeys(h['source_id'] for h in self.rank_units(db,terms,allowed)))\n        return roots if limit is None else roots[:limit]",'''        self.check_unchanged()
        if allowed is not None and set(allowed)-self.source_ids:raise ValueError('unit FTS does not cover requested article scope')
        if not terms or allowed is not None and not allowed:return []
        where='unit_fts MATCH ?';params=[expression(terms)]
        if allowed is not None:
            where+=' AND u.source_id IN (SELECT value FROM json_each(?))';params.append(json.dumps(sorted(allowed)))
        cursor=db.execute('SELECT u.source_id FROM unit_fts f JOIN unit u ON u.key=f.key WHERE '+where+' ORDER BY f.rank,f.key',params)
        roots=[];seen=set()
        try:
            for (sid,) in cursor:
                if sid not in seen:seen.add(sid);roots.append(sid)
                if limit is not None and len(roots)>=limit:break
        finally:cursor.close()
        self.check_unchanged()
        return roots''')
anchor='    def law_groups_page(self, db, terms, allowed=None, *, cursor=None, limit=12, unit_keys=None):'
method='''    def rank_page(self,db,terms,allowed=None,*,cursor=None,limit=16,unit_keys=None):
        where,params,binding,offset,nonempty=self._page_query(terms,allowed,cursor,limit,'rank',unit_keys=unit_keys)
        if not nonempty:return {'items':[],'total':0,'next_cursor':None}
        projection=self._projection(db,terms,allowed,unit_keys)
        if projection is not None:
            ranked=sorted((score,key) for hits in projection['hits'].values() for score,key in hits)
            total=len(ranked);selected=ranked[offset:offset+limit];keys=[key for _,key in selected]
            rows=db.execute('SELECT key,json FROM unit WHERE key IN (SELECT value FROM json_each(?))',(json.dumps(keys),)) if keys else []
            bodies={key:json.loads(raw) for key,raw in rows}
            if set(bodies)!=set(keys):raise ValueError('unit FTS projection body missing')
            items=[{**bodies[key],'score':score,'query_terms':list(terms)} for score,key in selected]
        else:
            join=' FROM unit_fts JOIN unit u ON u.key=unit_fts.key WHERE '+where
            total=db.execute('SELECT COUNT(*)'+join,params).fetchone()[0]
            rows=db.execute('SELECT u.json,unit_fts.rank'+join+' ORDER BY unit_fts.rank,u.key LIMIT ? OFFSET ?',[*params,limit,offset])
            items=[{**json.loads(raw),'score':score,'query_terms':list(terms)} for raw,score in rows]
        self.check_unchanged()
        return {'items':items,'total':total,'next_cursor':{'binding':binding,'offset':offset+len(items)} if offset+len(items)<total else None}

'''
replace(p,anchor,method+anchor)
print('FTS edits written')
