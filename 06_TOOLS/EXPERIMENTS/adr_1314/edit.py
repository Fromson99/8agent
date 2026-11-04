from common import *
x=read(DES/'after-path.json');C=ROOT/x['candidate']/'snapshot'/x['code_relative'];p=C/'02_BACKEND/semantic_runtime/oracle_query_matcher.py';s=p.read_text()
s=s.replace('class Units(Mapping):\n','class Units(Mapping):\n    # One complete authorized document, bounded independently of point/page LRU.\n    ROOT_MAX_UNITS = 4096\n    ROOT_MAX_BYTES = 16 * 1024 * 1024\n\n')
s=s.replace("        hit, found = for_request(self.request).find_rows(cache_key('native.unit', document_id=did), 'unit_id', key[1])", "        cache = for_request(self.request)\n        document = getattr(self, '_root_document', None)\n        if document is not None and document[0] == did:\n            if key[1] not in document[1]: raise KeyError(key)\n            return copy.deepcopy(document[1][key[1]])\n        hit, found = cache.find_rows(cache_key('native.unit', document_id=did), 'unit_id', key[1])")
start=s.index('    def children_for(self,did,parent):');end=s.index('\n\nclass SourceMetadata',start)
s=s[:start]+'''    def children_for(self,did,parent):
        if did not in self.request.sources.allowed: raise DPError('QUERY_SCOPE: unauthorized unit children')
        from .oracle_query_cache import for_request
        cache = for_request(self.request)
        document = getattr(self, '_root_document', None)
        if document is not None and document[0] == did:
            for uid in document[2].get(parent, ()):
                cache.check()
                yield (did,uid),copy.deepcopy(document[1][uid]['unit'])
            return
        if parent is None:
            # Root lookup already reads the full document. Keep that completed
            # view for subsequent parent/point lookups instead of discarding it.
            # Partial/oversized views never become authoritative cache entries.
            roots=[]; complete={}; children={}; size=0
            for row in pages(self.request,'native.unit',document_id=did):
                actual=row['unit'].get('parent')
                actual=str(actual) if actual is not None else None
                uid=str(row['unit_id'])
                if actual is None: roots.append(row)
                if complete is not None:
                    if row['document_id'] != did: raise DPError('QUERY_SCOPE: root view document differs')
                    if uid in complete: raise DPError('QUERY_STRUCTURE: duplicate unit identity')
                    size+=len(json.dumps(row,ensure_ascii=False).encode())
                    if len(complete)>=self.ROOT_MAX_UNITS or size>self.ROOT_MAX_BYTES:
                        complete=None;children=None
                    else:
                        complete[uid]=row
                        children.setdefault(actual,[]).append(uid)
            cache.check()
            if complete is not None: self._root_document=(did,complete,children)
            for row in roots:
                cache.check()
                yield (did,row['unit_id']),copy.deepcopy(row['unit'])
            return
        for row in pages(self.request,'native.unit',document_id=did,owner_id=str(parent)):
            actual=row['unit'].get('parent')
            if (str(actual) if actual is not None else None)==parent:
                yield (did,row['unit_id']),self.remember(row)['unit']
'''+s[end:];p.write_text(s)
# Recompute only dependent engine pins inside the isolated candidate.
changed={str(p.relative_to(C)):sha(p)}
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if isinstance(v.get('files'),dict) and any(k in v['files'] for k in changed):
  for n,h in changed.items():
   if n in v['files']:v['files'][n]=h
  p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
put(DES/'after-edit.json',{'changed':[n for n,h in x['files'].items() if sha(C/n)!=h],'files':{n:sha(C/n) for n in x['files']}})
print('Boundedrootview candidate implemented')
