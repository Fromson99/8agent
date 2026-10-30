"""Lazy navigation tables for Oracle requests; no resident corpus catalogue."""
from __future__ import annotations

from collections.abc import Mapping, Set
from contextlib import contextmanager
import json

from .contracts import digest
from .oracle_dp_io import DPError
from .oracle_query_db import Connection
from .term_index import IndexTools, OccurrenceMap, SourceMap, definition_summary
from .term_tools import TermTools


class SQLMap(Mapping):
    """A maintained key lookup. Iteration streams only when a consumer asks."""
    def __init__(self,db,table,*,key='id',value='json',decode=json.loads,where='1=1',args=()):
        self.db,self.table,self.key,self.value,self.decode=db,table,key,value,decode
        self.where,self.args=where,tuple(args)

    def __getitem__(self,key):
        row=self.db.execute(f'SELECT {self.value} FROM {self.table} WHERE {self.where} AND {self.key}=?',(*self.args,key)).fetchone()
        if row is None: raise KeyError(key)
        return self.decode(row[0])

    def __iter__(self):
        return (r[0] for r in self.db.execute(f'SELECT {self.key} FROM {self.table} WHERE {self.where} ORDER BY {self.key}',self.args))

    def __len__(self):
        return self.db.execute(f'SELECT COUNT(*) FROM {self.table} WHERE {self.where}',self.args).fetchone()[0]

    def items(self):
        return ((r[0],self.decode(r[1])) for r in self.db.execute(
            f'SELECT {self.key},{self.value} FROM {self.table} WHERE {self.where} ORDER BY {self.key}',self.args))

    def values(self):
        return (v for _,v in self.items())


class SourceScope(Set):
    def __init__(self,sources,documents):
        self.sources=sources
        self.document_ids=frozenset(documents)
        if not self.document_ids<=sources.request.sources.allowed:
            raise DPError('QUERY_SCOPE: source scope exceeds pinned authorization')

    def __contains__(self,sid):
        row=self.sources.db.execute('SELECT document_id FROM source WHERE id=?',(sid,)).fetchone()
        return bool(row and row[0] in self.document_ids)

    def __iter__(self):
        # Explicit callers can stream IDs; fulltext recognizes document_ids
        # and executes the scope predicate inside Oracle instead.
        return (r[0] for r in self.sources.db.execute(
            'SELECT id FROM source WHERE document_id IN (SELECT value FROM json_each(?)) ORDER BY id',
            (json.dumps(sorted(self.document_ids)),)))

    def __len__(self):
        return self.sources.db.execute('SELECT COUNT(*) FROM source WHERE document_id IN (SELECT value FROM json_each(?))',
            (json.dumps(sorted(self.document_ids)),)).fetchone()[0]

    def __rsub__(self,other):
        return {sid for sid in other if sid not in self}

    def __rand__(self,other):
        return {sid for sid in other if sid in self}


class Sources(Mapping):
    def __init__(self,request,db):
        self.request,self.db=request,db
        self.kind=db.tables['source'][0]
        self.cache_binding=lambda:(request.release_id,digest(sorted(request.sources.allowed)))

    def __getitem__(self,sid):
        rows=self.request.records.page(self.kind,lookup_id=sid,limit=2)['rows']
        if not rows: raise KeyError(sid)
        if len(rows)!=1: raise DPError('QUERY_SOURCE_DUPLICATE: ambiguous navigation source')
        value=json.loads(rows[0]['json'])
        if value['id']!=sid or value['document_id'] not in self.request.sources.allowed:
            raise DPError('QUERY_SOURCE_SCOPE: navigation source identity mismatch')
        return value

    def __iter__(self):
        return iter(self.ids_for_documents(self.request.sources.allowed))

    def __len__(self):
        return len(self.ids_for_documents(self.request.sources.allowed))

    def ids_for_documents(self,document_ids):
        return SourceScope(self,document_ids)

    @contextmanager
    def measure_loads(self):
        # Preserve the optional diagnostics contract without retaining bodies.
        yield {'source_lookup_backend':'oracle','source_cache_hits':0}


