"""Versioned term/source navigation index; source content remains immutable."""
import argparse
from collections import defaultdict
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from .contracts import sha, write, digest
from .term_tools import TermTools, freeze_label_trie
from . import term_tools as term_tools_module
from . import observability as obs

log = obs.get_logger('index')

ARTICLE = re.compile(r'제\d+(?:-\d+)?조(?:의\d+)?')
_SERVING_CACHE = {}
_SERVING_CACHE_LOCK = threading.Lock()


def cached_serving_index(path, store, *, expected_manifest_sha256=None):
    """Verify each immutable navigation SQLite once per process and file state.

    Request-local IndexTools still opens its own read-only SQLite connection. The
    manifest and file stat are checked on every request; a changed file is rehashed.
    Deployment E2E and verify_assets continue to call TermIndex directly.
    """
    path = Path(path).resolve()
    manifest = path / 'manifest.json'
    sqlite = path / 'navigation.sqlite'
    def signature(file):
        stat = file.stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    source_binding = digest({k: v for k, v in store.manifest.items()
                             if k not in {'navigation', 'fulltext', 'fulltext_derivation'}})
    key = (str(path), signature(manifest), signature(sqlite),
           store.manifest['store_sha256'], source_binding, expected_manifest_sha256,
           getattr(getattr(store, 'selection', None), 'fingerprint', None),
           getattr(getattr(store, 'selection', None), 'state', None))
    if hasattr(store, 'check_unchanged'): store.check_unchanged()
    with _SERVING_CACHE_LOCK:
        cached = _SERVING_CACHE.get(key)
        if cached is None:
            if expected_manifest_sha256 is not None and sha(manifest) != expected_manifest_sha256:
                raise ValueError('term index manifest mismatch')
            cached = TermIndex(path, store)
            if key[1:3] != (signature(manifest), signature(sqlite)):
                raise ValueError('term index changed during verification')
            _SERVING_CACHE.clear()
            _SERVING_CACHE[key] = cached
        return cached

def ro(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,check_same_thread=False)
    db.row_factory=sqlite3.Row
    return db

def text_sha(text):return hashlib.sha256(text.encode()).hexdigest()

