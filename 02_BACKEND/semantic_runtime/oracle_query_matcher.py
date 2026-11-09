"""Request-local reverse navigation over published Oracle lookup rows."""
from collections.abc import Mapping
from collections import OrderedDict
import copy,json

from lawrag.core.legal_coordinate import LegalCoordinate
from .oracle_dp_io import DPError,digest
from .oracle_query_index import Lists
from .navigation_match import ReverseMatcher, SurfaceIndex, MorphIndex


def pages(request,kind,*,budget=10000,**filters):
    from .oracle_query_cache import for_request, key
    cache = for_request(request); cache_key = key(kind, **filters)
    hit, saved = cache.get(cache_key)
    if hit:
        yield from saved
        return
    cursor=None;count=0; collected=[]; size=0
    while True:
        page=request.records.page(kind,limit=100,after=cursor,**filters)
        for value in page['rows']:
            count+=1
            if count>budget:
                raise DPError('QUERY_NAV_BUDGET: narrow the requested navigation page')
            if collected is not None:
                size += len(json.dumps(value,ensure_ascii=False).encode())
                if size <= 4*1024*1024: collected.append(value)
                else: collected = None
            yield copy.deepcopy(value)
        cursor=page['next']
        if cursor is None: break
    if collected is not None: cache.put(cache_key, collected)


class Units(Mapping):
    # One complete authorized document, bounded independently of point/page LRU.
    ROOT_MAX_UNITS = 4096
    ROOT_MAX_BYTES = 16 * 1024 * 1024

    DOCUMENT_MEMO_BYTES = 64 * 1024 * 1024

    def __init__(self,request):
        self.request,self.cache,self.cache_bytes=request,OrderedDict(),0
        self.counts,self.documents,self.document_index,self.document_bytes={},{},{},0
    def unit_count(self,did):
        if did not in self.request.sources.allowed: raise DPError('QUERY_SCOPE: unauthorized unit catalogue')
        if did not in self.counts:
            proof=list(pages(self.request,'native.structure_proof',document_id=did,lookup_id=did))
            if (len(proof)!=1 or proof[0].get('document_id')!=did or
                    type(proof[0].get('unit_count')) is not int or proof[0]['unit_count']<0):
                raise DPError('QUERY_STRUCTURE: missing or invalid document unit count')
            self.counts[did]=proof[0]['unit_count']
        return self.counts[did]
    def document_rows(self,did):
        """Every unit row of one document: budget = its published unit count, memo per request."""
        if did in self.documents:
            for row in self.documents[did]:
                yield copy.deepcopy(row)
            return
        expected=self.unit_count(did)
        # Read the whole listing before yielding: consumers that look up ancestors while
        # iterating are then served by the memo instead of one SQL per unit.
        rows=list(pages(self.request,'native.unit',budget=max(10000,expected),document_id=did))
        if len(rows)!=expected:
            raise DPError('QUERY_STRUCTURE: document unit listing differs from its published count')
        size=sum(len(json.dumps(row,ensure_ascii=False).encode()) for row in rows)
        if self.document_bytes+size<=self.DOCUMENT_MEMO_BYTES:
            self.documents[did]=rows;self.document_bytes+=size
            self.document_index[did]={str(r['unit_id']):r for r in rows}
        for row in rows:
            yield copy.deepcopy(row)
    def remember(self,row):
        key=(row['document_id'],row['unit_id'])
        size=len(json.dumps(row,ensure_ascii=False).encode())
        if key in self.cache: self.cache_bytes-=self.cache.pop(key)[1]
        if size<=4*1024*1024:
            self.cache[key]=(copy.deepcopy(row),size);self.cache_bytes+=size
        while len(self.cache)>512 or self.cache_bytes>4*1024*1024:
            _,(_,size)=self.cache.popitem(last=False);self.cache_bytes-=size
        return row
    def row(self,key):
        did,uid=key
        if did not in self.request.sources.allowed: raise KeyError(key)
        key=(did,str(uid))
        index=self.document_index.get(did)
        if index is not None:
            # A listed document answers point lookups from the request memo (no SQL per unit).
            if key[1] not in index: raise KeyError(key)
            return copy.deepcopy(index[key[1]])
        from .oracle_query_cache import for_request, key as cache_key
        cache = for_request(self.request)
        document = getattr(self, '_root_document', None)
        if document is not None and document[0] == did:
            if key[1] not in document[1]: raise KeyError(key)
            return copy.deepcopy(document[1][key[1]])
        hit, found = cache.find_rows(cache_key('native.unit', document_id=did), 'unit_id', key[1])
        if hit:
            if not found: raise KeyError(key)
            if len(found) != 1: raise DPError('QUERY_STRUCTURE: duplicate unit identity')
            return found[0]
        if key in self.cache:
            self.cache.move_to_end(key)
            return copy.deepcopy(self.cache[key][0])
        rows=self.request.records.page('native.unit',document_id=did,lookup_id=digest([did,str(uid)]),limit=2)['rows']
        if not rows: raise KeyError(key)
        if len(rows)!=1: raise DPError('QUERY_STRUCTURE: duplicate unit identity')
        return self.remember(rows[0])
    def prefetch(self,keys):
        """Fill the point-lookup cache for many (document, unit) keys: one SQL per 99 keys."""
        groups={}
        for did,uid in dict.fromkeys((d,str(u)) for d,u in keys):
            if did in self.request.sources.allowed and did not in self.document_index and (did,uid) not in self.cache:
                groups.setdefault(did,[]).append(uid)
        for did,uids in groups.items():
            for at in range(0,len(uids),99):
                batch=uids[at:at+99];wanted={digest([did,uid]):uid for uid in batch}
                rows=self.request.records.page('native.unit',document_id=did,lookup_ids=sorted(wanted),limit=100)['rows']
                if len(rows)>len(batch): raise DPError('QUERY_STRUCTURE: duplicate unit identity')
                for row in rows:
                    if row.get('document_id')!=did or str(row.get('unit_id')) not in batch:
                        raise DPError('QUERY_STRUCTURE: prefetched unit outside the requested keys')
                    self.remember(row)
    def __getitem__(self,key): return self.row(key)['unit']
    def __iter__(self): return (key for key,_ in self.items())
    def __len__(self): return sum(r['unit_count'] for r in pages(self.request,'native.structure_proof'))
    def items(self):
        return (((r['document_id'],r['unit_id']),r['unit']) for r in pages(self.request,'native.unit'))
    def for_document(self,did):
        if did not in self.request.sources.allowed: raise DPError('QUERY_SCOPE: unauthorized unit catalogue')
        return (((r['document_id'],r['unit_id']),self.remember(r)['unit']) for r in self.document_rows(did))

    def _document_rows(self, did):
        # Packed Gold rows have indexed lookup keys but their document/parent
        # fields live inside JSON. Enumerate source IDs before expanding bodies.
        # Other layouts retain the original catalogue path.
        manifest=self.request.records.manifest
        source_ids=getattr(self.request.sources,'unit_ids',None)
        if (not callable(source_ids) or
                manifest.get('extension',{}).get('schema_version')!='r12-packed-extension-v1' or
                'native.unit' not in manifest.get('extension',{}).get('packed_kinds',[])):
            yield from self.document_rows(did)
            return
        from .oracle_query_cache import for_request
        cache=for_request(self.request)
        proof=list(pages(self.request,'native.structure_proof',document_id=did,lookup_id=did))
        if (len(proof)!=1 or proof[0].get('document_id')!=did or
                type(proof[0].get('unit_count')) is not int or proof[0]['unit_count']<0):
            raise DPError('QUERY_STRUCTURE: missing or invalid document unit count')
        expected=proof[0]['unit_count']
        if expected>self.ROOT_MAX_UNITS:
            yield from self.document_rows(did)
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

    def children_for(self,did,parent):
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
            for row in self._document_rows(did):
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