class Lists(Mapping):
    def __init__(self,fetch): self.fetch=fetch
    def __getitem__(self,key):
        values=self.fetch(key)
        if not values: raise KeyError(key)
        return values
    def __iter__(self):
        raise DPError('QUERY_FULL_CATALOGUE: use a bounded key lookup')
    def __len__(self):
        raise DPError('QUERY_FULL_CATALOGUE: use a bounded key lookup')


class Tools(IndexTools):
    def __init__(self,request,db):
        self.request,self.db=request,db
        self.scope=set(request.sources.allowed)
        self.document_ids=frozenset(self.scope)
        self.sources=Sources(request,db)
        self.source_terms=OccurrenceMap(db)
        self.terms=SQLMap(db,'term')
        self.df=SQLMap(db,'term_stats',key='term_id',value='n',decode=lambda x:x)
        self.definitions=SQLMap(db,'definition')
        self.references={}
        self.labels=Lists(self._labels)
        self.edges=Lists(lambda key:[json.loads(r[0]) for r in db.execute(
            "SELECT json FROM edge WHERE json_extract(json,'$.source')=? OR json_extract(json,'$.target')=?",(key,key))])
        self.has_literal='source_literal' in db.tables
        if not self.has_literal:
            raise DPError('QUERY_NAV_SCHEMA: publish source_literal before Oracle serving')
        self.has_reference_witness_count='reference_witness_count' in db.tables

    @property
    def definition_summaries(self):
        raise DPError('QUERY_FULL_CATALOGUE: definition summaries require a question or source filter')

    def definition_summaries_for(self,*,question=None,query=None,labels=None,evidence_text=None,source_ids=None):
        from .oracle_query_catalog import ROW,json_body
        from .navigation_match import norm
        from .term_links import normalized
        filters=[];binds=[('ds_release',self.request.release_id,'VARCHAR2'),
            ('ds_docs',json_body(sorted(self.scope)),'CLOB')]
        if question is not None:
            filters.append('LENGTH(j.surface_key)>=2 AND INSTR(:ds_question,j.surface_key)>0')
            binds.append(('ds_question',norm(question),'CLOB'))
        if query is not None:
            filters.append('INSTR(j.normalized,:ds_query)>0')
            binds.append(('ds_query',normalized(query),'VARCHAR2'))
        if labels is not None:
            filters.append("(j.k IN (SELECT x.v FROM JSON_TABLE(:ds_labels,'$[*]' COLUMNS(v VARCHAR2(4000) PATH '$')) x)"+
                           (' OR INSTR(:ds_text,j.k)>0)' if evidence_text is not None else ')'))
            binds.append(('ds_labels',json_body(sorted(labels)),'CLOB'))
            if evidence_text is not None: binds.append(('ds_text',evidence_text,'CLOB'))
        if source_ids is not None:
            if hasattr(source_ids,'document_ids'):
                filters.append("r.DOCUMENT_ID IN (SELECT x.v FROM JSON_TABLE(:ds_scope,'$[*]' COLUMNS(v VARCHAR2(512) PATH '$')) x)")
                binds.append(('ds_scope',json_body(sorted(source_ids.document_ids)),'CLOB'))
            else:
                filters.append("r.OWNER_ID IN (SELECT x.v FROM JSON_TABLE(:ds_sources,'$[*]' COLUMNS(v VARCHAR2(512) PATH '$')) x)")
                binds.append(('ds_sources',json_body(sorted(source_ids)),'CLOB'))
        if not filters: raise DPError('QUERY_FULL_CATALOGUE: definition filter required')
        statement=(f"SELECT r.ROW_ID,r.LOOKUP_ID FROM {ROW} r,JSON_TABLE(r.VALUE_JSON,'$' COLUMNS(k VARCHAR2(4000) PATH '$.key',normalized VARCHAR2(4000) PATH '$.normalized',surface_key VARCHAR2(4000) PATH '$.surface_key')) j "
            "WHERE r.RELEASE_ID=:ds_release AND r.KIND='native.definition_summary' AND "
            "r.DOCUMENT_ID IN (SELECT x.v FROM JSON_TABLE(:ds_docs,'$[*]' COLUMNS(v VARCHAR2(512) PATH '$')) x) AND "+' AND '.join('('+f+')' for f in filters))
        after=None;count=0
        while True:
            rows=self.request.sql.query(statement+(' AND r.LOOKUP_ID>:ds_after' if after else '')+' ORDER BY r.LOOKUP_ID FETCH NEXT 100 ROWS ONLY',
                binds+([('ds_after',after,'VARCHAR2')] if after else []),limit=100)
            if not rows: break
            values=self.request.records.page('native.definition_summary',lookup_ids=[r['LOOKUP_ID'] for r in rows],limit=len(rows))['rows']
            values={v['id']:v for v in values}
            if set(values)!={r['LOOKUP_ID'] for r in rows}: raise DPError('QUERY_DEFINITION: selected summary set differs')
            for row in rows:
                v=values[row['LOOKUP_ID']]
                count+=1
                if count>10000: raise DPError('QUERY_NAV_BUDGET: definition selection exceeds request budget')
                yield tuple(v[k] for k in ('id','source_id','key','normalized','scope_status'))
            if len(rows)<100: break
            after=rows[-1]['LOOKUP_ID']

    def _labels(self,label):
        result=[r[0] for r in self.db.execute("SELECT id FROM term WHERE json_extract(json,'$.label')=?",(label,))]
        if 'term_surface' in self.db.tables:
            result.extend(r[0] for r in self.db.execute('SELECT term_id FROM term_surface WHERE key=? OR text=?',(label,label)))
        return list(dict.fromkeys(result))

    def match(self,text):
        # Oracle filters registered spellings against this question; the
        # existing longest-match implementation determines overlaps locally.
        pairs=[(r[0],r[1]) for r in self.db.execute(
            "SELECT id,json_extract(json,'$.label') AS label FROM term WHERE length(json_extract(json,'$.label'))>=2 AND instr(?,json_extract(json,'$.label'))>0",(text,))]
        if 'term_surface' in self.db.tables:
            for tid,key,label in self.db.execute('SELECT term_id,key,text FROM term_surface WHERE (length(key)>=2 AND instr(?,key)>0) OR (length(text)>=2 AND instr(?,text)>0)',(text,text)):
                pairs.extend((tid,v) for v in dict.fromkeys((key,label)) if v and v in text)
        temporary=TermTools([],[],[])
        for tid,label in pairs:
            temporary.labels[label].append(tid)
        temporary._rebuild_label_trie()
        return temporary.match(text)


