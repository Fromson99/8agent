from common import *
x=read(DES/'after-path.json');C=ROOT/x['candidate']/'snapshot'
p=C/'02_BACKEND/semantic_runtime/oracle_query_catalog.py';s=p.read_text();needle="        rows = self.sql.query(f'SELECT ROW_ID,ROW_SHA256,DOCUMENT_ID,LOOKUP_ID,OWNER_ID,TARGET_ID,TO_CLOB(VALUE_JSON) AS VALUE,DBMS_LOB.GETLENGTH(VALUE_JSON) AS N FROM {ROW} WHERE '+ ' AND '.join(where) +"
assert needle in s
s=s.replace(needle,"""        # A packed Gold publication already exposes a trusted kind-specific view.
        # Select it before JSON expansion; keep the outer release/kind/ACL/filter
        # predicates and all envelope/hash/cursor checks below unchanged.
        table = ROW
        mapping = getattr(self.sql, 'gold_config', None)
        published = getattr(mapping, 'manifest', None)
        if isinstance(published, dict) and published.get('extension', {}).get('schema_version') == 'r12-packed-extension-v1':
            table = mapping.names('query_row', only_kind=kind).table
        rows = self.sql.query(f'SELECT ROW_ID,ROW_SHA256,DOCUMENT_ID,LOOKUP_ID,OWNER_ID,TARGET_ID,TO_CLOB(VALUE_JSON) AS VALUE,DBMS_LOB.GETLENGTH(VALUE_JSON) AS N FROM {table} WHERE '+ ' AND '.join(where) +""");p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/multi_entry_navigation.py';s=p.read_text();old="""def freeze(value):
    if isinstance(value,dict):return FrozenDict({k:freeze(v) for k,v in value.items()})
    if isinstance(value,list):return FrozenList(freeze(v) for v in value)
    return value
""";new="""def freeze(value, memo=None, active=None):
    # Stored fields and raw_structure often share the same lists/dicts.
    # Freeze each shared object once within one unit, without cross-unit lifetime.
    if not isinstance(value, (dict, list)):return value
    memo = {} if memo is None else memo
    active = set() if active is None else active
    identity = id(value)
    if identity in active:raise ValueError('cyclic generation metadata')
    if identity in memo:return memo[identity]
    active.add(identity)
    try:
        frozen = (FrozenDict({k:freeze(v,memo,active) for k,v in value.items()})
                  if isinstance(value,dict) else FrozenList(freeze(v,memo,active) for v in value))
        memo[identity] = frozen
        return frozen
    finally:active.remove(identity)
""";assert old in s;s=s.replace(old,new);p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/folder_navigation.py';s=p.read_text();at=s.index('def bind_catalogue(')
helper='''def _catalogue_rows(store, columns):
    if getattr(store,'is_oracle_query',False):
        query="SELECT document_id,name,json_extract(json,'$.document_category') category,json_extract(json,'$.document_kind') kind,json_extract(json,'$.origin') origin,json_extract(json,'$.document_metadata') metadata FROM document"
        yield from store.db.execute(query)
        return
    # Parse each local document once; retain the artifact hash in the same scan.
    # Oracle keeps its registered server-side projection and bounded request port.
    query = ('SELECT document_id,name,json,source_artifact_sha256 FROM document'
             if 'source_artifact_sha256' in columns else
             'SELECT document_id,name,json,NULL AS source_artifact_sha256 FROM document')
    def sqlite_value(value):
        if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
        return int(value) if isinstance(value,bool) else value
    for row in store.db.execute(query):
        value=json.loads(row['json'])
        yield {'document_id':row['document_id'],'name':row['name'],
               'category':sqlite_value(value.get('document_category')),
               'kind':sqlite_value(value.get('document_kind')),
               'origin':sqlite_value(value.get('origin')),
               'metadata':sqlite_value(value.get('document_metadata')),
               'source_artifact_sha256':row['source_artifact_sha256']}


'''
s=s[:at]+helper+s[at:];old='''    query="SELECT document_id,name,json_extract(json,'$.document_category') category,json_extract(json,'$.document_kind') kind,json_extract(json,'$.origin') origin,json_extract(json,'$.document_metadata') metadata FROM document"
    for row in store.db.execute(query):''';assert old in s;s=s.replace(old,"    for row in _catalogue_rows(store,columns):")
s=s.replace("expected=store.db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]", "expected=(store.db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]\n                              if getattr(store,'is_oracle_query',False) else row['source_artifact_sha256'])")
p.write_text(s);print('Three isolated product modules edited; regenerate Oraclecatalog beforefreeze')