class SourceMetadata(Mapping):
    def __init__(self,request,sources): self.request,self.sources=request,sources
    def __getitem__(self,sid):
        if not isinstance(sid,str) or not sid:
            raise KeyError(sid)  # SQLite dict semantics; lookup_id=None would mean "no filter"
        from .oracle_query_cache import for_request, key
        cache=for_request(self.request); cache_key=key('source-metadata',sid=sid)
        hit,value=cache.get(cache_key)
        if hit:return value
        rows=self.request.records.page('native.source',lookup_id=sid,limit=2)['rows']
        if not rows: raise KeyError(sid)
        if len(rows)!=1: raise DPError('QUERY_SOURCE_DUPLICATE: ambiguous source metadata')
        cache.put(cache_key,rows[0])
        return copy.deepcopy(rows[0])
    def __iter__(self): return iter(self.sources)
    def __len__(self): return len(self.sources)
    def ids_for_documents(self,ids): return self.sources.ids_for_documents(ids)
    def items(self): return ((r['id'],r) for r in pages(self.request,'native.source'))
    def for_document(self,did): return ((r['id'],r) for r in pages(self.request,'native.source',document_id=did))


class RemoteSurface(SurfaceIndex):
    # A two-character group above GROUP_ROWS rows (field '제1' 34,595) is not read whole:
    # every key that can match at a question position is looked up exactly instead.
    GROUP_ROWS = 1000
    MAX_KEY = 128
    def __init__(self,request,group):
        super().__init__()
        self.request,self.group=request,group
        self.large,self.looked,self.loaded=set(),set(),set()
    def candidates(self,prefix):
        # The prefix and its values live for this request only.
        if prefix in self.large:
            return sorted(self.prefix.get(prefix,()),key=lambda x:(-len(x),x))
        if prefix not in self.ordered:
            rows=[]
            for row in pages(self.request,'native.surface',lookup_id=self.group+':'+prefix,owner_id=self.group):
                rows.append(row)
                if len(rows)>self.GROUP_ROWS:
                    self.large.add(prefix)
                    return sorted(self.prefix.get(prefix,()),key=lambda x:(-len(x),x))
            for row in rows:
                key=row['key']
                self.values[key].append(row['value'])
                self.prefix[prefix].add(key)
                self.loaded.add(key)
            self.ordered[prefix]=sorted(self.prefix[prefix],key=lambda x:(-len(x),x))
        return self.ordered[prefix]
    def _exact(self,query,i):
        wanted=[query[i:j] for j in range(i+2,min(len(query),i+self.MAX_KEY)+1)]
        wanted=[k for k in dict.fromkeys(wanted) if k not in self.looked]
        for at in range(0,len(wanted),100):
            batch={digest(k):k for k in wanted[at:at+100]}
            for row in pages(self.request,'native.surface',owner_id=self.group,target_ids=sorted(batch)):
                key=row['key']
                if key in batch.values() and key not in self.loaded:
                    self.values[key].append(row['value'])
                    self.prefix[key[:2]].add(key)
            self.looked.update(batch.values())
    def match(self,text,*,include_nested=False):
        query,offsets=self.span(text)
        for i in range(len(query)-1):
            if self.word_start(text,offsets,i):
                prefix=query[i:i+2]
                self.candidates(prefix)
                if prefix in self.large:
                    self._exact(query,i)
        return super().match(text,include_nested=include_nested)