def compile_index(store, legal, dictionary, output, *, glossary=None, linkage_report=None, knowledge=None,
                  reference_scope_v2=False, audit_output=None, storage_profile='legacy', audit_profile='materialized'):
    """Explicit selected stores only; no experiment products, mocks, or model calls."""
    progress = globals().get('_BUILD_PROGRESS', lambda **kw: None)
    phase_started = time.monotonic()
    phase_cpu = time.thread_time()
    def phase(name):
        nonlocal phase_started, phase_cpu
        now, cpu = time.monotonic(), time.thread_time()
        print(f'NAVIGATION {name} elapsed={now-phase_started:.3f}s thread_cpu={cpu-phase_cpu:.3f}s', flush=True)
        phase_started, phase_cpu = now, cpu
        progress(task=name, completed=0, total=None, unit='checks')
    phase('schema.start')
    output=Path(output)
    compact_v2 = storage_profile == 'compact-v2'
    if audit_profile not in {'materialized', 'factorized-v1'} or (audit_profile != 'materialized' and not compact_v2):
        raise ValueError('factorized audit requires compact-v2')
    if compact_v2:
        from . import navigation_build as nb
        from .reference_build import shared_reference_schema
        from .term_references import load_reference_inputs
        aliases,delegations,reference_inputs=load_reference_inputs()
        identity={'source':store.manifest,'legal':sha(legal),'dictionary':sha(dictionary),
                  'glossary':sha(glossary) if glossary else None,
                  'report':linkage_report if isinstance(linkage_report,dict) else sha(linkage_report) if linkage_report else None,
                  'knowledge':sha(Path(knowledge)/'manifest.json') if knowledge else None,
                  'scope_v2':reference_scope_v2,'reference_inputs':reference_inputs,'audit_profile':audit_profile,
                  'code':{n:sha(Path(__file__).with_name(n)) for n in
                    ('term_index.py','term_links.py','reference_build.py','navigation_build.py','factorized_audit.py','term_references.py','term_references_legacy.py','term_tools.py')}}
        if audit_output is None or glossary is None:raise ValueError('compact-v2 requires explicit glossary and audit')
        if (output/'manifest.json').exists():
            if json.loads((output/'build-identity.json').read_text())!=identity:raise ValueError('navigation resume identity changed')
            value=json.loads((output/'manifest.json').read_text())
            if sha(output/'navigation.sqlite')!=value['index_sha256']:raise ValueError('completed navigation drift')
            from .navigation_storage import verify_audit
            verify_audit(audit_output,expected_manifest_sha256=value['storage']['audit_manifest_sha256'],expected_index_sha256=value['index_sha256'])
            return value
        db=nb.open_build(output,audit_output,identity)
        initialized=nb.get(db,'initialized') is not None
    else:
        if output.exists():raise ValueError('immutable term index already exists')
        output.mkdir(parents=True)
        db=sqlite3.connect(output/'navigation.sqlite');db.row_factory=sqlite3.Row
        initialized=False
    dc=projector=None
    try:
        if not initialized:
            db.executescript('''
              CREATE TABLE term(id TEXT PRIMARY KEY,json TEXT);
              CREATE TABLE edge(id TEXT PRIMARY KEY,json TEXT);
              CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
              CREATE INDEX source_document ON source(document_id);
              CREATE TABLE occurrence(term_id TEXT,source_id TEXT,PRIMARY KEY(term_id,source_id));
              CREATE INDEX occurrence_source ON occurrence(source_id);
              CREATE TABLE definition(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
              CREATE INDEX definition_document ON definition(document_id);
              CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
              CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));
              CREATE TABLE reference_target(reference_id TEXT,ordinal INTEGER,source_id TEXT,unit_id TEXT,
                unit_path TEXT,block_ids TEXT,target_level TEXT,PRIMARY KEY(reference_id,ordinal));
              CREATE INDEX reference_target_source ON reference_target(source_id,reference_id);
              CREATE TABLE reference_candidate(reference_id TEXT,candidate_id TEXT,ordinal INTEGER,source_id TEXT,unit_id TEXT,
                unit_path TEXT,block_ids TEXT,target_level TEXT,basis TEXT,json TEXT,
                PRIMARY KEY(reference_id,candidate_id));
              CREATE TABLE reference_candidate_end(source_id TEXT,reference_id TEXT,candidate_id TEXT,
                PRIMARY KEY(source_id,reference_id,candidate_id));
              CREATE TABLE source_unit_map(source_id TEXT,unit_id TEXT,parent_id TEXT,ordinal TEXT,surface TEXT,block_ids TEXT,family TEXT,PRIMARY KEY(source_id,unit_id));
              CREATE TABLE document_frame(document_id TEXT PRIMARY KEY,json TEXT);
            ''')
            if reference_scope_v2:
                db.execute('CREATE TABLE structure_anchor(source_id TEXT,unit_id TEXT,json TEXT,PRIMARY KEY(source_id,unit_id))')
            if compact_v2:
                shared_reference_schema(db)
                nb.occurrence_schema(db)
        lg=ro(legal);terms=[]
        columns={r['name'] for r in lg.execute('PRAGMA table_info(entry)')}
        query=("SELECT id,label,homonym FROM entry WHERE id LIKE 'moleg:knowledge_terms:%' AND length(label)>=2 ORDER BY id"
               if 'homonym' in columns else "SELECT id,label,NULL AS homonym FROM entry WHERE length(label)>=2 ORDER BY id")
        if 'source' in columns:
            query=query.replace(' ORDER BY id', " AND source!='corpus_definition' ORDER BY id")
        for r in lg.execute(query):
            t={**dict(r),'status':'SOURCE_TERM_NOT_CANONICAL_MEANING'};terms.append(t)
            db.execute('INSERT OR IGNORE INTO term VALUES (?,?)',(t['id'],json.dumps(t,ensure_ascii=False)))
        if lg.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='edge'").fetchone():
            known={t['id'] for t in terms}
            for r in lg.execute("SELECT * FROM edge WHERE status='CONNECTED' ORDER BY id"):
                if r['source_id'] not in known or r['target_id'] not in known:continue
                e={'id':r['id'],'source':r['source_id'],'target':r['target_id'],'code':r['code'],'status':r['status'],'reason':r['reason']}
                db.execute('INSERT OR IGNORE INTO edge VALUES (?,?)',(e['id'],json.dumps(e,ensure_ascii=False)))
        lg.close();matcher=TermTools([],terms,[]);dc=ro(dictionary);definitions=0;references=0;unresolved=0;rejected_defs=0;docs=0
        phase('catalogue.start')
        projector=None
        if glossary is not None or linkage_report is not None or knowledge is not None:
            if glossary is None or linkage_report is None:raise ValueError('glossary and linkage report must be explicit together')
            from .term_links import LinkProjector,normalized
            projector=LinkProjector(db,store,dictionary,glossary,linkage_report,knowledge,direct_audit=compact_v2,audit_profile=audit_profile)
        if compact_v2 and not initialized:
            nb.put(db,'initialized',True);db.commit()
        phase('documents.start')
        documents=store.db.execute('SELECT document_id,name,source_artifact_sha256 FROM document ORDER BY document_id').fetchall()
        progress(task='document-navigation', completed=0, total=len(documents), unit='documents')
        for doc in documents:
            did=doc['document_id']
            if compact_v2:
                completed=nb.get(db,'document',did)
                if completed is not None:
                    docs+=1;rejected_defs+=completed['rejected'];continue
            rejected_before=rejected_defs
            units={r['unit_id']:dict(r)|{'value':json.loads(r['json'])} for r in store.db.execute('SELECT * FROM source_unit WHERE document_id=?',(did,))}
            @lru_cache(None)
            def root(uid):
                current=uid;seen=set();chosen=None
                while current in units:
                    if current in seen:raise ValueError('source ancestor cycle')
                    seen.add(current);u=units[current]
                    if u['value'].get('family') in ['kr_article','kr_조']:chosen=current
                    current=str(u['parent_id']) if u['parent_id'] is not None else None
                return chosen or uid
            groups=defaultdict(list);block_sources={};original_blocks={}
            for b in store.db.execute('SELECT block_id,unit_id,text,source_artifact_sha256 FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,)):
                original_blocks[str(b['block_id'])]=dict(b)
                uid=root(b['unit_id']) if b['unit_id'] is not None else 'block:'+b['block_id']
                groups[uid].append({'block_id':b['block_id'],'text':b['text']})
            byid={};heads=defaultdict(list)
            for uid,blocks in groups.items():
                sid='article:'+text_sha(did+'|'+str(uid))[:24];u=units.get(uid,{}).get('value',{});surface=u.get('surface','');title=u.get('title','');heading=(surface+' '+title).strip() or blocks[0]['text'].split('\n')[0][:160]
                # Some formats embed the article label in title rather than surface.
                match=ARTICLE.match(heading);article=match.group() if match else None
                text='\n'.join(b['text'] for b in blocks)
                s={'id':sid,'document_id':did,'document_name':doc['name'],'unit_id':uid if uid in units else None,'block_id':blocks[0]['block_id'],'heading':heading,'article_coordinate':{'doc_id':did,'node':uid},'source_artifact_sha256':doc['source_artifact_sha256'],'blocks':blocks,'text':text,'text_sha256':text_sha(text)}
                byid[sid]=s
                if article:heads[article].append(sid)
                for b in blocks:block_sources[b['block_id']]=sid
                db.execute('INSERT INTO source VALUES (?,?,?,?)',(sid,did,article,json.dumps(s,ensure_ascii=False)))
                db.executemany('INSERT INTO occurrence VALUES (?,?)',[(t,sid) for t in matcher.match(text)])
                if projector:db.execute('INSERT INTO source_literal VALUES (?,?,?)',(sid,did,normalized(text)))
            # 조 안의 항·호·목 마디 — 인용 `제4조제1항` 을 그 조의 실제 첫 하위 마디로 잇는다.
            # 마커 모양(①·1)·(1))이 아니라 구조 위치와 서수로 찾으므로 틀이 달라도 같다.
            blocks_of=defaultdict(list)
            for bid,b in original_blocks.items():
                if b['unit_id'] is not None:blocks_of[str(b['unit_id'])].append(bid)
            for uid,u in units.items():
                top=root(uid)
                if top not in groups:continue
                sid='article:'+text_sha(did+'|'+str(top))[:24]
                if reference_scope_v2:
                    path=[];cursor=str(uid);visited=set()
                    while cursor in units:
                        if cursor in visited:raise ValueError('anchor cycle')
                        visited.add(cursor);path.append(cursor);cursor=str(units[cursor]['parent_id'])
                    anchor={**u['value'],'unit_id':str(uid),'parent_id':str(u['parent_id']) if u['parent_id'] is not None else None,
                            'unit_ids':list(reversed(path)),'document_id':did,
                            'source_artifact_sha256':doc['source_artifact_sha256']}
                    db.execute('INSERT INTO structure_anchor VALUES (?,?,?)',(sid,str(uid),json.dumps(anchor,ensure_ascii=False)))
                if top==uid:continue
                db.execute('INSERT OR IGNORE INTO source_unit_map VALUES (?,?,?,?,?,?,?)',(sid,str(uid),str(u['parent_id']) if u['parent_id'] is not None else None,
                           json.dumps(u['value'].get('ordinal')),u['value'].get('surface') or '',
                           json.dumps(sorted({p['block_id'] for p in u['value'].get('own_spans',[])} or set(blocks_of.get(str(uid),[])))),
                           u['value'].get('family')))
            # 구조화가 이 문서에 세운 계층 틀. 인용 해석이 문서마다 이 틀로 항·호·목 역할을 정한다.
            doc_json=json.loads(store.db.execute('SELECT json FROM document WHERE document_id=?',(did,)).fetchone()[0] or '{}')
            from .term_references import frame_roles,frame_roles_v2
            roles=frame_roles_v2 if reference_scope_v2 else frame_roles
            db.execute('INSERT OR REPLACE INTO document_frame VALUES (?,?)',(did,json.dumps(roles(doc_json.get('ladder')),ensure_ascii=False)))
            if projector:projector.document(did,original_blocks,block_sources)
            for row in dc.execute('SELECT * FROM corpus_definition WHERE document_id=?',(did,)):
                d=dict(row);sid=block_sources.get(d['block_id']);s=byid.get(sid)
                if not s or not any(b['block_id']==d['block_id'] and b['text']==d['source_text'] for b in s['blocks']) or text_sha(d['source_text'])!=d['source_text_sha256']:
                    rejected_defs+=1;continue
                tids=matcher.labels.get(d['key'],[])
                if projector:tids=sorted(set(tids)|{r[0] for r in db.execute('SELECT term_id FROM term_surface WHERE key=?',(d['key'],))})
                d.update(term_ids=tids,source_id=sid,document_name=doc['name'],source_artifact_sha256=s['source_artifact_sha256'],origin='existing_corpus_definition',match_kind='LABEL_CANDIDATE',verification='EXACT_BLOCK_AND_HASH')
                for k in ['scope_hint','location','reference_hints']:d[k]=json.loads(d[k])
                db.execute('INSERT INTO definition VALUES (?,?,?)',(d['id'],did,json.dumps(d,ensure_ascii=False)));definitions+=1
            docs+=1
            # Unpublished stage is restartable; batch durable writes on NFS.
            if compact_v2:nb.put(db,'document',{'rejected':rejected_defs-rejected_before},did)
            if storage_profile not in {'compact-v1','compact-v2'} or docs % 64 == 0: db.commit()
            progress(task='document-navigation', completed=docs, total=len(documents), unit='documents')
            if docs%20==0:print('Indexed documents',docs,flush=True)
        db.commit()
        phase('references.start')
        from .term_references import compile_references,load_reference_inputs
        aliases,delegations,reference_inputs=load_reference_inputs()
        completed=nb.get(db,'references') if compact_v2 else None
        if completed is None:
            references,unresolved=compile_references(db,aliases,delegations)
            if compact_v2:nb.put(db,'references',[references,unresolved]);db.commit()
        else:references,unresolved=completed
        phase('reference-witnesses.start')
        # Witness ambiguity is immutable within a generation. Materialize it once
        # while building instead of decoding every source's references per request.
        if compact_v2:
            if nb.get(db,'witnesses') is None:
                db.execute('BEGIN')
                db.execute('CREATE TABLE reference_witness_count(source_id TEXT NOT NULL,block_id TEXT NOT NULL,source_text_sha256 TEXT NOT NULL,n INTEGER NOT NULL,PRIMARY KEY(source_id,block_id,source_text_sha256))')
                db.execute("INSERT INTO reference_witness_count SELECT json_extract(json,'$.source_id'),json_extract(json,'$.block_id'),json_extract(json,'$.source_text_sha256'),count(*) FROM reference_payload WHERE json_extract(json,'$.source_text_sha256') IS NOT NULL GROUP BY 1,2,3")
                nb.put(db,'witnesses',True);db.commit()
            phase('glossary-evidence.start')
            linkage=nb.get(db,'evidence')
            if linkage is None:
                db.execute('BEGIN')
                linkage=projector.finish()
                nb.put(db,'evidence',linkage);db.commit()
            projector.close();dc.close()
        else:
            db.executescript('''
              CREATE TABLE reference_witness_count(
                source_id TEXT NOT NULL,block_id TEXT NOT NULL,
                source_text_sha256 TEXT NOT NULL,n INTEGER NOT NULL,
                PRIMARY KEY(source_id,block_id,source_text_sha256));
              INSERT INTO reference_witness_count
              SELECT json_extract(json,'$.source_id'),json_extract(json,'$.block_id'),
                     json_extract(json,'$.source_text_sha256'),count(*)
              FROM reference
              WHERE json_extract(json,'$.source_text_sha256') IS NOT NULL
              GROUP BY 1,2,3;
            ''')
            phase('glossary-evidence.start')
            dc.close();linkage=None
            if projector:
                try:linkage=projector.finish()
                finally:projector.close()
        phase('statistics-integrity.start')
        if not compact_v2 or nb.get(db,'statistics') is None:
            if compact_v2:db.execute('BEGIN')
            db.execute('CREATE TABLE term_stats AS SELECT term_id,count(*) AS n FROM occurrence GROUP BY term_id');db.execute('CREATE UNIQUE INDEX term_stats_id ON term_stats(term_id)')
            if compact_v2:nb.put(db,'statistics',True)
            db.commit()
        counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['term','edge','source','occurrence','definition','reference']}
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
        phase('audit-separation.start')
        storage=None
        if compact_v2:
            storage=nb.finish_audit(output/'navigation.sqlite',audit_output,audit_profile=audit_profile)
        elif audit_output is not None:
            from .navigation_storage import separate_navigation
            storage=separate_navigation(output/'navigation.sqlite', audit_output, compact=storage_profile=='compact-v1')
        manifest={'schema_version':'term-navigation-index-v7' if compact_v2 else 'term-navigation-index-v6' if storage_profile=='compact-v1' else 'term-navigation-index-v5' if reference_scope_v2 else 'term-navigation-index-v4','generation_id':store.manifest['generation_id'],'source_store_sha256':store.manifest['store_sha256'],'source_manifest_sha256':digest({k:v for k,v in store.manifest.items() if k not in {'navigation','fulltext','fulltext_derivation'}}),'legal_sha256':sha(legal),'dictionary_sha256':sha(dictionary),'index_sha256':sha(output/'navigation.sqlite'),'counts':counts,'document_count':docs,'rejected_definitions':rejected_defs,'unresolved_references':unresolved,'reference_inputs_sha256':reference_inputs,'quality_certified':False,'compiler_sha256':sha(__file__),'term_tools_sha256':sha(term_tools_module.__file__)}
        if reference_scope_v2:manifest['scope_contract']='reference-scope-v2'
        if linkage:manifest.update(linkage=linkage)
        if storage:manifest['storage']=storage
        write(output/'manifest.json',manifest)
        phase('done')
        return manifest
    finally:
        if dc is not None:dc.close()
        if projector is not None:projector.close()
        db.close()

