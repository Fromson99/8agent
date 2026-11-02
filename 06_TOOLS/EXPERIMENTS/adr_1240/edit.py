from common import *
S=CAND/'snapshot';P=PORT/'snapshot'/GOLD.relative_to(ROOT)
p=S/'02_BACKEND/semantic_runtime/unit_fulltext.py';s=p.read_text();point='    def cache_namespace(self):'
new='''    def scope_keys(self, db, document_id, unit_ids):
        """Return source-bound keys for the caller's already resolved unit scope."""
        self.check_unchanged()
        selected = sorted(set(unit_ids))
        if not isinstance(document_id, str) or not document_id or any(not isinstance(u, str) or not u for u in selected):
            raise ValueError('invalid fulltext unit scope')
        if not selected:
            return []
        rows = db.execute("SELECT key,source_id FROM unit WHERE document_id=? AND json_extract(json,'$.unit_id') IN (SELECT value FROM json_each(?))",
                          (document_id, json.dumps(selected))).fetchall()
        self.check_unchanged()
        return rows

''';assert point in s;s=s.replace(point,new+point,1);p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/legal_agent/law_candidates.py';s=p.read_text();old='''    rows=db.execute("SELECT key,source_id FROM unit WHERE document_id=? AND json_extract(json,'$.unit_id') IN (SELECT value FROM json_each(?))",
                    (document_id,json.dumps(sorted(units)))).fetchall()''';assert old in s;s=s.replace(old,'    rows=idx.scope_keys(db, document_id, units)');s=s.replace('''    """Resolve selected metadata scope to indexed units before lexical ranking."""
    import json
''','''    """Resolve selected metadata scope to indexed units before lexical ranking."""
''');p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/oracle_query_fulltext.py';s=p.read_text();s=s.replace("        relative=path+'/units.sqlite'","        relative=path+'/units.sqlite'\n        self.asset=relative",1);point='    def _matches(self,terms,allowed=None,unit_keys=None):'
new='''    def scope_keys(self, db, document_id, unit_ids):
        """Resolve metadata scope in Oracle and verify each selected published row."""
        self.check_unchanged()
        if db is not self or document_id not in self.request.sources.allowed:
            raise DPError('QUERY_SCOPE: fulltext unit scope exceeds request authorization')
        selected = sorted(set(unit_ids))
        if not isinstance(document_id, str) or not document_id or any(not isinstance(u, str) or not u for u in selected):
            raise DPError('QUERY_SCOPE: invalid fulltext unit scope')
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

''';assert point in s;s=s.replace(point,new+point,1);p.write_text(s)
p=P/'connect.py';s=p.read_text();point='def open_mapped_engine('
helper='''def mapped_reads(runtime, config, statement, binds):
 """Narrow a single maintained Records SELECT before unpacking its Gold rows.

 Keep every outer ACL/filter/cursor clause and its binds. General relational,
 joined, aliased and multi-kind queries retain the original complete view.
 """
 from semantic_runtime.oracle_query_catalog import ROW
 prefix=('SELECT ROW_ID,ROW_SHA256,DOCUMENT_ID,LOOKUP_ID,OWNER_ID,TARGET_ID,'
         'TO_CLOB(VALUE_JSON) AS VALUE,DBMS_LOB.GETLENGTH(VALUE_JSON) AS N FROM '+ROW+
         ' WHERE RELEASE_ID=:release AND KIND=:kind')
 matches=[value for name,value,typ in binds if name=='kind' and typ=='VARCHAR2']
 if (config.manifest is None or not statement.startswith(prefix+' AND ') and not statement.startswith(prefix+' ORDER BY ') or
     len(matches)!=1 or statement.count(ROW)!=1 or ' UNION ' in statement or ' OR KIND' in statement):
  return runtime.rewrite_reads(statement, config)
 kind=matches[0]
 if kind not in config.manifest['tables']:
  raise runtime.GoldError('EXTENSION_KIND')
 class Scoped:
  def names(self,key):
   return config.names(key, only_kind=kind if key=='query_row' else None)
 return runtime.rewrite_reads(statement, Scoped())

'''
assert point in s;s=s.replace(point,helper+point,1);s=s.replace('return runtime.SQL.query(self,runtime.rewrite_reads(statement,config),binds,limit=limit)','return runtime.SQL.query(self,mapped_reads(runtime,config,statement,binds),binds,limit=limit)');p.write_text(s)
print('Candidate product3 and Gold connector1 edited; no selected bytes changed')