class BodyValues(Mapping):
    def __init__(self,request): self.request,self.values=request,{}
    def __getitem__(self,key):
        if key not in self.values:
            self.values[key]=[r['value'] for r in pages(self.request,'native.surface',owner_id='body',target_id=digest(key)) if r['key']==key]
        if not self.values[key]: raise KeyError(key)
        return self.values[key]
    def __iter__(self): raise DPError('QUERY_FULL_CATALOGUE: use a registered surface lookup')
    def __len__(self): raise DPError('QUERY_FULL_CATALOGUE: use a registered surface lookup')


class ShortWords:
    def __init__(self,values): self.values=values
    def __contains__(self,key): return len(key)==1 and key in self.values


class Coordinates(Mapping):
    def __init__(self,units): self.units=units
    @staticmethod
    def decode(v):
        if not v: return None
        chain=v.get('chain',[]);subs=tuple(x.get('sub') for x in chain)
        return LegalCoordinate(v['unit'],v['n'],sub=v.get('sub'),dash=v.get('dash'),
            chain=tuple((x['unit'],x['n']) for x in chain),chain_subs=subs if any(x is not None for x in subs) else ())
    def __getitem__(self,key): return self.decode(self.units.row(key)['coordinate'])
    def __iter__(self): return iter(self.units)
    def __len__(self): return len(self.units)
    def for_document(self,did):
        return (((r['document_id'],r['unit_id']),self.decode(r['coordinate'])) for r in self.units.document_rows(did))
    def for_document_units(self,did):
        # The same listing as for_document, with each row's unit: no lookup per unit.
        return (((r['document_id'],r['unit_id']),self.decode(r['coordinate']),r['unit']) for r in self.units.document_rows(did))


class CoordinateIndex(Lists):
    """Body-article coordinates: exact key lookups, or one document's indexed units."""
    def __init__(self,request):
        self.request=request
        super().__init__(lambda key:[r['unit_id'] for r in pages(request,'native.coordinate',document_id=key[0],lookup_id=digest(list(key)))])
    def document_units(self,did):
        # Each row is published under its own unit's coordinate (one listing per document).
        return frozenset(r['unit_id'] for r in pages(self.request,'native.coordinate',document_id=did))


class Matcher(ReverseMatcher):
    def __init__(self,store,tools,glossary,*,document_aliases=None,origin_projection=None):
        self.request=tools.request
        from .navigation_compatibility import require
        require(self.request.records.manifest.get('navigation_compilers',{}))
        self.tools,self.glossary=tools,glossary
        self.projection_aliases=dict(document_aliases or {})
        self._load_documents(store.db)
        self.structures=RemoteSurface(self.request,'structure')
        self.body=MorphIndex()
        self.body.surfaces.values=BodyValues(self.request)
        self.body.short=ShortWords(self.body.surfaces.values)
        self.index_labels=Lists(lambda key:[r['term_id'] for r in pages(self.request,'native.index_label',lookup_id=digest(key))])
        self.units=Units(self.request)
        self.sources=SourceMetadata(self.request,tools.sources)
        self.members=Lists(lambda key:[r['source_id'] for r in pages(self.request,'native.member',document_id=key[0],lookup_id=digest([key[0],str(key[1])]))])
        self.stored_coordinates=Coordinates(self.units)
        self.coordinate_index=CoordinateIndex(self.request)
        self.structure_binding={'generation_id':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256'],'authority':'source_unit.json'}
        self.navigation_store=store
        from .folder_navigation import bind_catalogue
        bind_catalogue(self,store,origin_projection)

    def validate_structure(self,scope):
        if not set(scope)<=self.request.sources.allowed:
            raise DPError('QUERY_SCOPE: structure validation scope exceeds request')
        proofs={r['document_id']:r for r in pages(self.request,'native.structure_proof')}
        if not set(scope)<=proofs.keys():
            raise DPError('QUERY_STRUCTURE: missing Dataiku validation proof')
        return sum(proofs[did]['unit_count'] for did in scope)
