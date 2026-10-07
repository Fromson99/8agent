"""Generation-bound metadata navigation. No body search or inferred legal structure."""
from copy import deepcopy
from pathlib import Path,PurePosixPath
import hashlib,json,re,secrets,threading,unicodedata
from . import observability as obs

_CATALOGUE_CACHE = {}
_CATALOGUE_LOCK = threading.Lock()
log = obs.get_logger('folder_catalogue')

PUBLIC_PROVIDERS=frozenset(('kofia','krx','law','moleg','fsc','expc','prec'))

def normalized(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text)).casefold()

def classify_path(path):
    """Path is relative to the admitted RAW root; keep every actual folder component."""
    if not isinstance(path,str) or not path or '\\' in path:raise ValueError('RAW-relative POSIX path required')
    p=PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('invalid RAW-relative path')
    parts=p.parts;category='unknown';provider=parts[0]
    if parts[0]=='internal':category='internal'
    elif parts[0]=='external':
        if len(parts)<3:raise ValueError('external path needs provider and filename')
        category='external';provider=parts[1]
    elif parts[0] in PUBLIC_PROVIDERS:category='external'
    folder=str(p.parent)
    logical=folder if parts[0] in ('internal','external') else 'external/'+folder if category=='external' else folder
    return {'category':category,'tags':['내규'] if category=='internal' else [],'provider':provider,'raw_relative_path':str(p),'folder':folder,'navigation_folder':logical,'classification_basis':'admitted RAW folder location'}

def load_origin_projection(root,config,store):
    """Select the pinned projection for this exact generation; other generations get none."""
    bindings=[b for b in (config or {}).get('origin_projections',[]) if b.get('generation_id')==store.manifest['generation_id']]
    if not bindings:return None
    if len(bindings)!=1:raise ValueError('multiple origin projections for one generation')
    base=Path(root).resolve();path=(base/bindings[0]['path']).resolve();path.relative_to(base)
    with path.open('rb') as stream:data=stream.read()
    if hashlib.sha256(data).hexdigest()!=bindings[0]['sha256']:raise ValueError('origin projection hash mismatch')
    value=json.loads(data)
    if value.get('schema_version')!='document-origin-projection-v1':raise ValueError('unsupported origin projection')
    for k in ('generation_id','store_sha256'):
        if value.get(k)!=store.manifest[k]:raise ValueError('stale origin projection')
    return value

def bind_catalogue(matcher,store,projection=None):
    """Origin projection supplied explicitly; old stores remain unknown without provenance."""
    projection_hash = hashlib.sha256(json.dumps(projection,sort_keys=True,ensure_ascii=False).encode()).hexdigest() if projection is not None else None
    from .team_scope import generation_key
    key = (generation_key(store),projection_hash)
    with _CATALOGUE_LOCK:
        cached = _CATALOGUE_CACHE.get(key)
    if cached is not None:
        matcher.document_catalogue = cached
        obs.event(log,'folder_catalogue.cached')
        return matcher
    origins={}
    if projection is not None:
        for k in ('generation_id','store_sha256'):
            if projection[k]!=store.manifest[k]:raise ValueError('stale origin projection')
        origins=projection['documents']
    catalogue={}
    columns={r[1] for r in store.db.execute('PRAGMA table_info(document)')}
    query="SELECT document_id,name,json_extract(json,'$.document_category') category,json_extract(json,'$.document_kind') kind,json_extract(json,'$.origin') origin,json_extract(json,'$.document_metadata') metadata FROM document"
    for row in store.db.execute(query):
        did=row['document_id'];raw=row['category'];kind=row['kind'];origin=origins.get(did)
        if origin is None and row['origin']:
            origin=json.loads(row['origin'])
            if origin.get('document_id')!=did:raise ValueError('origin document mismatch')
        category=raw if raw in ('internal','external') else {'internal_regulation':'internal','internal_rule':'internal','external_statute':'external','published_rule':'external'}.get(kind,'unknown')
        record={'id':did,'name':row['name'],'category':category,'tags':['내규'] if category=='internal' else [],'provider':None,'folder':None,'navigation_folder':None,'classification_basis':'stored document metadata' if category!='unknown' else 'origin not recorded; never inferred from title'}
        # Current ingestion persists admitted relative paths in document_metadata.
        # The immutable store hash binds these fields; never inspect the live RAW tree.
        if origin is None and row['metadata']:
            metadata = json.loads(row['metadata'])
            relative = metadata.get('relative_path')
            source = metadata.get('source_category')
            if relative and source in ('internal', 'external'):
                path = PurePosixPath(relative)
                if path.is_absolute() or '..' in path.parts or '\\' in relative:
                    raise ValueError('invalid stored document metadata path')
                if source == 'internal' and path.parts[0] != 'internal':
                    relative = 'internal/' + relative
                elif source == 'external' and path.parts[0] not in PUBLIC_PROVIDERS | {'external'}:
                    relative = 'external/' + relative
                classified = classify_path(relative)
                if classified['category'] != source:
                    raise ValueError('stored document source category/path conflict')
                record.update(classified, classification_basis='hash-bound ingestion document_metadata',
                              aliases=deepcopy(metadata.get('aliases', [])))
        if origin:
            if origin.get('status')!='verified':
                record.update(category='unknown',tags=[],classification_basis='ambiguous/unverified origin')
            else:
                if 'source_artifact_sha256' in columns:
                    expected=store.db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]
                    if origin.get('source_artifact_sha256')!=expected:raise ValueError('origin source artifact mismatch')
                record.update(classify_path(origin['raw_relative_path']));record['origin']=deepcopy(origin)
        catalogue[did]=record
    with _CATALOGUE_LOCK:
        _CATALOGUE_CACHE.clear()
        matcher.document_catalogue=_CATALOGUE_CACHE.setdefault(key,catalogue)
    obs.event(log,'folder_catalogue.ready')
    return matcher

