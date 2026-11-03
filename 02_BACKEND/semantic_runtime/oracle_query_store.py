"""Request-local Store contract backed by Oracle, without a generation path."""
from __future__ import annotations

import copy
import json

from sqlglot import exp

from .oracle_dp_io import DPError, TABLES, digest
from .oracle_query_db import Connection
from .oracle_query_catalog import json_body,ROW


class SourceConnection(Connection):
    def __init__(self,request):
        self.request,self.sql=request,request.sql
        self.asset='oracle-source'
        rows=request.records.page('source.schema',limit=10)['rows']
        self.tables={r['table']:('source.schema',r) for r in rows}
        if set(self.tables)!={'document','source_unit','source_block'}:
            raise DPError('QUERY_SOURCE_SCHEMA: missing logical source table schema')
        self.row_factory=None;self.closed=False

    def create_function(self,name,arity,function,*,deterministic=False):
        from .folder_navigation import normalized
        if name!='legal_normalized' or arity!=1 or function is not normalized or not deterministic:
            raise DPError('QUERY_SQL_FUNCTION: only the published normalization projection is supported')

    def _view(self,name,number):
        kind='block_payload' if name=='source_block' else name
        columns={'document_id':'DOCUMENT_ID','name':'NAME','source_artifact_sha256':'SOURCE_ARTIFACT_SHA256',
                 'unit_id':'UNIT_ID','parent_id':'PARENT_ID','block_id':'BLOCK_ID','text':'TEXT','json':'SOURCE_JSON'}
        fields=[]
        for logical,spec in self.tables[name][1]['columns'].items():
            physical=columns[logical]
            value='r.'+physical
            if logical=='json' and kind=='block_payload':
                value="CASE WHEN r.JSON_TEXT_ELIDED=1 THEN JSON_MERGEPATCH(r.SOURCE_JSON,JSON_OBJECT('text' VALUE r.TEXT NULL ON NULL RETURNING CLOB) RETURNING CLOB) ELSE r.SOURCE_JSON END"
            if physical=='NAME' and spec['max_bytes']<=4000:
                value='CAST('+value+' AS VARCHAR2(4000))'
            elif physical in ('SOURCE_JSON','TEXT','NAME'):
                value='TO_CLOB('+value+')'
            fields.append(value+' AS "'+logical+'"')
        keys=self.tables[name][1]['primary_key']
        fields.append('JSON_ARRAY('+','.join('r.'+columns[k] for k in keys)+' RETURNING VARCHAR2(4000)) AS "a8_row_id"')
        suffix=str(number)
        join=''
        if kind=='block_payload' and getattr(self,'_needs_literal',True):
            fields.append("JSON_VALUE(l.VALUE_JSON,'$.text' RETURNING CLOB ERROR ON ERROR) AS \"a8_normalized_text\"")
            join=f" LEFT JOIN {ROW} l ON l.RELEASE_ID=:a8_literal_release{suffix} AND l.KIND='native.block_literal' AND l.DOCUMENT_ID=r.DOCUMENT_ID AND l.OWNER_ID=r.BLOCK_ID "
        text='SELECT '+','.join(fields)+' FROM SIDDA.'+TABLES[kind]+' r '+join+\
             f"WHERE r.DATASET_VERSION=:a8_version{suffix} AND r.DOCUMENT_ID IN (SELECT s.did FROM JSON_TABLE(:a8_scope{suffix},'$[*]' COLUMNS(did VARCHAR2(512) PATH '$')) s)"
        binds=[('a8_version'+suffix,self.request.snapshot.dataset_version,'VARCHAR2'),
               ('a8_scope'+suffix,json_body(sorted(self.request.sources.allowed)),'CLOB')]
        if join: binds.append(('a8_literal_release'+suffix,self.request.release_id,'VARCHAR2'))
        return exp.Subquery(this=exp.Var(this=text)),binds


class Selection:
    def __init__(self,request):
        self.request=request
        self.value=copy.deepcopy(request.records.manifest.get('search_selection'))
        self.fingerprint=digest(self.value) if self.value is not None else None
        self.excluded=request.snapshot.excluded
        self.latest={r['document_id']:r for r in (self.value or {}).get('latest_documents',[])}
        proof=request.records.manifest.get('selection_proof') or {}
        if proof.get('fingerprint')!=self.fingerprint:
            raise DPError('QUERY_SELECTION: published selection proof differs')
        self.native_latest_verified=proof.get('native_latest_verified') is True

    def check_unchanged(self):
        if (digest(self.value) if self.value is not None else None)!=self.fingerprint:
            raise DPError('QUERY_SELECTION: request selection was modified')

    def require_latest(self):
        self.check_unchanged()
        if not self.native_latest_verified and (self.value or {}).get('schema_version')!='filename-search-selection-v2':
            raise DPError('QUERY_SELECTION: Dataiku must verify latest document selection before serving')


class Store:
    is_oracle_query=True

    def __init__(self,request):
        self.oracle_request=request
        self.manifest=copy.deepcopy(request.snapshot.manifest)
        self.selection=Selection(request)
        self.db=SourceConnection(request)
        self._signature=self.binding_signature()

    def binding_signature(self):
        self.selection.check_unchanged()
        return (self.oracle_request.release_id,self.oracle_request.snapshot.binding_hash,digest(self.manifest),
                self.selection.fingerprint,digest(sorted(self.oracle_request.sources.allowed)))

    def check_unchanged(self):
        if self.binding_signature()!=self._signature:
            raise DPError('QUERY_SOURCE_BINDING: request store binding changed')

    def close(self):
        self.db.close()

    def reopen(self):
        self.check_unchanged()
        return Store(self.oracle_request)

    def source(self,did,bid):
        self.check_unchanged()
        return self.oracle_request.sources.source(did,bid)

    def sources(self,did,bids):
        self.check_unchanged()
        ids=list(bids);result=[]
        for start in range(0,len(ids),100):
            result.extend(self.oracle_request.sources.sources(did,ids[start:start+100]))
        return result

    def section(self,did,uid):
        self.check_unchanged()
        return self.oracle_request.sources.section(did,uid)

    def source_scope(self,did,bid):
        self.check_unchanged()
        return self.oracle_request.sources.source_scope(did,bid)