class SourceMap(Mapping):
    def __init__(self,db,table='source'):
        self.db=db;self.table=table;self.cache={};self._load_metrics=None

    def ids_for_documents(self, document_ids):
        """ACL metadata only: do not decode every source body to find its owner."""
        from . import query_latency as latency
        ids = sorted(set(document_ids))
        if not ids: return frozenset()
        rows = latency.rows(self.db,
            'SELECT id FROM source WHERE document_id IN (SELECT value FROM json_each(?))',
            [json.dumps(ids)], 'scope_source_ids')
        return frozenset(row[0] for row in rows)

    @contextmanager
    def measure_loads(self):
        """Aggregate only the caller's location/preview reads; no per-source logs."""
        previous=self._load_metrics
        metrics={'source_lookup_count':0,'source_cache_hits':0,'source_sql_count':0,
                 'source_sql_execute_ms':0.0,'source_sql_fetch_ms':0.0,
                 'source_sql_cpu_ms':0.0,'source_json_decode_ms':0.0,
                 'source_json_cpu_ms':0.0,'source_json_chars':0,
                 'source_sql_max_ms':0.0,'source_load_errors':0}
        self._load_metrics=metrics
        try:yield metrics
        finally:self._load_metrics=previous

    def __getitem__(self,key):
        metrics=self._load_metrics
        if metrics is not None:
            metrics['source_lookup_count']+=1
            if key in self.cache:metrics['source_cache_hits']+=1
        if key not in self.cache and metrics is None:
            r=self.db.execute('SELECT json FROM source WHERE id=?',(key,)).fetchone()
            if r is None:raise KeyError(key)
            self.cache[key]=json.loads(r[0])
        elif key not in self.cache:
            metrics['source_sql_count']+=1
            cursor=None;started=time.perf_counter();cpu=time.thread_time()
            try:
                t=time.perf_counter()
                try:cursor=self.db.execute('SELECT json FROM source WHERE id=?',(key,))
                finally:metrics['source_sql_execute_ms']+=(time.perf_counter()-t)*1000
                t=time.perf_counter()
                try:r=cursor.fetchone()
                finally:metrics['source_sql_fetch_ms']+=(time.perf_counter()-t)*1000
            except BaseException:
                metrics['source_load_errors']+=1;raise
            finally:
                metrics['source_sql_cpu_ms']+=(time.thread_time()-cpu)*1000
                metrics['source_sql_max_ms']=max(metrics['source_sql_max_ms'],(time.perf_counter()-started)*1000)
                if cursor is not None:cursor.close()
            if r is None:
                metrics['source_load_errors']+=1;raise KeyError(key)
            metrics['source_json_chars']+=len(r[0])
            t=time.perf_counter();cpu=time.thread_time()
            try:self.cache[key]=json.loads(r[0])
            except BaseException:
                metrics['source_load_errors']+=1;raise
            finally:
                metrics['source_json_decode_ms']+=(time.perf_counter()-t)*1000
                metrics['source_json_cpu_ms']+=(time.thread_time()-cpu)*1000
        return self.cache[key]
    def __iter__(self):return (r[0] for r in self.db.execute('SELECT id FROM source'))
    def __len__(self):return self.db.execute('SELECT count(*) FROM source').fetchone()[0]

