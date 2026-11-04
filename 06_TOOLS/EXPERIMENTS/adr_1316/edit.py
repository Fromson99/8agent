from common import *
C=ROOT/read(DES/'after-path.json')['candidate']/'snapshot'
p=C/'02_BACKEND/semantic_runtime/oracle_query.py';s=p.read_text();at=s.index('    def unit(self, did, uid):');s=s[:at]+'''    def unit_ids(self, did, *, after=None, limit=MAX_PAGE):
        """Read candidate IDs from the authorized source index, never evidence.

        Callers must fetch and verify the corresponding published native rows.
        Avoid fetching/parsing source JSON when only the indexed identity is used.
        """
        from .oracle_dp_io import names, OWNER, TABLES
        _, binds = self._where(did)
        limit = _page_size(limit)
        n = names(self.sql, 'source_unit', OWNER+'.'+TABLES['source_unit'])
        where = n.c('DATASET_VERSION')+'=:version AND '+n.c('DOCUMENT_ID')+'=:document'
        order = "NLSSORT("+n.c('UNIT_ID')+",'NLS_SORT=BINARY')"
        if after is not None:
            checked_id(after, 'after_unit_id')
            where += " AND "+order+">NLSSORT(:after_unit,'NLS_SORT=BINARY')"
            binds.append(('after_unit',after,'VARCHAR2'))
        projection = ','.join(n.select(c) for c in ('DATASET_VERSION','DOCUMENT_ID','UNIT_ID'))
        rows = self.sql.query(f'SELECT {projection} FROM {n.table} WHERE {where} ORDER BY {order} FETCH FIRST {limit} ROWS ONLY',binds,limit=limit)
        ids=[]
        for row in rows:
            if row['DATASET_VERSION']!=self.snapshot.dataset_version or row['DOCUMENT_ID']!=did:
                raise DPError('QUERY_ROW_BINDING: unit ID belongs to another document/version')
            ids.append(checked_id(row['UNIT_ID'],'unit_id'))
        if ids!=sorted(set(ids)) or (after is not None and any(uid<=after for uid in ids)):
            raise DPError('QUERY_PAGE_ORDER: invalid source unit ID page')
        return {'rows':ids,'next':ids[-1] if len(ids)==limit else None}

'''+s[at:];p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/oracle_query_matcher.py';s=p.read_text();at=s.index('    def children_for(self,did,parent):');s=s[:at]+'''    def _document_rows(self, did):
        # Packed Gold rows have indexed lookup keys but their document/parent
        # fields live inside JSON. Enumerate source IDs before expanding bodies.
        # Other layouts retain the original catalogue path.
        manifest=self.request.records.manifest
        source_ids=getattr(self.request.sources,'unit_ids',None)
        if (not callable(source_ids) or
                manifest.get('extension',{}).get('schema_version')!='r12-packed-extension-v1' or
                'native.unit' not in manifest.get('extension',{}).get('packed_kinds',[])):
            yield from pages(self.request,'native.unit',document_id=did)
            return
        from .oracle_query_cache import for_request
        cache=for_request(self.request)
        proof=list(pages(self.request,'native.structure_proof',document_id=did,lookup_id=did))
        if (len(proof)!=1 or proof[0].get('document_id')!=did or
                type(proof[0].get('unit_count')) is not int or proof[0]['unit_count']<0):
            raise DPError('QUERY_STRUCTURE: missing or invalid document unit count')
        expected=proof[0]['unit_count']
        if expected>self.ROOT_MAX_UNITS:
            yield from pages(self.request,'native.unit',document_id=did)
            return
        ids=[];after=None
        while True:
            cache.check()
            page=source_ids(did,after=after,limit=100)
            ids.extend(page['rows'])
            if len(ids)>expected or len(set(ids))!=len(ids):
                raise DPError('QUERY_STRUCTURE: source unit IDs differ from published count')
            next_id=page['next']
            if next_id is None:break
            if not page['rows'] or next_id!=page['rows'][-1] or next_id==after:
                raise DPError('QUERY_STRUCTURE: source unit cursor made no progress')
            after=next_id
        if len(ids)!=expected:
            raise DPError('QUERY_STRUCTURE: source unit IDs incomplete')
        # The producer binds both row_id and lookup_id to digest([did,uid]).
        # Keep the original global row order while batching below page size.
        ids.sort(key=lambda uid:digest([did,uid]))
        seen=set()
        for start in range(0,len(ids),99):
            group=ids[start:start+99];wanted=set(group)
            rows=list(pages(self.request,'native.unit',document_id=did,
                            lookup_ids=[digest([did,uid]) for uid in group]))
            actual=[row.get('unit_id') for row in rows]
            if (len(rows)!=len(group) or set(actual)!=wanted or
                    any(row.get('document_id')!=did for row in rows) or seen.intersection(actual)):
                raise DPError('QUERY_STRUCTURE: published unit batch incomplete or duplicated')
            seen.update(actual)
            for row in rows:
                cache.check()
                yield row
        cache.check()
        if len(seen)!=expected:raise DPError('QUERY_STRUCTURE: incomplete document batch')

'''+s[at:];old="            for row in pages(self.request,'native.unit',document_id=did):";assert s.count(old)==1;s=s.replace(old,"            for row in self._document_rows(did):");p.write_text(s)
# Bind the existing development mapper and its configuration together. The
# profile remains opt-in; all current Gold names/selection remain unchanged.
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if '02_BACKEND/semantic_runtime/oracle_dp.py' in v.get('files',{}):
  for n in ['02_BACKEND/semantic_runtime/oracle_development_mapping.py','00_SYSTEM/ORACLE/development_g19_1.json']:v['files'][n]=sha(C/n)
  p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print('Two product changes plus complete optional mapping pins; no DDL/adapter change')