class FolderNavigator:
    """One instance per conversation. Contexts are opaque server-owned narrowing handles."""
    def __init__(self,matcher,store):
        self.m,self.store=matcher,store;self.contexts={};self.binding={k:store.manifest[k] for k in ('generation_id','store_sha256')}
    def scope(self,authorized,context=None):
        allowed=set(self.m.tools.validate_scope(authorized))
        if context:
            if context not in self.contexts:raise ValueError('unknown navigation context; reselect document')
            saved=self.contexts[context]
            if saved['binding']!=self.binding:raise ValueError('stale navigation context')
            allowed&=set(saved['document_ids'])
        return allowed
    def remember(self,ids,filters):
        handle='NC'+secrets.token_hex(12);self.contexts[handle]={'binding':deepcopy(self.binding),'document_ids':sorted(ids),'filters':deepcopy(filters)}
        return handle
    def catalogue(self,authorized,*,context=None,category='all',provider='',folder='',title_query='',offset=0,limit=100):
        if category not in ('all','internal','external','unknown'):raise ValueError('invalid category')
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=500:raise ValueError('invalid pagination')
        if len(title_query)>500:raise ValueError('title query too long')
        if folder and (folder.startswith('/') or '..' in PurePosixPath(folder).parts):raise ValueError('invalid folder')
        scope=self.scope(authorized,context);records=[self.m.document_catalogue[d] for d in sorted(scope)];q=normalized(title_query)
        def matches(d):
            path=d.get('navigation_folder') or ''
            return (category=='all' or d['category']==category) and (not provider or d['provider']==provider) and (not folder or path==folder or path.startswith(folder.rstrip('/')+'/')) and (not q or q in normalized(d['name']))
        items=[deepcopy(d) for d in records if matches(d)];filters=dict(category=category,provider=provider,folder=folder,title_query=title_query,search_field='document.name')
        selected=self.remember([d['id'] for d in items],filters);groups={}
        for d in items:
            path=d.get('navigation_folder')
            if path:groups[path]=groups.get(path,0)+1
        page=items[offset:offset+limit];unknown=sum(d['category']=='unknown' for d in records)
        return {'documents':page,'total':len(items),'offset':offset,'next_offset':offset+limit if offset+limit<len(items) else None,'complete':offset==0 and len(page)==len(items),'context':selected,'filters':filters,'folders':[{'path':p,'document_count':n} for p,n in sorted(groups.items())],'unknown_category_count':unknown,'classification_complete':unknown==0,'scope_document_count':len(scope),'content_read':False,'scope_note':'authorized documents intersect previous navigation context; title-only literal normalized search'}
    def select(self,authorized,context,document_id):
        if document_id not in self.scope(authorized,context):raise ValueError('document outside current navigation scope')
        return self.remember([document_id],{'selected_document_id':document_id})
    def document(self,authorized,context,document_id=''):
        scope=self.scope(authorized,context)
        if document_id:
            if document_id not in scope:raise ValueError('document outside current navigation scope')
            return document_id
        if len(scope)!=1:raise ValueError('DOCUMENT_SELECTION_REQUIRED: '+str(len(scope)))
        return next(iter(scope))
    def outline(self,authorized,*,context,document_id='',root_unit_id='',include_children=False,offset=0,limit=100):
        did=self.document(authorized,context,document_id)
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=500:raise ValueError('invalid pagination')
        units={uid:u for (d,uid),u in self.m.units.items() if d==did}
        if root_unit_id and root_unit_id not in units:raise ValueError('unknown stored root unit')
        def within(uid):
            if not root_unit_id:return True
            while uid is not None:
                if uid==root_unit_id:return True
                uid=units[uid]['parent']
            return False
        def depth(uid):
            n=0
            while units[uid]['parent'] is not None:n+=1;uid=units[uid]['parent']
            return n
        rows=[]
        for uid,u in sorted(units.items(),key=lambda x:(x[1].get('span',[0])[0],int(x[0]))):
            if not within(uid):continue
            if not include_children and u.get('family') in ('circled','dot_number:1','hangul'):continue
            rows.append({'unit_id':uid,'parent_id':u['parent'],'depth':depth(uid),'family':u.get('family'),'surface':u.get('surface'),'title':u.get('title'),'coordinate_key':u.get('coordinate_key'),'coordinate_scope':u.get('coordinate_scope'),'span':u.get('span')})
        return {'document_id':did,'document_name':self.m.documents[did],'items':rows[offset:offset+limit],'total':len(rows),'offset':offset,'next_offset':offset+limit if offset+limit<len(rows) else None,'authority':'stored source_unit hierarchy; generated outline, not a printed table of contents','content_read':False}
    def read_unit(self,authorized,*,context,document_id='',unit_id):
        did=self.document(authorized,context,document_id);u=self.m.units.get((did,str(unit_id)))
        if u is None:raise ValueError('unknown stored unit')
        span=u.get('span')
        if not isinstance(span,list) or len(span)!=2 or not all(type(x)==int for x in span) or span[0]>=span[1]:raise ValueError('missing structural block span')
        sources=[self.m.tools.sources[s] for s in self.m._unit_sources(did,str(unit_id)) if s in self.m.sources and self.m.sources[s]['document_id']==did]
        selected=[]
        for s in sources:
            blocks=[b for b in s['blocks'] if span[0]<=int(b['block_id'])<span[1]]
            if blocks:selected.append((s,blocks))
        if len(selected)!=1:raise ValueError('structure does not resolve to one source article')
        s,blocks=selected[0];found={int(b['block_id']) for b in blocks}
        if found!=set(range(*span)):raise ValueError('structural span not fully represented by original source blocks')
        text='\n'.join(b['text'] for b in blocks)
        return {'document_id':did,'document_name':self.m.documents[did],'unit_id':str(unit_id),'source_id':s['id'],'coordinate_key':u.get('coordinate_key'),'coordinate_scope':u.get('coordinate_scope'),'blocks':deepcopy(blocks),'text':text,'segment_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_artifact_sha256':s['source_artifact_sha256'],'binding':self.binding,'read_extent':'exact stored node span, including its descendants','content_read':True}

