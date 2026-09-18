"""Match a whole question against canonical structure and registered glossary labels.

No provider, generated keywords, gold inputs, or product registry discovery.
Both routes run independently and retain exact question spans and source IDs.
"""
from collections import defaultdict
import hashlib
import json
import re
import threading
import unicodedata

# Pure-data indices of one immutable generation, shared by requests in this process.
# The key binds the source store hash and the glossary bundle hash; per-request
# objects (index tools, glossary connections) are never cached here.
_INDEX_CACHE = {}
_INDEX_LOCK = threading.Lock()


def normalized_span(text):
    chars, offsets = [], []
    for index, char in enumerate(text):
        for value in unicodedata.normalize('NFKC', char).casefold():
            if not value.isspace():
                chars.append(value)
                offsets.append(index)
    return ''.join(chars), offsets


def norm(text):
    return normalized_span(text)[0]


# Korean particles and endings attach to a term's tail, so only the left edge is a
# hard boundary: a registered surface must begin where a word begins. Brackets and
# punctuation open a word, so 「자본시장법」 still anchors.
WORD_CHAR = re.compile(r'[0-9A-Za-z\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3'
                       r'\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')


class SurfaceIndex:
    def __init__(self):
        self.values = defaultdict(list)
        self.prefix = defaultdict(set)
        self.ordered = {}

    def add(self, text, value):
        key = norm(text)
        if len(key) >= 2:
            self.values[key].append(value)
            self.prefix[key[:2]].add(key)
            self.ordered.pop(key[:2], None)

    def candidates(self, prefix):
        order = self.ordered.get(prefix)
        if order is None:
            order = self.ordered[prefix] = sorted(self.prefix.get(prefix, ()),
                                                  key=lambda x: (-len(x), x))
        return order

    def word_start(self, text, offsets, index):
        start = offsets[index]
        # Never anchor inside one raw character that NFKC expanded into several.
        if index and offsets[index-1] == start:
            return False
        return start == 0 or not WORD_CHAR.match(text[start-1])

    def match(self, text):
        """Longest match, left to right, no overlap, anchored at word starts."""
        query, offsets = normalized_span(text)
        result, i = [], 0
        while i < len(query) - 1:
            if not self.word_start(text, offsets, i):
                i += 1
                continue
            hit = None
            for key in self.candidates(query[i:i+2]):
                if not query.startswith(key, i):
                    continue
                end = i + len(key)
                # Latin abbreviations must not match inside a longer ASCII word.
                if (key.isascii() and key.isalpha() and end < len(query)
                        and query[end].isascii() and query[end].isalpha()):
                    continue
                hit = (key, end)
                break
            if hit is None:
                i += 1
                continue
            key, end = hit
            start_raw, end_raw = offsets[i], offsets[end-1]+1
            result.append({'key': key, 'start': start_raw, 'end': end_raw,
                           'text': text[start_raw:end_raw], 'values': self.values[key]})
            i = end
        return result


