from pathlib import Path
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized/snapshot'
B=S/'02_BACKEND/semantic_runtime'
def replace(path,old,new):
 s=path.read_text();assert old in s,(path,old[:70]);path.write_text(s.replace(old,new,1))

# Reuse only complete enumerations; failures or abandoned generators cannot fill the cache.
p=B/'oracle_query_matcher.py'
replace(p,'    cursor=None;count=0\n','''    from .oracle_query_cache import for_request, key
    cache = for_request(request); cache_key = key(kind, **filters)
    hit, saved = cache.get(cache_key)
    if hit:
        yield from saved
        return
    cursor=None;count=0; collected=[]; size=0
''')
replace(p,'            yield value\n','''            if collected is not None:
                size += len(json.dumps(value,ensure_ascii=False).encode())
                if size <= 4*1024*1024: collected.append(value)
                else: collected = None
            yield copy.deepcopy(value)
''')
replace(p,'        if cursor is None: break\n','''        if cursor is None: break
    if collected is not None: cache.put(cache_key, collected)
''')
replace(p,"        if key in self.cache:\n            self.cache.move_to_end(key)",'''        from .oracle_query_cache import for_request, key as cache_key
        hit, rows = for_request(self.request).get(cache_key('native.unit', document_id=did))
        if hit:
            found = [r for r in rows if str(r['unit_id']) == key[1]]
            if not found: raise KeyError(key)
            if len(found) != 1: raise DPError('QUERY_STRUCTURE: duplicate unit identity')
            return found[0]
        if key in self.cache:
            self.cache.move_to_end(key)''')
replace(p,"    def __getitem__(self,sid):\n        rows=self.request.records.page('native.source',lookup_id=sid,limit=2)['rows']",'''    def __getitem__(self,sid):
        from .oracle_query_cache import for_request, key
        cache=for_request(self.request); cache_key=key('source-metadata',sid=sid)
        hit,value=cache.get(cache_key)
        if hit:return value
        rows=self.request.records.page('native.source',lookup_id=sid,limit=2)['rows']''')
replace(p,"        return rows[0]\n    def __iter__(self): return iter(self.sources)","        cache.put(cache_key,rows[0])\n        return copy.deepcopy(rows[0])\n    def __iter__(self): return iter(self.sources)")

# Keep request arguments intact in the exact-substring branch.
p=B/'legal_agent/exploration_tools.py'
replace(p,"                args=[*docs,normalized(query)]","                params=[*docs,normalized(query)]")
replace(p,"<?';args.extend(bounds)","<?';params.extend(bounds)")
replace(p,"ORDER BY document_id,CAST(block_id AS INTEGER)',args)","ORDER BY document_id,CAST(block_id AS INTEGER)',params)")

# Repeated block-range ownership is immutable within the checked request binding.
p=B/'legal_agent/unit_reading.py'
start=p.read_text().index('def blocks(s,did,uid,extent):');end=p.read_text().index('\n\ndef block_lengths',start)
s=p.read_text();s=s[:start]+'''def blocks(s,did,uid,extent):
    s.store.check_unchanged()
    if did not in s.scope: raise ContractError('block metadata outside request scope')
    binding=(s.store,getattr(s.store,'_binding_state',None),frozenset(s.scope))
    if getattr(s,'_unit_blocks_binding',None)!=binding:
        s._unit_blocks_binding=binding;s._unit_blocks={};s._unit_blocks_count=0
    unit=s.matcher.units[(did,str(uid))]
    key=(did,str(uid),extent,digest(unit))
    if key in s._unit_blocks:return list(s._unit_blocks[key])
    if extent=='exact':
        rows=s.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',(did,uid))
    else:
        lo,hi=unit['span']
        rows=s.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<? ORDER BY CAST(block_id AS INTEGER)',(did,lo,hi))
    values=[str(r[0]) for r in rows]
    s.store.check_unchanged()
    if s._unit_blocks_count+len(values)<=50000:
        s._unit_blocks[key]=tuple(values);s._unit_blocks_count+=len(values)
    return values
'''+s[end:];p.write_text(s)

# Only join the normalization projection when the maintained function is used.
p=B/'oracle_query_store.py'
replace(p,"        if kind=='block_payload':\n            fields.append", "        if kind=='block_payload' and getattr(self,'_needs_literal',True):\n            fields.append")
p=B/'oracle_query_db.py'
replace(p,"        statement,binds=_parameters(statement,list(parameters))",'''        self._needs_literal = bool(re.search(r'\blegal_normalized\s*\(', statement, re.I))
        statement,binds=_parameters(statement,list(parameters))''')
# Schema interpretation is immutable and tiny; cache exact query/parameters only.
replace(p,"        import sqlite3\n        if not statement",'''        import sqlite3
        cache_key=(statement,tuple(parameters))
        cached=getattr(self,'_schema_results',{}).get(cache_key)
        if cached is not None:return Cursor(list(cached[0]),list(cached[1]))
        if not statement''')
replace(p,"            return Cursor([d[0] for d in cursor.description],cursor.fetchall())",'''            names=[d[0] for d in cursor.description];rows=cursor.fetchall()
            if not hasattr(self,'_schema_results'):self._schema_results={}
            if len(self._schema_results)<64:self._schema_results[cache_key]=(tuple(names),tuple(rows))
            return Cursor(names,rows)''')
print('core edits written')
