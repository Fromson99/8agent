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
from . import observability as obs

log = obs.get_logger('matcher')

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


def spaced_span(text):
    """Like normalized_span, but each whitespace run stays one space."""
    chars, offsets = [], []
    for index, char in enumerate(text):
        for value in unicodedata.normalize('NFKC', char).casefold():
            if value.isspace():
                if chars and chars[-1] != ' ':
                    chars.append(' ')
                    offsets.append(index)
                continue
            chars.append(value)
            offsets.append(index)
    if chars and chars[-1] == ' ':
        chars.pop(); offsets.pop()
    return ''.join(chars), offsets


def spaced(text):
    return spaced_span(text)[0]


# Korean particles and endings attach to a term's tail, so only the left edge is a
# hard boundary: a registered surface must begin where a word begins. Brackets and
# punctuation open a word, so 「자본시장법」 still anchors.
WORD_CHAR = re.compile(r'[0-9A-Za-z\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3'
                       r'\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')


class SurfaceIndex:
    # spacing=True assumes the question is spaced correctly: a label matches only
    # with its own spacing, so '회사가 해야' can no longer yield '가해'.
    def __init__(self, spacing=False):
        self.spacing = spacing
        self.span = spaced_span if spacing else normalized_span
        self.values = defaultdict(list)
        self.prefix = defaultdict(set)
        self.ordered = {}

    def add(self, text, value):
        key = self.span(text)[0]
        if len(key.replace(' ', '')) >= 2 and ' ' not in key[:2]:
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

    def match(self, text, *, include_nested=False):
        """Word-boundary matches; optionally retain all nested lexical clues."""
        query, offsets = self.span(text)
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
                if include_nested:
                    start_raw, end_raw = offsets[i], offsets[end-1]+1
                    result.append({'key': key, 'start': start_raw, 'end': end_raw,
                                   'text': text[start_raw:end_raw], 'values': self.values[key]})
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


class MorphIndex:
    """Glossary surfaces matched on noun morphemes of the question (term_morph).

    Keys keep their registered spacing (spacing=True surfaces); a term can only start
    and end on a noun morpheme, so endings (하나요), verbs (위해) and locator fragments
    never seed. Document names and structures keep the character SurfaceIndex.
    """
    def __init__(self):
        self.surfaces = SurfaceIndex(spacing=True)
        self.short = set()

    def add(self, text, value):
        self.surfaces.add(text, value)

    def add_short(self, text, value):
        # One-syllable words (빚, 숏) bypass the 2-character floor; only a whole noun
        # morpheme of the question can match them.
        key = spaced(text)
        if len(key) == 1:
            self.short.add(key)
            self.surfaces.values[key].append(value)

    def match(self, text):
        from . import term_morph  # PeCab loads on first question, not on module import
        values = self.surfaces.values
        return [{'key': key, 'start': start, 'end': end, 'text': text[start:end], 'values': values[key]}
                for start, end, key in term_morph.longest(text, values.__contains__, spaced,
                                                          getattr(self, 'short', set()).__contains__, include_nested=True)]