class Index:
    def __init__(self,store):
        self.store,self.request=store,store.oracle_request
        binding=store.manifest.get('navigation') or {}
        self.asset=str(binding.get('path'))+'/navigation.sqlite'
        meta=self.request.records.manifest.get('metadata',{}).get(str(binding.get('path'))+'/manifest.json')
        if not meta or meta['sha256']!=binding.get('manifest_sha256'):
            raise DPError('QUERY_NAV_BINDING: missing bound navigation descriptor')
        self.manifest=meta['value']
        if self.manifest.get('index_sha256')!=self.request.records.manifest['assets'].get(self.asset):
            raise DPError('QUERY_NAV_BINDING: navigation asset digest differs')
        if self.manifest.get('source_store_sha256')!=store.manifest['store_sha256']:
            raise DPError('QUERY_NAV_BINDING: navigation source digest differs')
        self.selection=store.selection

    def cache_binding(self):
        self.store.check_unchanged()
        return (*self.store.binding_signature(),self.manifest['index_sha256'])

    def resident_connect(self):
        return Connection(self.request,self.asset)

    def tools(self,scope):
        self.cache_binding()
        if set(scope)&self.selection.excluded:
            raise DPError('QUERY_SCOPE: excluded document version')
        request=self.request.restrict(scope)
        return Tools(request,Connection(request,self.asset))
