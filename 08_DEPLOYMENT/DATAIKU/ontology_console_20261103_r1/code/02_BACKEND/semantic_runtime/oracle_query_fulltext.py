"""Oracle unit FTS queries over published FTS5 positions (no index download).

The tiny in-memory FTS tokenizer contains only the user's query strings. Corpus
positions, frequencies, lengths, ranking and grouping stay in Oracle. Selected
hit bodies are subsequently read through the hash-checking Records port.
"""
from __future__ import annotations

import json
import sqlite3

from .oracle_dp_io import DPError, digest
from .oracle_query_catalog import ROW, json_body


def query_phrases(terms):
    if not isinstance(terms,(list,tuple)) or len(terms)>64 or any(not isinstance(t,str) or len(t)>4096 for t in terms):
        raise DPError('QUERY_FTS_TERMS: expected bounded query strings')
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
    return phrases


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
        counts=[]
        for i,phrase in enumerate(phrases):
            joins=''.join(f' JOIN positions p{n} ON p{n}.k=p0.k AND p{n}.col=p0.col AND p{n}.pos=p0.pos+{n}'
                          f' AND p{n}.token=:{token_names[t]}' for n,t in enumerate(phrase[1:],1))
            counts.append(f'SELECT {i} AS phrase,p0.k,COUNT(*) AS tf FROM positions p0'+joins+
                          f' WHERE p0.token=:{token_names[phrase[0]]} GROUP BY p0.k')
        where=["r.DOCUMENT_ID IN (SELECT j.did FROM JSON_TABLE(:q_documents,'$[*]' COLUMNS(did VARCHAR2(512) PATH '$')) j)"]
        if source_ids is not None:
            where.append("l.sid IN (SELECT j.sid FROM JSON_TABLE(:q_sources,'$[*]' COLUMNS(sid VARCHAR2(512) PATH '$')) j)")
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
        cte=('WITH positions AS ('+positions+'), frequencies AS ('+' UNION ALL '.join(counts)+'), '
            'df AS (SELECT phrase,COUNT(*) AS n FROM frequencies GROUP BY phrase), '
            'lengths AS ('+lengths+'), matches AS ('
            'SELECT l.k,l.did,l.sid,-SUM(CASE WHEN :q_documents_n<=2*df.n THEN 1e-6 ELSE LN((:q_documents_n-df.n+0.5)/(df.n+0.5)) END'
            '*f.tf*2.2/(f.tf+1.2*(0.25+0.75*l.n/:q_average))) AS score '
            'FROM frequencies f JOIN df ON df.phrase=f.phrase JOIN lengths l ON l.k=f.k GROUP BY l.k,l.did,l.sid) ')
        return cte,binds

    def _page(self,terms,allowed,kind,identity=None,*,cursor=None,limit=12,unit_keys=None):
        if type(limit) is not int or not 1<=limit<=100:
            raise DPError('QUERY_PAGE: fulltext pages require 1..100 rows')
        scope=(sorted(allowed.document_ids) if hasattr(allowed,'document_ids') else None if allowed is None else sorted(set(allowed)))
        binding=digest({'release':self.request.release_id,'terms':list(terms),'documents':sorted(self.request.sources.allowed),
                        'allowed':scope,'kind':kind,'identity':identity,'units':None if unit_keys is None else sorted(set(unit_keys))})
        offset=0
        if cursor is not None:
            if (not isinstance(cursor,dict) or set(cursor)!={'binding','offset'} or cursor['binding']!=binding or
                    type(cursor['offset']) is not int or cursor['offset']<0):
                raise DPError('QUERY_CURSOR: fulltext cursor belongs to another request scope/query')
            offset=cursor['offset']
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
        elif kind in ('hits','rank'):
            selection='SELECT k,score FROM matches'+predicates
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
        roots=list(dict.fromkeys(row['source_id'] for row in self.rank_units(db,terms,allowed)))
        return roots if limit is None else roots[:limit]