class ReverseMatcher:
    INDEX_FIELDS = ('documents', 'structures', 'document_names', 'body', 'units', 'members',
                    'sources', 'document_context')
    # An everyday word never seeds articles itself; it enters through the legal terms
    # law.go.kr records as its synonyms. 연관어/상위어/하위어 fan out to 20+ terms per
    # word and 반의어 inverts meaning, so those stay behind the explicit GRAPH tool.
    EVERYDAY_PREFIX = 'moleg:everyday_terms:'
    BRIDGE_CODES = ('140301',)
    BRIDGE_LIMIT = 4

    def __init__(self, store_db, source_tools, glossary, *, cache_key=None):
        self.tools, self.glossary = source_tools, glossary
        if cache_key is not None:
            with _INDEX_LOCK:
                built = _INDEX_CACHE.get(cache_key)
                if built is None:
                    built = _INDEX_CACHE[cache_key] = self._build(store_db, source_tools, glossary)
            for name in self.INDEX_FIELDS:
                setattr(self, name, built[name])
            return
        for name, value in self._build(store_db, source_tools, glossary).items():
            setattr(self, name, value)

    def _build(self, store_db, source_tools, glossary):
        self.documents = {r['document_id']: r['name'] for r in store_db.execute(
            'SELECT document_id,name FROM document ORDER BY document_id')}
        self.structures, self.document_names, self.body = SurfaceIndex(), SurfaceIndex(), SurfaceIndex()
        self.units, self.members = {}, defaultdict(set)
        self.sources = {}
        for row in source_tools.db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') AS unit_id,json_extract(json,'$.heading') AS heading FROM source"):
            self.sources[row['id']] = dict(row)
        for did, name in self.documents.items():
            self.document_names.add(name, did)
        self.document_context = {}
        for row in store_db.execute('SELECT document_id,json FROM document'):
            context = json.loads(row['json']).get('document_metadata', {})
            fields = ('document_title','file_name','folder_names','folder_path','display_name','relative_path','source_category','team')
            self.document_context[row['document_id']] = {k:context[k] for k in fields if k in context}
            self.document_context[row['document_id']]['aliases'] = [
                {k:a[k] for k in fields if k in a} for a in context.get('aliases', [])]
            # Explicit physical names/locations are navigation metadata, not legal evidence.
            for item in [context, *context.get('aliases', [])]:
                labels = [item.get(k, '') for k in ('document_title','file_name','folder_path','display_name')]
                labels += item.get('folder_names', [])
                for label in set(labels):
                    if label: self.document_names.add(label, row['document_id'])
        for r in store_db.execute('SELECT document_id,unit_id,parent_id,json FROM source_unit'):
            u = json.loads(r['json']); key = (r['document_id'], str(r['unit_id']))
            self.units[key] = {'parent': str(r['parent_id']) if r['parent_id'] is not None else None,
                               'family': u.get('family',''), 'surface': u.get('surface',''),
                               'title': u.get('title',''), 'ordinal': u.get('ordinal')}
            family = u.get('family',''); surface = u.get('surface',''); title = u.get('title','')
            locators = []
            if re.fullmatch(r'제\s*\d+(?:-\d+)?\s*[편장절관조항호](?:의\s*\d+)?', surface):
                locators.append(surface)
            ordinal = u.get('ordinal')
            if isinstance(ordinal,list) and len(ordinal)==1 and isinstance(ordinal[0],int):
                kind = '호' if family=='dot_number:1' else '항' if family=='circled' else None
                if kind: locators.append(f'제{ordinal[0]}{kind}')
            for label in set(locators):
                self.structures.add(label, {'document_id':key[0],'unit_id':key[1],'kind':'LOCATOR','family':family})
            # Structural titles come from the selected source tree, never model text.
            title = re.sub(r'^제\s*\d+(?:-\d+)?\s*[편장절관조항호](?:의\s*\d+)?\s*', '', title).strip(' ()')
            if len(norm(title)) >= 2:
                self.structures.add(title, {'document_id':key[0],'unit_id':key[1],'kind':'TITLE','family':family})
        for sid, source in self.sources.items():
            current = str(source['unit_id']) if source['unit_id'] is not None else None
            visited = set()
            while current is not None:
                key = (source['document_id'],current)
                if key in visited: raise ValueError('structural ancestor cycle')
                visited.add(key); self.members[key].add(sid)
                if key not in self.units: break
                current = self.units[key]['parent']
        # Full selected bundle includes native, translated and dictionary surfaces.
        for row in glossary.dbs['lookup'].execute('SELECT DISTINCT key FROM label WHERE length(key)>=2'):
            self.body.add(row[0], row[0])
        return {name: getattr(self, name) for name in self.INDEX_FIELDS}

    def _in_scope(self, tid, scope):
        term = self.tools.terms.get(tid)
        if term is None or (term.get('scope_document_id') and term['scope_document_id'] not in scope):
            return False
        # A legal term is one our selected law data actually uses: at least one article in scope.
        db = getattr(self.tools, 'db', None)
        if db is None:
            return True
        marks = ','.join('?' * len(scope))
        return db.execute('SELECT 1 FROM occurrence o JOIN source s ON s.id=o.source_id '
                          'WHERE o.term_id=? AND s.document_id IN (' + marks + ') LIMIT 1',
                          (tid, *sorted(scope))).fetchone() is not None

    def _bridge(self, everyday, scope):
        identity = self.glossary.dbs.get('identity')
        if identity is None:
            return []
        marks = ','.join('?' * len(self.BRIDGE_CODES))
        rows = identity.execute('SELECT DISTINCT source_id,code FROM official_relation WHERE target_id=? '
                                'AND code IN (' + marks + ') ORDER BY code,source_id',
                                (everyday, *self.BRIDGE_CODES))
        return [(r[0], r[1]) for r in rows if self._in_scope(r[0], scope)][:self.BRIDGE_LIMIT]

    def _unit_sources(self, did, uid):
        visited = set()
        while uid is not None:
            key = (did,uid)
            if key in visited: raise ValueError('structural ancestor cycle')
            visited.add(key)
            if self.members.get(key): return sorted(self.members[key])
            if key not in self.units: break
            uid = self.units[key]['parent']
        return []

    def starts(self, question, scope):
        scope=set(self.tools.validate_scope(scope))
        docs=self.document_names.match(question)
        docs=[h for h in docs if not any(x['start']<=h['start'] and x['end']>=h['end'] and len(x['key'])>len(h['key']) for x in docs)]
        named={d for h in docs for d in h['values'] if d in scope}
        structures={};terms={}
        for h in self.structures.match(question):
            for v in h['values']:
                if v['document_id'] not in scope:continue
                if v['kind']=='LOCATOR' and named and v['document_id'] not in named:continue
                key='structure:'+v['document_id']+':'+v['unit_id']
                row=structures.setdefault(key,{'id':key,**v,'question_spans':[]})
                row['question_spans'].append({k:h[k] for k in ('start','end','text')})
                if v['kind']=='LOCATOR':row['kind']='LOCATOR'
        for h in self.body.match(question):
            span={k:h[k] for k in ('start','end','text')}
            for r in self.glossary.dbs['lookup'].execute('SELECT DISTINCT source,node_id FROM label WHERE key=? ORDER BY source,node_id',(h['key'],)):
                tid=r['node_id'] if r['source']=='dictionary' else 'concept:'+hashlib.sha256((r['source']+'\0'+r['node_id']).encode()).hexdigest()[:24]
                if tid not in self.tools.terms:continue
                if tid.startswith(self.EVERYDAY_PREFIX):
                    for legal,code in self._bridge(tid,scope):
                        row=terms.setdefault(legal,{'id':legal,'question_spans':[]})
                        if span not in row['question_spans']:row['question_spans'].append(span)
                        row.setdefault('bridged_from',[]).append({'everyday_term_id':tid,'relation_code':code})
                    continue
                if not self._in_scope(tid,scope):continue
                row=terms.setdefault(tid,{'id':tid,'question_spans':[]})
                row['question_spans'].append(span)
        return {'documents':[{'id':d,'name':self.documents[d],'document_context':self.document_context.get(d,{})} for d in sorted(named)],
                'structures':sorted(structures.values(),key=lambda x:(min(s['start'] for s in x['question_spans']),x['id'])),
                'terms':sorted(terms.values(),key=lambda x:(min(s['start'] for s in x['question_spans']),x['id']))}
