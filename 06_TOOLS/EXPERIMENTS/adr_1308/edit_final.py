from pathlib import Path
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized/snapshot';B=S/'02_BACKEND/semantic_runtime'
p=B/'legal_agent/exploration_tools.py';s=p.read_text();start=s.index("        elif mode == 'title':",s.index('    def search('));end=s.index('    def locate(',start);part=s[start:end]
part=part.replace("items.append(self.node_card(did, uid, route=route))", "items.append({'_node_key':(did,uid)})")
part=part.replace("items.append(self.node_card(r['document_id'], str(r['unit_id']), route=route))", "items.append({'_node_key':(r['document_id'],str(r['unit_id']))})")
part=part.replace("        items = list({i['target']: i for i in items}.values())\n        page, next_pos = self.page(items, offset)","""        items = list({('node',*i['_node_key']) if '_node_key' in i else ('target',i['target']): i for i in items}.values())
        page, next_pos = self.page(items, offset)
        page=[self.node_card(*i['_node_key'],route=route) if '_node_key' in i else i for i in page]""")
s=s[:start]+part+s[end:];p.write_text(s)
p=B/'oracle_query_glossary.py';s=p.read_text();old='    def lookup(self,label,*,limit=8,offset=0):\n';new='''    def lookup(self,label,*,limit=8,offset=0):
        self.check_unchanged();self.page(limit,offset)
        if not isinstance(label,str) or not 2<=len(label.strip())<=120:raise ValueError('label length must be 2..120')
        from .oracle_query_cache import for_request,key
        cache=for_request(self.request)
        binding=key('glossary-page',glossary=self.binding,label=label,limit=limit,offset=offset)
        found,value=cache.get(binding)
        if found:return value
        value=self._lookup(label,limit=limit,offset=offset)
        self.check_unchanged();cache.put(binding,value)
        return value

    def _lookup(self,label,*,limit=8,offset=0):
''';assert old in s;s=s.replace(old,new);p.write_text(s)
p=B/'oracle_query_fulltext.py';s=p.read_text();s=s.replace('SELECT p.OWNER_ID AS k,p.LOOKUP_ID AS token,JSON_VALUE','SELECT p.OWNER_ID AS k,p.DOCUMENT_ID AS did,p.LOOKUP_ID AS token,JSON_VALUE')
s=s.replace("        counts=[]\n", "        single_only=all(len(p)==1 for p in phrases)\n        candidate_scope=\" AND did IN (SELECT j.did FROM JSON_TABLE(:q_documents,'$[*]' COLUMNS(did VARCHAR2(512) PATH '$')) j)\" if single_only else ''\n        counts=[]\n")
s=s.replace("counts.append(f'SELECT {i} AS phrase,k,SUM(tf) AS tf FROM postings WHERE token=:{token_names[phrase[0]]} GROUP BY k')", "counts.append(f'SELECT {i} AS phrase,k,SUM(tf) AS tf FROM postings WHERE token=:{token_names[phrase[0]]}'+candidate_scope+' GROUP BY k')")
s=s.replace("        cte=('WITH postings", "        global_df=(' UNION ALL '.join(f'SELECT {i} AS phrase,COUNT(DISTINCT k) AS n FROM postings WHERE token=:{token_names[p[0]]}' for i,p in enumerate(phrases)) if single_only else 'SELECT phrase,COUNT(*) AS n FROM frequencies GROUP BY phrase')\n        cte=('WITH postings")
s=s.replace("'df AS (SELECT phrase,COUNT(*) AS n FROM frequencies GROUP BY phrase), '","'df AS ('+global_df+'), '");p.write_text(s)
print('Final candidate changes written')