class OccurrenceMap:
    def __init__(self,db):self.db=db
    def __getitem__(self,key):return {r[0] for r in self.db.execute('SELECT term_id FROM occurrence WHERE source_id=?',(key,))}


class _CopyOnRead(Mapping):
    """Expose cached catalogue values without sharing mutable request state."""
    def __init__(self, values):
        self._values=values
    def __getitem__(self, key):
        return deepcopy(self._values[key])
    def __iter__(self):
        return iter(self._values)
    def __len__(self):
        return len(self._values)

def definition_summary(identifier, value):
    """Small immutable query fields; large source text/term arrays stay lazy."""
    from .term_links import normalized
    key = value.get('key', '')
    return (identifier, value.get('source_id'), key, normalized(key), value.get('scope_status'))


class IndexTools(TermTools):
    def __init__(self,db,terms,relations,scope,*,catalog=None,definition_rows=None,definition_summaries=None):
        if catalog is None:
            with obs.step(log, 'tools.catalog'):
                super().__init__([],terms,relations)
                self._load_catalog(db)
        else:
            # Independent mutable views: no request can alter a later request's
            # terms, edges, or definitions through returned navigation cards.
            with obs.step(log, 'tools.copy'):
                self.__dict__.update(catalog)
            self.references={}
        self.db=db;self.scope=set(scope);self.sources=SourceMap(db);self.source_terms=OccurrenceMap(db)
        if catalog is None:
            self.has_reference_witness_count=bool(db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reference_witness_count'").fetchone())
        with obs.step(log, 'tools.definitions'):
            if definition_rows is None:
                rows = (db.execute('SELECT id,json FROM definition WHERE document_id IN ('+','.join('?' for _ in scope)+')',scope) if scope else ())
                self.definitions={row[0]:json.loads(row[1]) for row in rows}
            else:
                scoped={}
                for did in dict.fromkeys(scope):
                    scoped.update(definition_rows.get(did, {}))
                self.definitions=_CopyOnRead(scoped)
            if definition_summaries is None:
                self.definition_summaries = tuple(definition_summary(k, v) for k, v in sorted(self.definitions.items()))
            else:
                self.definition_summaries = tuple(sorted(
                    row for did in dict.fromkeys(scope) for row in definition_summaries.get(did, ())))

    def _load_catalog(self,db):
        with obs.step(log, 'tools.stats'):
            self.df={r[0]:r[1] for r in db.execute('SELECT term_id,n FROM term_stats')}
        with obs.step(log, 'tools.documents'):
            self.document_ids={r[0] for r in db.execute('SELECT DISTINCT document_id FROM source')}
            self.has_literal=bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='source_literal'").fetchone())
        with obs.step(log, 'tools.surfaces'):
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='term_surface'").fetchone():
                # Deduplicate in memory: DISTINCT may sort a large NFS table in
                # SQLite, and list membership grows quadratically for homonyms.
                seen={label:set(ids) for label,ids in self.labels.items()}
                for tid,key,value in db.execute('SELECT term_id,key,text FROM term_surface'):
                    for label in dict.fromkeys((key,value)):
                        ids=seen.setdefault(label,set())
                        if tid not in ids:
                            ids.add(tid);self.labels[label].append(tid)
                self.prefix=defaultdict(list)
                for label in self.labels:self.prefix[label[:2]].append(label)
                for prefix in self.prefix:self.prefix[prefix].sort(key=lambda value:(-len(value),value))
                self._rebuild_label_trie()
    def validate_scope(self,scope):
        if not scope or not set(scope)<=self.scope or not set(scope)<=self.document_ids:raise ValueError('invalid source scope')
        return list(dict.fromkeys(scope))
    def search_labels(self,labels,scope,limit=3,exclude_ids=()):
        from .term_links import normalized
        scope=self.validate_scope(scope)
        labels=list(dict.fromkeys(normalized(x) for x in labels if 2<=len(normalized(x))<=80))[:8]
        if not labels:return []
        if type(limit) is not int or not 1<=limit<=8:raise ValueError('invalid source result limit')
        if not self.has_literal:
            # Older v2 remains readable; normalize each row lazily, without a second corpus in memory.
            self.db.create_function('normalize_source',1,normalized,deterministic=True)
            table="(SELECT id,document_id,normalize_source(json_extract(json,'$.text')) AS text FROM source)"
        else:table='source_literal'
        excluded=tuple(exclude_ids);exsql=' AND id NOT IN ('+','.join('?' for _ in excluded)+')' if excluded else ''
        scores='+'.join('(instr(text,?)>0)' for _ in labels)
        sql='SELECT id,text,('+scores+') AS score FROM '+table+' WHERE document_id IN ('+','.join('?' for _ in scope)+') AND ('+' OR '.join('instr(text,?)>0' for _ in labels)+')'+exsql+' ORDER BY score DESC,id LIMIT ?'
        request_deadline=getattr(self,'request_deadline',None)
        deadline=min(time.monotonic()+3,request_deadline) if request_deadline is not None else time.monotonic()+3
        self.db.set_progress_handler(lambda:int(time.monotonic()>deadline),10000)
        try:rows=self.db.execute(sql,(*labels,*scope,*labels,*excluded,limit)).fetchall()
        finally:
            if request_deadline is None:
                self.db.set_progress_handler(None,0)
            else:
                self.db.set_progress_handler(lambda:int(time.monotonic()>=request_deadline),1000)
        return [{'id':r['id'],'score':r['score'],'matched_labels':[x for x in labels if x in r['text']]} for r in rows]
    def search(self,term_ids,scope,limit=3,exclude_ids=()):
        import math
        if not set(scope)<=self.scope or not set(term_ids)<=self.terms.keys():raise ValueError('term search scope/ID mismatch')
        if not term_ids or not scope:return []
        marks=lambda xs:','.join('?' for _ in xs)
        sql='SELECT o.source_id,o.term_id FROM occurrence o JOIN source s ON s.id=o.source_id WHERE o.term_id IN ('+marks(term_ids)+') AND s.document_id IN ('+marks(scope)+')'
        ranked={};excluded=set(exclude_ids);total=len(self.sources)
        for sid,tid in self.db.execute(sql,list(term_ids)+list(scope)):
            if sid in excluded:continue
            row=ranked.setdefault(sid,{'id':sid,'score':0,'matched_term_ids':[]});row['matched_term_ids'].append(tid);row['score']+=math.log((total+1)/(self.df.get(tid,0)+1))+1
        return sorted(ranked.values(),key=lambda x:(-x['score'],x['id']))[:limit]
    def navigation_menu(self,seen,searched,question,scope,*args,**kwargs):
        if not set(scope)<=self.scope:raise ValueError('navigation scope mismatch')
        if seen:
            query='SELECT DISTINCT r.id,r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id IN ('+','.join('?' for _ in seen)+')'
            self.references.update({r[0]:json.loads(r[1]) for r in self.db.execute(query,seen)})
        return super().navigation_menu(seen,searched,question,scope,*args,**kwargs)

class TermIndex:
    def __init__(self,path,store):
        self.selection = getattr(store, 'selection', None)
        path=Path(path);self.manifest=json.loads((path/'manifest.json').read_text())
        m=self.manifest
        if m.get('schema_version') not in {'term-navigation-index-v2','term-navigation-index-v3','term-navigation-index-v4','term-navigation-index-v5','term-navigation-index-v6','term-navigation-index-v7'}:raise ValueError('unsupported term index schema')
        if m['source_store_sha256']!=store.manifest['store_sha256'] or m['source_manifest_sha256']!=digest({k:v for k,v in store.manifest.items() if k not in {'navigation','fulltext','fulltext_derivation'}}) or m['index_sha256']!=sha(path/'navigation.sqlite'):raise ValueError('term index generation/hash mismatch')
        self.path=path;self._cache_signature=self.cache_signature();db=self.resident_connect();self.terms=[json.loads(r[0]) for r in db.execute('SELECT json FROM term')];self.relations=[json.loads(r[0]) for r in db.execute('SELECT json FROM edge')];db.close()
        self._tools_lock=threading.Lock()
        self._tool_catalog=None
        self._definition_rows=None
        self._definition_summaries=None

    def resident_connect(self):
        from .resident_data import POOL
        self.cache_binding()
        db=POOL.connect(self.path/'navigation.sqlite', expected=self.manifest['index_sha256'])
        db.row_factory=sqlite3.Row
        try:
            if self.selection is not None: self.selection.bind(db, navigation=True)
        except BaseException:
            db.close()
            raise
        return db

    def cache_signature(self):
        files=(self.path/'manifest.json', self.path/'navigation.sqlite')
        if any(p.is_symlink() or Path(str(p)+'-wal').exists() for p in files):
            raise ValueError('unbound navigation cache file')
        return tuple((p.stat().st_dev,p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns)
                     for p in files)

    def cache_binding(self):
        if self.selection is not None: self.selection.check_unchanged()
        if self.cache_signature()!=self._cache_signature:
            raise ValueError('navigation changed; reopen and verify')
        return (str(self.path.resolve()), self._cache_signature, self.manifest['generation_id'],
                self.manifest['source_store_sha256'], self.manifest['index_sha256'],
                self.selection.fingerprint if self.selection is not None else None)

    def tools(self,scope):
        if self.selection is not None:
            self.selection.check_unchanged()
            if set(scope) & self.selection.excluded:
                raise ValueError('search scope contains excluded document versions')
        # This cache belongs to the verified TermIndex, so generation/file-state
        # invalidation of cached_serving_index also invalidates these data.
        with self._tools_lock:
            if self._tool_catalog is None:
                db=self.resident_connect()
                try:
                    template=IndexTools(db,self.terms,self.relations,[])
                    with obs.step(log, 'tools.definition_catalog'):
                        definitions=defaultdict(list)
                        for did,identifier,raw in db.execute('SELECT document_id,id,json FROM definition'):
                            definitions[did].append((identifier,json.loads(raw)))
                    catalog={name:_CopyOnRead(getattr(template,name)) for name in (
                        'terms','labels','prefix','edges')}
                    catalog['_label_trie']=freeze_label_trie(template._label_trie)
                    catalog['df']=_CopyOnRead(template.df)
                    catalog['document_ids']=frozenset(template.document_ids)
                    catalog['has_literal']=template.has_literal
                    catalog['has_reference_witness_count']=template.has_reference_witness_count
                    self._definition_rows={did:dict(rows) for did,rows in definitions.items()}
                    self._definition_summaries={did:tuple(definition_summary(k, v) for k, v in rows.items())
                                                for did, rows in self._definition_rows.items()}
                    self._tool_catalog=catalog
                    obs.event(log,'tools.cache.ready',path=str(self.path))
                finally:
                    db.close()
            else:
                obs.event(log,'tools.cache.hit',path=str(self.path))
        db=self.resident_connect()
        try:
            result=IndexTools(db,(),(),list(scope),catalog=self._tool_catalog,
                              definition_rows=self._definition_rows,definition_summaries=self._definition_summaries)
            result.sources.cache_binding=self.cache_binding
            return result
        except BaseException:
            db.close()
            raise

def main():
    from .storage import Store
    p=argparse.ArgumentParser();p.add_argument('--generation',required=True,type=Path);p.add_argument('--legal',required=True,type=Path);p.add_argument('--dictionary',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--glossary',type=Path);p.add_argument('--linkage-report',type=Path);p.add_argument('--knowledge',type=Path)
    a=p.parse_args();store=Store(a.generation)
    try:print(json.dumps(compile_index(store,a.legal,a.dictionary,a.output,glossary=a.glossary,
        linkage_report=a.linkage_report,knowledge=a.knowledge),ensure_ascii=False,indent=2))
    finally:store.close()
if __name__=='__main__':main()
