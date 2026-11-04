"""Oracle unit FTS queries over published FTS5 positions (no index download).

The tiny in-memory FTS tokenizer contains only the user's query strings. Corpus
positions, frequencies, lengths, ranking and grouping stay in Oracle. Selected
hit bodies are subsequently read through the hash-checking Records port.
"""
from __future__ import annotations

import json
import sqlite3
import math
from functools import lru_cache

from .oracle_dp_io import DPError, digest
from .oracle_query_catalog import ROW, json_body


def query_phrases(terms):
    if not isinstance(terms,(list,tuple)) or len(terms)>64 or any(not isinstance(t,str) or len(t)>4096 for t in terms):
        raise DPError('QUERY_FTS_TERMS: expected bounded query strings')
    return [tuple(p) for p in _phrases(tuple(terms))]


@lru_cache(maxsize=16)
def _phrases(terms):
    phrases=[]
    # This reproduces SQLite unicode61 exactly, including its Unicode-version
    # and diacritic rules. No original/index/result data enters this connection.
    with sqlite3.connect(':memory:') as db:
        db.execute('PRAGMA temp_store=MEMORY')
        db.execute('CREATE VIRTUAL TABLE query_text USING fts5(body,tokenize="unicode61")')
        db.execute('CREATE VIRTUAL TABLE query_tokens USING fts5vocab(query_text,instance)')
        for term in terms:
            db.execute('DELETE FROM query_text')
            db.execute('INSERT INTO query_text VALUES(?)',(term.replace('"',''),))
            tokens=tuple(r[0] for r in db.execute('SELECT term FROM query_tokens ORDER BY offset'))
            if tokens:
                phrases.append(tokens)
    if sum(map(len,phrases))>256:
        raise DPError('QUERY_FTS_TERMS: query token budget exceeded')
    return tuple(phrases)