class ReverseMatcher:
    INDEX_FIELDS = ('documents', 'structures', 'document_names', 'body', 'units', 'members',
                    'sources', 'document_context', 'index_labels', 'title_keys', 'document_aliases',
                    'alias_sources')
    # Official MOLEG terms the generation indexed beyond the glossary dictionary
    # (the whole 법령용어·지식용어 catalogue) seed a question the same way.
    INDEX_PREFIXES = ('moleg:legal_terms:', 'moleg:knowledge_terms:', 'moleg:everyday_terms:')
    # An everyday word never seeds articles itself; it enters through the legal terms
    # law.go.kr records as its synonyms. 연관어/상위어/하위어 fan out to 20+ terms per
    # word and 반의어 inverts meaning, so those stay behind the explicit GRAPH tool.
    EVERYDAY_PREFIX = 'moleg:everyday_terms:'
    BRIDGE_CODES = ('140301',)
    # Without a synonym, a narrow word (숏 → 공매도) may follow 연관어/상위어/하위어 when
    # they reach at most BRIDGE_LIMIT in-scope terms; 반의어 never bridges.
    FALLBACK_CODES = ('140305', '140303', '140304')
    BRIDGE_LIMIT = 4
    TERM_SOURCES = ('dictionary', 'fibo')
    # Public glossaries (GLOSSARY_PIPELINE external_dictionary_collection). A headword
    # with no article in scope and no MOLEG bridge is an orphan: it never seeds articles,
    # it is returned as a reference so the answer can explain it without citing it.
    REFERENCE_SOURCES = ('econedu', 'nts', 'bok', 'kofia', 'krx')

    def __init__(self, store_db, source_tools, glossary, *, cache_key=None, document_aliases=None):
        self.tools, self.glossary = source_tools, glossary
        # Pinned abbreviation projection (document_aliases.load) for generations whose store
        # predates document_metadata.official_abbreviation; callers put it in cache_key.
        self.projection_aliases = dict(document_aliases or {})
        if cache_key is not None:
            with _INDEX_LOCK:
                built = _INDEX_CACHE.get(cache_key)
                if built is None:
                    with obs.step(log,'matcher.build'):
                        built = _INDEX_CACHE[cache_key] = self._build(store_db, source_tools, glossary)
                    obs.event(log,'matcher.cache.ready')
                else:
                    obs.event(log,'matcher.cache.hit')
            for name in self.INDEX_FIELDS:
                setattr(self, name, built[name])
            return
        for name, value in self._build(store_db, source_tools, glossary).items():
            setattr(self, name, value)

    def _load_documents(self, store_db):
        self.documents = {r['document_id']: r['name'] for r in store_db.execute(
            'SELECT document_id,name FROM document ORDER BY document_id')}
        self.document_names = SurfaceIndex()
        # Document titles and official abbreviations name a law; folder and file labels
        # below only locate it. Only title spans shadow glossary terms in starts().
        self.title_keys = set()
        for did, name in self.documents.items():
            self.document_names.add(name, did)
            self.title_keys.add(norm(name))
        self.document_context = {};stored = {}
        for row in store_db.execute('SELECT document_id,json FROM document'):
            context = json.loads(row['json']).get('document_metadata', {})
            fields = ('document_title','file_name','folder_names','folder_path','display_name','relative_path',
                      'source_category','team','official_abbreviation','document_role','raw_role')
            self.document_context[row['document_id']] = {k:context[k] for k in fields if k in context}
            self.document_context[row['document_id']]['aliases'] = [
                {k:a[k] for k in fields if k in a} for a in context.get('aliases', [])]
            # Explicit physical names/locations are navigation metadata, not legal evidence.
            for item in [context, *context.get('aliases', [])]:
                labels = [item.get(k, '') for k in ('document_title','file_name','folder_path','display_name')]
                labels += item.get('folder_names', [])
                for label in set(labels):
                    if label: self.document_names.add(label, row['document_id'])
                if item.get('document_title'): self.title_keys.add(norm(item['document_title']))
                if item.get('official_abbreviation'):
                    stored.setdefault(row['document_id'], []).append(item['official_abbreviation'])
        # The store is the authority; the projection only fills documents it does not cover.
        projected = {d: tuple(a) for d, a in getattr(self, 'projection_aliases', {}).items()
                     if d in self.documents and d not in stored}
        self.document_aliases = {**{d: tuple(dict.fromkeys(a)) for d, a in stored.items()}, **projected}
        self.alias_sources = {'store': len(stored), 'projection': len(projected)}
        for did, aliases in self.document_aliases.items():
            for alias in aliases:
                self.document_names.add(alias, did)
                self.title_keys.add(norm(alias))

    def _build(self, store_db, source_tools, glossary):
        self._load_documents(store_db)
        self.structures = SurfaceIndex()
        self.body = MorphIndex()
        self.units, self.members = {}, defaultdict(set)
        self.sources = {}
        for row in source_tools.db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') AS unit_id,json_extract(json,'$.heading') AS heading FROM source"):
            self.sources[row['id']] = dict(row)
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
        # Only legal-term sources seed a question: the dictionary (법제처, financial
        # glossaries, document definitions) and translated FIBO. General-language
        # sources (nlsh, wikidata) stay reachable through graph navigation only.
        marks = ','.join('?' * len(self.TERM_SOURCES))
        for row in glossary.dbs['lookup'].execute('SELECT DISTINCT label,key FROM label WHERE length(key)>=2 '
                                                  'AND source IN (' + marks + ')', self.TERM_SOURCES):
            self.body.add(row[0], row[1])
        self.index_labels = defaultdict(list)
        for tid, term in getattr(source_tools, 'terms', {}).items():
            if tid.startswith(self.INDEX_PREFIXES) and term.get('label'):
                key = spaced(term['label'])
                if len(key.replace(' ', '')) >= 2:
                    self.index_labels[key].append(tid)
                    self.body.add(term['label'], None)
                elif len(key) == 1 and tid.startswith(self.EVERYDAY_PREFIX):
                    self.index_labels[key].append(tid)
                    self.body.add_short(term['label'], None)
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

    def _relations(self, everyday, codes):
        identity = self.glossary.dbs.get('identity')
        marks = ','.join('?' * len(codes))
        rows = [] if identity is None else [tuple(r) for r in identity.execute(
            'SELECT DISTINCT source_id,code FROM official_relation WHERE target_id=? AND code IN (' + marks + ')',
            (everyday, *codes))]
        db = getattr(self.tools, 'db', None)
        # Relations collected for the whole 지식용어 catalogue live in the generation index.
        if db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE name='moleg_relation'").fetchone():
            rows += [tuple(r) for r in db.execute('SELECT DISTINCT source_id,code FROM moleg_relation WHERE target_id=? '
                                                  'AND code IN (' + marks + ')', (everyday, *codes))]
        return sorted(set(rows), key=lambda r: (r[1], r[0]))

    def _bridge(self, everyday, scope):
        rows = [r for r in self._relations(everyday, self.BRIDGE_CODES) if self._in_scope(r[0], scope)]
        if not rows:
            wide = [r for r in self._relations(everyday, self.FALLBACK_CODES) if self._in_scope(r[0], scope)]
            if len({r[0] for r in wide}) <= self.BRIDGE_LIMIT:
                rows = wide
        return rows[:self.BRIDGE_LIMIT]

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
        # A glossary surface or structure title strictly inside a matched law title or
        # abbreviation is part of that name (자본시장법 -> 자본시장 + 법), not a question concept.
        titles=[(h['start'],h['end']) for h in docs if h['key'] in getattr(self,'title_keys',()) and any(d in scope for d in h['values'])]
        inside=lambda s,e:any(a<=s and e<=b and (b-a)>(e-s) for a,b in titles)
        structures={};terms={};references={}
        for h in self.structures.match(question):
            for v in h['values']:
                if v['document_id'] not in scope:continue
                if v['kind']=='LOCATOR' and named and v['document_id'] not in named:continue
                if v['kind']=='TITLE' and inside(h['start'],h['end']):continue
                key='structure:'+v['document_id']+':'+v['unit_id']
                row=structures.setdefault(key,{'id':key,**v,'question_spans':[]})
                row['question_spans'].append({k:h[k] for k in ('start','end','text')})
                if v['kind']=='LOCATOR':row['kind']='LOCATOR'
        marks=','.join('?'*len(self.TERM_SOURCES))
        for h in self.body.match(question):
            if inside(h['start'],h['end']):continue
            span={k:h[k] for k in ('start','end','text')}
            rows=[r for key in dict.fromkeys(v for v in h['values'] if v is not None) for r in self.glossary.dbs['lookup'].execute(
                'SELECT DISTINCT source,node_id,label FROM label WHERE key=? AND source IN ('+marks+') ORDER BY source,node_id',
                (key,*self.TERM_SOURCES)) if spaced(r['label'])==h['key']]
            rows=[(r['source'],r['node_id']) for r in rows]+[('dictionary',t) for t in getattr(self,'index_labels',{}).get(h['key'],())]
            direct,everyday,orphans=[],[],[]
            for source,node in dict.fromkeys(rows):
                tid=node if source=='dictionary' else 'concept:'+hashlib.sha256((source+'\0'+node).encode()).hexdigest()[:24]
                if tid not in self.tools.terms:continue
                if tid.startswith(self.EVERYDAY_PREFIX):everyday.append(tid)
                elif self._in_scope(tid,scope):direct.append(tid)
                elif self.tools.terms[tid].get('source') in self.REFERENCE_SOURCES:orphans.append(tid)
            for tid in direct:
                row=terms.setdefault(tid,{'id':tid,'question_spans':[]})
                row['question_spans'].append(span)
            # The bridge is for words our law data does not use itself.
            bridged=False
            for tid in ([] if direct else everyday):
                for legal,code in self._bridge(tid,scope):
                    bridged=True
                    row=terms.setdefault(legal,{'id':legal,'question_spans':[]})
                    if span not in row['question_spans']:row['question_spans'].append(span)
                    row.setdefault('bridged_from',[]).append({'everyday_term_id':tid,'relation_code':code})
            for tid in ([] if direct or bridged else orphans):
                references.setdefault(tid,{'id':tid,'question_spans':[]})['question_spans'].append(span)
        return {'documents':[{'id':d,'name':self.documents[d],'document_context':self.document_context.get(d,{})} for d in sorted(named)],
                'structures':sorted(structures.values(),key=lambda x:(min(s['start'] for s in x['question_spans']),x['id'])),
                # Specific terms first: a term linked to fewer articles narrows the search more
                # (경우/사항 stay reachable, just later in the page order).
                'terms':sorted(terms.values(),key=lambda x:(getattr(self.tools,'df',{}).get(x['id'],0),min(s['start'] for s in x['question_spans']),x['id'])),
                'references':sorted(references.values(),key=lambda x:(min(s['start'] for s in x['question_spans']),x['id']))}
