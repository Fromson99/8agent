from pathlib import Path
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_1308/optimized/snapshot';B=S/'02_BACKEND/semantic_runtime'
p=B/'legal_agent/request_repair.py';s=p.read_text();old="""    for receipt in read_judgment.state_for(inv,data).get('history',[]):
        targets.update(a['target'] for a in receipt.get('next_actions',[]) if a.get('target'))
""";new="""    state=read_judgment.state_for(inv,data)
    # History stores receipt keys. Only the latest decision can propose a
    # current continuation; an old action cannot revive a closed need.
    history=state.get('history',[])
    latest=state.get('receipts',{}).get(history[-1],{}) if history else {}
    open_text={n.get('text') for n in need_continuity.known_needs(inv,data).values() if n.get('status')=='OPEN'}
    targets.update(a['target'] for a in latest.get('next_actions',[])
                   if a.get('target') and a.get('missing_need') in open_text)
""";assert old in s;s=s.replace(old,new);p.write_text(s)
p=B/'unit_fulltext.py';s=p.read_text();start=s.index('    def search_metadata(self,db,terms,allowed):');end=s.index('    def search_bodies(',start);part=s[start:end];part=part.replace("        where='unit_fts MATCH ?';params=[expression(terms)]", """        from copy import deepcopy
        binding=(self.manifest['index_sha256'],tuple(terms),None if allowed is None else tuple(sorted(allowed)))
        cached=getattr(self,'_navigation_metadata',None)
        if cached is not None and cached[0]==binding:return deepcopy(cached[1])
        where='unit_fts MATCH ?';params=[expression(terms)]""");part=part.replace('        return result\n',"        if size<=4*1024*1024:self._navigation_metadata=(binding,deepcopy(result))\n        return result\n");s=s[:start]+part+s[end:];p.write_text(s)
p=B/'ontology_work/wiki_repository.py';s=p.read_text();start=s.index('        result = {}\n',s.index('    def current_publications'));old=s[start:];assert old.rstrip().endswith('return result');s=s[:start]+'''        result = {ref['publication_id']:False for ref in references}
        visible=[ref for ref in references if self.workspace_visible(ref['bundle_id'])]
        if not visible:return result
        with self.session() as c:
            # One current-authority read; no cache survives revocation.
            binds=[];conditions=[]
            for ref in visible:
                n=len(binds)+1;conditions.append(f'(p.PUB_ID=:{n} AND p.BNDL_ID=:{n+1})')
                binds.extend((ref['publication_id'],ref['bundle_id']))
            rows=self.execute(c,f"SELECT p.PUB_ID,p.BNDL_ID,p.PKG_HASH_VAL,a.DOC_ID FROM {self.tables['publication']} p JOIN {self.tables['head']} h ON h.PUB_ID=p.PUB_ID AND h.BNDL_ID=p.BNDL_ID JOIN {self.tables['anchor']} a ON a.PUB_ID=p.PUB_ID WHERE "+' OR '.join(conditions),tuple(binds)).fetchmany(1025)
            if len(rows)>1024:raise ContractError('workspace publication anchor bound')
            grouped={}
            for pid,bid,sha,did in rows:grouped.setdefault((pid,bid),[]).append((sha,did))
            for ref in visible:
                items=grouped.get((ref['publication_id'],ref['bundle_id']),[])
                result[ref['publication_id']]=bool(items and len(items)<=128
                    and all(sha==ref['package_sha256'] for sha,did in items)
                    and {did for sha,did in items}<=set(allowed_documents))
        return result
''';p.write_text(s)
print('Incremental fixes applied')
