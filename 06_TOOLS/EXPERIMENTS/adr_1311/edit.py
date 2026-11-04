from common import *
d=read(DES/'optimized-path.json');C=ROOT/d['candidate']/'snapshot'/d['code_relative']
def change(n,old,new):
 p=C/n;s=p.read_text();assert s.count(old)==1,(n,s.count(old));p.write_text(s.replace(old,new))
base='02_BACKEND/semantic_runtime/'
change(base+'multi_entry_navigation.py',"'source_index':MappingProxyType({d:tuple(v) for d,v in sources.items()}),", "'source_index':MappingProxyType({d:tuple(v) for d,v in sources.items()}),\n                     'coordinates':MappingProxyType(dict(bound.stored_coordinates)),")
change(base+'multi_entry_navigation.py',"bound.prepared_structure = value\n", "bound.prepared_structure = value\n        bound.stored_coordinates = value['coordinates']\n        bound._structure_store = store\n        # A bound matcher owns successful selection reuse; never share mutable request results.\n        bound._selection_resolution_cache = None\n")
p=C/(base+'legal_agent/structure_selection.py');s=p.read_text().replace('from copy import deepcopy\n','from copy import deepcopy\nfrom collections import OrderedDict\nimport json\n')
start=s.index('        else:\n            rows = values.for_document',s.index('    def children('));end=s.index('        out = []',start)
s=s[:start]+'''        else:
            prepared = getattr(self.m, 'prepared_structure', None)
            if prepared is not None and values is prepared['units']:
                from .structure_query import document_tree
                ids = document_tree(self.m, self.did)['children'].get(parent, ())
                rows = (((self.did, uid), values[(self.did, uid)]) for uid in ids)
            else:
                # Mutable/test adapters get one fresh index per resolution, never a stale cache.
                if not hasattr(self, '_children_index'):
                    index = {}
                    source = values.for_document(self.did) if hasattr(values, 'for_document') else (
                        (key, unit) for key, unit in values.items() if key[0] == self.did)
                    for key, unit in source:
                        owner = unit.get('parent')
                        index.setdefault(str(owner) if owner is not None else None, []).append((key, unit))
                    self._children_index = index
                rows = self._children_index.get(parent, ())
'''+s[end:]
needle='def resolve(selection, matcher, did, authorized):'
helper='''class _ResolutionCache:
    """Small successful-result memo owned by one immutable bound matcher."""
    def __init__(self):
        self.values = OrderedDict()
        self.bytes = 0

    def get(self, key):
        if key not in self.values:
            return False, None
        self.values.move_to_end(key)
        return True, deepcopy(self.values[key][0])

    def put(self, key, value):
        size = len(json.dumps(value, ensure_ascii=False).encode())
        if size > 1024 * 1024:
            return
        if key in self.values:
            self.bytes -= self.values.pop(key)[1]
        while self.values and (len(self.values) >= 128 or self.bytes + size > 1024 * 1024):
            _, (_, removed) = self.values.popitem(last=False)
            self.bytes -= removed
        self.values[key] = (deepcopy(value), size)
        self.bytes += size


def _resolution_cache(matcher):
    prepared = getattr(matcher, 'prepared_structure', None)
    store = getattr(matcher, '_structure_store', None)
    if (prepared is not None and store is not None
            and matcher.units is prepared['units']
            and matcher.stored_coordinates is prepared.get('coordinates')):
        store.check_unchanged()
        cache = getattr(matcher, '_selection_resolution_cache', None)
        if cache is None:
            cache = matcher._selection_resolution_cache = _ResolutionCache()
        return cache
    # Published Oracle metadata has a request-owned, version/ACL/deadline-bound cache.
    from ..oracle_query_matcher import Units, Coordinates
    if (isinstance(matcher.units, Units) and isinstance(matcher.stored_coordinates, Coordinates)
            and matcher.stored_coordinates.units is matcher.units):
        from ..oracle_query_cache import for_request
        return for_request(matcher.units.request)
    return None


'''
s=s.replace(needle,helper+needle)
s=s.replace("    nodes = Nodes(matcher, did, selection['coordinate_scope'])", """    cache = _resolution_cache(matcher)
    cache_key = ('structure-selection-v1', id(matcher.units), id(matcher.stored_coordinates),
                 digest(getattr(matcher, 'structure_binding', None)), did,
                 digest(sorted(authorized)), digest(selection))
    if cache is not None:
        hit, saved = cache.get(cache_key)
        if hit:
            return saved
    nodes = Nodes(matcher, did, selection['coordinate_scope'])""")
s=s.replace("    return {**record, 'hash': digest(record)}\n", """    result = {**record, 'hash': digest(record)}
    if cache is not None:
        # Recheck source/version before publishing a successful memo entry.
        if _resolution_cache(matcher) is not cache:
            raise ContractError('structure selection binding changed')
        cache.put(cache_key, result)
    return result
""",1)
p.write_text(s)
change(base+'legal_agent/query_scope.py',"    docs = set(documents(session))\n    return frozenset(sid for sid in allowed(session) if session.tools.sources[sid]['document_id'] in docs)",'''    docs = frozenset(documents(session))
    sources = session.tools.sources
    scoped = getattr(sources, 'ids_for_documents', None)
    if scoped is not None:
        verify = getattr(sources, 'cache_binding', None)
        binding = verify() if verify else None
        key = (id(sources), binding, frozenset(session.scope), docs)
        cached = getattr(session, '_direct_search_sources', None)
        if cached is None or cached[0] != key:
            ids = scoped(docs)
            if verify and verify() != binding:
                raise ContractError('search source binding changed')
            session._direct_search_sources = (key, ids)
        # Retain Oracle SourceScope: fulltext pushes its document predicate to SQL.
        return session._direct_search_sources[1]
    return frozenset(sid for sid in allowed(session) if sources[sid]['document_id'] in docs)''')
p=C/(base+'storage.py');s=p.read_text().replace('import threading\n','import threading\nfrom collections import OrderedDict\n')
s=s.replace('        self.path=Path(path).resolve()','        self._source_cache = OrderedDict()\n        self._source_cache_bytes = 0\n        self._source_cache_lock = threading.Lock()\n        self.path=Path(path).resolve()',1)
s=s.replace('    def close(self):self.db.close()', '''    def close(self):
        with self._source_cache_lock:
            self._source_cache.clear()
            self._source_cache_bytes = 0
        self.db.close()''')
old="""        r=self.db.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',(did,str(bid))).fetchone()
        if not r:raise KeyError((did,bid))
        return dict(r)"""
new="""        key = (did, str(bid))
        with self._source_cache_lock:
            if key in self._source_cache:
                self._source_cache.move_to_end(key)
                return dict(self._source_cache[key][0])
        r=self.db.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',key).fetchone()
        if not r:raise KeyError((did,bid))
        value = dict(r)
        self.check_unchanged()
        size = len(json.dumps(value, ensure_ascii=False).encode())
        if size <= 4 * 1024 * 1024:
            with self._source_cache_lock:
                if key in self._source_cache:
                    self._source_cache_bytes -= self._source_cache.pop(key)[1]
                while self._source_cache and (len(self._source_cache) >= 512
                        or self._source_cache_bytes + size > 4 * 1024 * 1024):
                    _, (_, removed) = self._source_cache.popitem(last=False)
                    self._source_cache_bytes -= removed
                self._source_cache[key] = (dict(value), size)
                self._source_cache_bytes += size
        return value"""
assert s.count(old)==1;s=s.replace(old,new);p.write_text(s)
print('Changed4 product modules in isolated candidate only.')