class UnitIndex:
    def __init__(self,request):
        self.request,self.sql,self.records=request,request.sql,request.records
        binding=request.snapshot.manifest.get('fulltext') or {}
        path=binding.get('path')
        metadata=self.records.manifest.get('metadata',{}).get(str(path)+'/manifest.json')
        if not metadata or metadata['sha256']!=binding.get('manifest_sha256'):
            raise DPError('QUERY_FTS_BINDING: missing projected fulltext metadata')
        self.manifest=metadata['value']
        if self.manifest.get('schema_version')!='semantic-unit-fulltext-v1':
            raise DPError('QUERY_FTS_FORMAT: Oracle unit search requires the selected unit FTS publication')
        relative=path+'/units.sqlite'
        self.asset=relative
        prefix='asset_'+digest(relative)[:12]+'.'
        self.kinds={name:prefix+name for name in ('unit','unit_fts_posting','unit_fts_length','unit_fts_stats')}
        if not set(self.kinds.values()) <= self.records.manifest['tables'].keys():
            raise DPError('QUERY_FTS_SCHEMA: publish unit positions, lengths and statistics')
        statistics=self.records.page(self.kinds['unit_fts_stats'],lookup_id='stats',limit=1)['rows']
        if len(statistics)!=1:
            raise DPError('QUERY_FTS_STATS: missing statistics')
        self.statistics=statistics[0]
        if any(type(self.statistics.get(k)) is not int or self.statistics[k]<0 for k in ('documents','tokens')):
            raise DPError('QUERY_FTS_STATS: invalid statistics')

    def connect(self):
        return self

    def close(self):
        pass  # Request owns the ORDS budget/connection; no local data handle.

    def set_progress_handler(self,callback,steps):
        self.progress_handler=callback

    def check_unchanged(self):
        callback=getattr(self,'progress_handler',None)
        if callback is not None and callback():
            raise DPError('QUERY_CANCELLED: caller deadline/cancellation reached')
        if digest(self.records.manifest)!=self.request.release_id:
            raise DPError('QUERY_RELEASE_BINDING: request manifest changed')

    def scope_keys(self, db, document_id, unit_ids):
        """Resolve metadata scope in Oracle and verify each selected published row."""
        self.check_unchanged()
        if db is not self or document_id not in self.request.sources.allowed:
            raise DPError('QUERY_SCOPE: fulltext unit scope exceeds request authorization')
        if (not isinstance(document_id, str) or not document_id or
                not isinstance(unit_ids, (list, tuple, set, frozenset)) or
                any(not isinstance(u, str) or not u for u in unit_ids)):
            raise DPError('QUERY_SCOPE: invalid fulltext unit scope')
        selected = sorted(set(unit_ids))
        if not selected:
            return []
        from .oracle_query_db import Connection
        from .oracle_query_catalog import lookup_key
        with Connection(self.request, self.asset) as relation:
            relation.set_progress_handler(lambda: self.check_unchanged(), 1)
            rows = list(relation.execute(
                "SELECT key,source_id FROM unit WHERE document_id=? AND json_extract(json,'$.unit_id') IN (SELECT value FROM json_each(?))",
                (document_id, json.dumps(selected))))
        expected = {key: sid for key, sid in rows}
        if len(expected) != len(rows):
            raise DPError('QUERY_FTS_SCOPE: duplicate selected unit key')
        verified = {}
        keys = sorted(expected)
        for at in range(0, len(keys), 100):
            batch = keys[at:at+100]
            values = self.records.page(self.kinds['unit'], document_id=document_id,
                                       lookup_ids=[lookup_key(k) for k in batch], limit=100)['rows']
            for value in values:
                body = json.loads(value['json'])
                key = value['key']
                if (key not in batch or key in verified or value['document_id'] != document_id or
                        body['key'] != key or body['document_id'] != document_id or
                        body['unit_id'] not in selected or value['source_id'] != body['source_id'] or
                        body['source_id'] != expected[key]):
                    raise DPError('QUERY_FTS_SCOPE: selected unit differs from verified publication')
                verified[key] = body['source_id']
        if verified != expected:
            raise DPError('QUERY_FTS_SCOPE: selected unit row missing')
        self.check_unchanged()
        return sorted(verified.items())

    def _matches(self,terms,allowed=None,unit_keys=None):
        self.check_unchanged()
        phrases=query_phrases(list(terms))
        documents=self.request.sources.allowed
        if hasattr(allowed,'document_ids'):
            if not set(allowed.document_ids)<=documents:
                raise DPError('QUERY_SCOPE: fulltext scope exceeds request authorization')
            documents=frozenset(allowed.document_ids)
            source_ids=None
        else:
            source_ids=None if allowed is None else sorted(set(allowed))
        if not phrases or not documents or source_ids==[] or unit_keys==[]:
            return None,[]
        tokens=list(dict.fromkeys(t for p in phrases for t in p))
        binds=[('q_release',self.request.release_id,'VARCHAR2'),
               ('q_posting',self.kinds['unit_fts_posting'],'VARCHAR2'),
               ('q_length',self.kinds['unit_fts_length'],'VARCHAR2'),
               ('q_documents',json_body(sorted(documents)),'CLOB')]
        token_names={t:'q_token'+str(i) for i,t in enumerate(tokens)}
        binds += [(name,t,'VARCHAR2') for t,name in token_names.items()]
        positions=(f"SELECT p.OWNER_ID AS k,p.TARGET_ID AS col,p.LOOKUP_ID AS token,j.pos FROM {ROW} p,"
            "JSON_TABLE(p.VALUE_JSON,'$.positions[*]' COLUMNS(pos NUMBER PATH '$' ERROR ON ERROR)) j "
            "WHERE p.RELEASE_ID=:q_release AND p.KIND=:q_posting AND p.LOOKUP_ID IN ("+
            ','.join(':'+token_names[t] for t in tokens)+')')
        # Published tf is the exact FTS5 occurrence count. Unigrams do not
        # need to expand occurrence positions; phrases still use adjacency.
        postings=(f"SELECT p.OWNER_ID AS k,p.DOCUMENT_ID AS did,p.LOOKUP_ID AS token,JSON_VALUE(p.VALUE_JSON,'$.tf' RETURNING NUMBER ERROR ON ERROR) AS tf FROM {ROW} p "
            "WHERE p.RELEASE_ID=:q_release AND p.KIND=:q_posting AND p.LOOKUP_ID IN ("+
            ','.join(':'+token_names[t] for t in tokens)+')')
        single_only=all(len(p)==1 for p in phrases)
        candidate_scope=" AND did IN (SELECT j.did FROM JSON_TABLE(:q_documents,'$[*]' COLUMNS(did VARCHAR2(512) PATH '$')) j)" if single_only else ''
        counts=[]
        for i,phrase in enumerate(phrases):
            if len(phrase)==1:
                counts.append(f'SELECT {i} AS phrase,k,SUM(tf) AS tf FROM postings WHERE token=:{token_names[phrase[0]]}'+candidate_scope+' GROUP BY k')
                continue
            joins=''.join(f' JOIN positions p{n} ON p{n}.k=p0.k AND p{n}.col=p0.col AND p{n}.pos=p0.pos+{n}'
                          f' AND p{n}.token=:{token_names[t]}' for n,t in enumerate(phrase[1:],1))
            counts.append(f'SELECT {i} AS phrase,p0.k,COUNT(*) AS tf FROM positions p0'+joins+
                          f' WHERE p0.token=:{token_names[phrase[0]]} GROUP BY p0.k')
        where=["r.DOCUMENT_ID IN (SELECT j.did FROM JSON_TABLE(:q_documents,'$[*]' COLUMNS(did VARCHAR2(512) PATH '$')) j)"]
        if source_ids is not None:
            where.append("r.OWNER_ID IN (SELECT j.sid FROM JSON_TABLE(:q_sources,'$[*]' COLUMNS(sid VARCHAR2(512) PATH '$')) j)")
            binds.append(('q_sources',json_body(source_ids),'CLOB'))
        if unit_keys is not None:
            where.append("r.LOOKUP_ID IN (SELECT j.k FROM JSON_TABLE(:q_units,'$[*]' COLUMNS(k VARCHAR2(512) PATH '$')) j)")
            binds.append(('q_units',json_body(sorted(set(unit_keys))),'CLOB'))
        lengths=(f'SELECT r.LOOKUP_ID AS k,r.DOCUMENT_ID AS did,l.sid,l.n FROM {ROW} r,'
            "JSON_TABLE(r.VALUE_JSON,'$' COLUMNS(sid VARCHAR2(512) PATH '$.source_id',n NUMBER PATH '$.length' ERROR ON ERROR)) l "
            'WHERE r.RELEASE_ID=:q_release AND r.KIND=:q_length AND '+' AND '.join(where))
        n=self.statistics['documents']; total=self.statistics['tokens']
        if not n or not total:
            return None,[]
        binds += [('q_documents_n',n,'NUMBER'),('q_average',total/n,'NUMBER')]
        # FTS5 BM25: global (pre-ACL) phrase document frequency, k1=1.2,
        # b=.75, one indexed body column, negative score sorts first.
        global_df=(' UNION ALL '.join(f'SELECT {i} AS phrase,COUNT(DISTINCT k) AS n FROM postings WHERE token=:{token_names[p[0]]}' for i,p in enumerate(phrases)) if single_only else 'SELECT phrase,COUNT(*) AS n FROM frequencies GROUP BY phrase')
        cte=('WITH postings AS ('+postings+'), '+('positions AS ('+positions+'), ' if any(len(p)>1 for p in phrases) else '')+'frequencies AS ('+' UNION ALL '.join(counts)+'), '
            'df AS ('+global_df+'), '
            'lengths AS ('+lengths+'), matches AS ('
            'SELECT l.k,l.did,l.sid,-SUM(CASE WHEN :q_documents_n<=2*df.n THEN 1e-6 ELSE LN((:q_documents_n-df.n+0.5)/(df.n+0.5)) END'
            '*f.tf*2.2/(f.tf+1.2*(0.25+0.75*l.n/:q_average))) AS score '
            'FROM frequencies f JOIN df ON df.phrase=f.phrase JOIN lengths l ON l.k=f.k GROUP BY l.k,l.did,l.sid) ')
        return cte,binds

    def _projection(self,terms,allowed,unit_keys=None):
        """One bounded metadata result shared by law/article/hit pages."""
        from .oracle_query_cache import for_request, key
        self.check_unchanged()
        scope=({'documents':sorted(allowed.document_ids)} if hasattr(allowed,'document_ids') else None if allowed is None else {'sources':sorted(set(allowed))})
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

    def search_metadata(self,db,terms,allowed):
        from .oracle_query_cache import for_request,key
        from .oracle_query_db import Connection
        self.check_unchanged()
        scope={'documents':sorted(allowed.document_ids)} if hasattr(allowed,'document_ids') else None if allowed is None else {'sources':sorted(set(allowed))}
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

    def rank_page(self,db,terms,allowed=None,*,cursor=None,limit=16,unit_keys=None):
        return self._page(terms,allowed,'rank',cursor=cursor,limit=limit,unit_keys=unit_keys)

    def _page(self,terms,allowed,kind,identity=None,*,cursor=None,limit=12,unit_keys=None):
        if type(limit) is not int or not 1<=limit<=100:
            raise DPError('QUERY_PAGE: fulltext pages require 1..100 rows')
        scope=({'documents':sorted(allowed.document_ids)} if hasattr(allowed,'document_ids') else None if allowed is None else {'sources':sorted(set(allowed))})
        binding=digest({'release':self.request.release_id,'terms':list(terms),'documents':sorted(self.request.sources.allowed),
                        'allowed':scope,'kind':kind,'identity':identity,'units':None if unit_keys is None else sorted(set(unit_keys))})
        offset=0
        if cursor is not None:
            if (not isinstance(cursor,dict) or set(cursor)!={'binding','offset'} or cursor['binding']!=binding or
                    type(cursor['offset']) is not int or cursor['offset']<0):
                raise DPError('QUERY_CURSOR: fulltext cursor belongs to another request scope/query')
            offset=cursor['offset']
        projection=self._projection(terms,allowed,unit_keys)
        if projection is not None:
            return self._project_page(projection,terms,kind,identity,binding,offset,limit)
        cte,binds=self._matches(terms,allowed,unit_keys)
        if cte is None:
            return {'items':[],'total':0,'next_cursor':None}
        predicates=''
        if identity is not None:
            predicates=' WHERE '+('did' if kind=='articles' else 'sid')+'=:q_identity'
            binds.append(('q_identity',identity,'VARCHAR2'))
        if kind=='laws':
            selection='SELECT did,COUNT(DISTINCT sid) AS articles,COUNT(*) AS units,MIN(score) AS score FROM matches GROUP BY did'
            order='score,did'
        elif kind=='articles':
            selection='SELECT sid,COUNT(*) AS units,MIN(score) AS score FROM matches'+predicates+' GROUP BY sid'
            order='score,sid'
        elif kind in ('hits','rank','rank_keys'):
            selection=('SELECT k,did,sid,score FROM matches' if kind=='rank_keys' else 'SELECT k,score FROM matches')+predicates
            order='score,k'
        else:
            raise DPError('QUERY_FTS_KIND: unknown result shape')
        # Analytic count preserves total without a second full scoring query.
        statement='SELECT * FROM ('+cte+'SELECT x.*,COUNT(*) OVER() AS total FROM ('+selection+') x) ORDER BY '+order+f' OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY'
        rows=self.sql.query(statement,binds,limit=limit)
        total=rows[0]['TOTAL'] if rows else 0
        if not rows and offset:
            # A stale/out-of-range cursor is not an empty successful catalogue.
            raise DPError('QUERY_CURSOR: page offset outside completed query result')
        if kind=='laws':
            items=[{'document_id':r['DID'],'article_count':r['ARTICLES'],'unit_count':r['UNITS']} for r in rows]
        elif kind=='articles':
            items=[{'source_id':r['SID'],'unit_count':r['UNITS']} for r in rows]
        elif kind=='rank_keys':
            items=[{'key':r['K'],'document_id':r['DID'],'source_id':r['SID'],'score':r['SCORE']} for r in rows]
        else:
            keys=[r['K'] for r in rows]
            values=self.records.page(self.kinds['unit'],lookup_ids=keys,limit=len(keys))['rows'] if keys else []
            bodies={v['key']:json.loads(v['json']) for v in values}
            if set(bodies)!=set(keys):
                raise DPError('QUERY_FTS_BODY: selected hit body set differs')
            items=[{**bodies[r['K']],'query_terms':list(terms),**({'score':r['SCORE']} if kind=='rank' else {})} for r in rows]
        return {'items':items,'total':total,'next_cursor':{'binding':binding,'offset':offset+len(rows)} if offset+len(rows)<total else None}

    def law_groups_page(self,db,terms,allowed=None,*,cursor=None,limit=12,unit_keys=None):
        return self._page(terms,allowed,'laws',cursor=cursor,limit=limit,unit_keys=unit_keys)

    def article_groups_page(self,db,terms,document_id,allowed=None,*,cursor=None,limit=8,unit_keys=None):
        return self._page(terms,allowed,'articles',document_id,cursor=cursor,limit=limit,unit_keys=unit_keys)

    def hit_page(self,db,terms,source_id,allowed=None,*,cursor=None,limit=16,unit_keys=None):
        return self._page(terms,allowed,'hits',source_id,cursor=cursor,limit=limit,unit_keys=unit_keys)

    def rank_units(self,db,terms,allowed=None,limit=None):
        if limit is not None and (type(limit) is not int or limit<0):
            raise DPError('QUERY_PAGE: invalid fulltext result limit')
        rows,cursor,total_bytes=[],None,0
        while limit is None or len(rows)<limit:
            page=self._page(terms,allowed,'rank',cursor=cursor,limit=100 if limit is None else min(100,limit-len(rows)))
            total_bytes+=len(json_body(page['items']).encode())
            if total_bytes>64*1024*1024:
                raise DPError('QUERY_FTS_RESULT_BUDGET: selected hit bodies exceed request memory budget')
            rows.extend(page['items']);cursor=page['next_cursor']
            if cursor is None:
                break
        return rows

    def rank(self,db,terms,allowed=None,limit=None):
        if limit is not None and (type(limit) is not int or limit<0):
            raise DPError('QUERY_PAGE: invalid fulltext result limit')
        if limit==0:
            return []
        roots=[];seen=set();cursor=None
        while True:
            page=self._page(terms,allowed,'rank_keys',cursor=cursor,limit=100)
            for row in page['items']:
                sid=row['source_id']
                if sid not in seen:seen.add(sid);roots.append(sid)
                if limit is not None and len(roots)>=limit:return roots
            cursor=page['next_cursor']
            if cursor is None:return roots