def request(question):
    """Conservative metadata intent parser; explicit filters, never a hidden body fallback."""
    q=normalized(question)
    category='internal' if '내규' in q or '내부문서' in q else 'external' if '외부문서' in q else 'all'
    provider=next((x for x in PUBLIC_PROVIDERS if re.search(r'(?<![A-Za-z])'+x+r'(?![A-Za-z])',question,re.I)), '')
    if '금융투자협회' in question:provider='kofia'
    listing=any(w in q for w in ('전체목록','문서목록','내규목록','어떤문서','어떤게있','어떤것이있','뭐가있','문서들','문서리스트')) or ('db' in q and '문서' in q and '알려' in q)
    if not listing:return None
    if any(w in q for w in ('지급기준','지급조건','승인요건','해석해','적용해','내용을')):return None
    title='';m=re.search(r'(?:중에서|중에|중)\s*(.+?)\s*관련(?:한|된)?',question)
    if m:title=m.group(1).strip()
    else:
        m=re.search(r'([^\s]+)\s*관련(?:한|된)?',question)
        if m:title=m.group(1)
    if not title:
        m=re.search(r'["“](.+?)["”]',question)
        if m:title=m.group(1)
    if not title:
        # Explicit topic directly followed by 문서들/문서 목록.
        m=re.search(r'([^\s]+)\s+문서(?:들|\s*목록)',question)
        if m and m.group(1) not in ('외부','내부','전체','있는','보유한'):title=m.group(1)
    return dict(category=category,provider=provider,title_query=title)

def search_structure(navigator,authorized,*,context,document_id='',root_unit_id,query,field='structure_title',offset=0,limit=100):
    """Explicit subtree search. Body mode only scans blocks inside stored node span."""
    if field not in ('structure_title','body'):raise ValueError('explicit structure_title or body field required')
    if not query or len(query)>500:raise ValueError('bounded query required')
    if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=500:raise ValueError('invalid pagination')
    did=navigator.document(authorized,context,document_id);units=navigator.m.units
    root=units.get((did,str(root_unit_id)))
    if root is None:raise ValueError('stored root required; no global search fallback')
    start,end=root['span'];q=normalized(query);hits=[]
    if field=='structure_title':
        for (d,uid),u in units.items():
            if d!=did or not(start<=u['span'][0] and u['span'][1]<=end):continue
            if q in normalized(u.get('title') or ''):hits.append({'unit_id':uid,'surface':u.get('surface'),'title':u.get('title'),'coordinate_key':u.get('coordinate_key')})
    else:
        # Read only the selected structural subtree, not every article in the database.
        for row in navigator.store.db.execute('SELECT block_id,unit_id,text FROM source_block WHERE document_id=? AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<? ORDER BY CAST(block_id AS INTEGER)',(did,start,end)):
            if q in normalized(row['text']):hits.append({'block_id':row['block_id'],'unit_id':row['unit_id'],'document_id':did})
    hits.sort(key=lambda x:int(x.get('block_id',x.get('unit_id'))))
    return {'items':hits[offset:offset+limit],'total':len(hits),'next_offset':offset+limit if offset+limit<len(hits) else None,'field':field,'document_id':did,'root_unit_id':str(root_unit_id),'span':[start,end],'content_read':False,'search_mode':'literal normalized within stored subtree only'}
