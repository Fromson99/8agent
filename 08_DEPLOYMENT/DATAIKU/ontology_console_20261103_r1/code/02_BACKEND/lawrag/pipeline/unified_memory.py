from semantic_runtime.legal_agent.shortcut_store import selected_store
"""Offline case migration, catalogue compilation and wiki rebuild through pipeline.py."""
import argparse
import json
from pathlib import Path
import sqlite3
from semantic_runtime.legal_agent.corrected_memory import digest,encoded,MemoryError
from semantic_runtime.legal_agent.case_repository import CaseRepository


def migrate(source,destination,*,kind='corrected-memory'):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or destination.exists() and source.samefile(destination):raise ValueError('migration requires a separate v3 store')
    with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as legacy:
        legacy.row_factory=sqlite3.Row
        legacy.execute('BEGIN')
        if kind=='corrected-memory' and legacy.execute('PRAGMA user_version').fetchone()[0]!=2:
            raise ValueError('only explicit memory-v2 import is supported')
        tables=[r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        # Table names come from SQLite metadata, never from the caller.
        records={name:[dict(row) for row in legacy.execute('SELECT * FROM "'+name.replace('"','""')+'" ORDER BY rowid')] for name in tables}
        source_hash=digest(records);directory=destination.parent/'legacy-imports'/source_hash
        directory.mkdir(parents=True,exist_ok=True)
        backup=directory/'source.sqlite'
        if not backup.exists():
            with backup.open('xb'):pass
            with sqlite3.connect(backup) as snapshot:legacy.backup(snapshot)
            backup.chmod(0o600)
    cases=CaseRepository(destination,None,None)
    try:
        old=cases.db.execute('SELECT payload FROM import_receipt WHERE id=?',(source_hash,)).fetchone()
        if old:return json.loads(old[0])
        mapping={'sessions':{},'questions':{},'events':{},'experiences':{}}
        prefix='legacy:'+source_hash[:16]+':'
        with cases.transaction():
            cases.db.execute('CREATE TABLE IF NOT EXISTS legacy_record(source_hash TEXT,table_name TEXT,row_number INTEGER,payload TEXT,PRIMARY KEY(source_hash,table_name,row_number))')
            for name,rows in records.items():
                for index,row in enumerate(rows):cases.db.execute('INSERT INTO legacy_record VALUES(?,?,?,?)',(source_hash,name,index,encoded(row)))
            if kind=='corrected-memory':
                for s in records['session']:
                    ident=prefix+s['id'];mapping['sessions'][s['id']]=ident
                    cases.db.execute('INSERT INTO session VALUES(?,?,?)',(ident,s['owner'],s['team']))
                    cases.db.execute('INSERT INTO session_export VALUES(?,0)',(ident,))
                for g in records['goal']:
                    ident=prefix+g['id'];mapping['questions'][g['id']]=ident
                    cases.db.execute('INSERT INTO goal VALUES(?,?,?,?,?,?,?)',(ident,mapping['sessions'][g['session']],
                        g['ordinal'],g['state'],g['revision'],'PENDING','INTENT'))
                # Allocate all IDs before rewriting restoration refs, so references
                # to an earlier correction and original requests stay traceable.
                base=cases.db.execute('SELECT COALESCE(MAX(id),0) FROM event').fetchone()[0]
                for i,e in enumerate(records['event']):mapping['events'][str(e['id'])]=base+i+1
                for e in records['event']:
                    c=json.loads(e['command']) if e['command'] else None
                    if c:
                        if c.get('target') in mapping['questions']:c['target']=mapping['questions'][c['target']]
                        if c.get('restore_event') is not None:c['restore_event']=mapping['events'][str(c['restore_event'])]
                    cases.db.execute('INSERT INTO event VALUES(?,?,?,?,?,?,?,?)',(
                        mapping['events'][str(e['id'])],mapping['questions'].get(e['goal']),prefix+e['request'],
                        e['utterance'],encoded(c) if c else None,e['before_state'],e['after_state'],e['kind']))
                for k in records['knowledge']:
                    ident=prefix+k['id'];mapping['experiences'][k['id']]=ident
                    cases.db.execute('INSERT INTO knowledge VALUES(?,?,?,?,?,?,?,?)',(ident,k['owner'],k['team'],
                        mapping['questions'][k['bundle']],k['revision'],'LEGACY_UNBOUND',k['payload'],k['hash']))
            receipt={'schema_version':'unified-memory-import-v1','source_hash':source_hash,'kind':kind,
                'source_snapshot':str(backup),'table_counts':{k:len(v) for k,v in records.items()},
                'mapping':mapping,'approval':'LEGACY_UNBOUND','automatic_reuse':False}
            cases.db.execute('INSERT INTO import_receipt VALUES(?,?)',(source_hash,encoded(receipt)))
        return receipt
    finally:cases.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['migrate','status','catalogue-compile','catalogue-verify','wiki-rebuild','recall-rebuild','backup','restore','reconcile','store-plan','store-apply','store-rollback','review-import','retention-inventory','package-check','package-import','package-verify','package-retire'])
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
    p.add_argument('--runtime',type=Path);p.add_argument('--source',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--legacy-kind',choices=['corrected-memory','action-memory','v3','native','query-shortcut'],default='corrected-memory')
    p.add_argument('--generation',type=Path);p.add_argument('--principal',type=Path);p.add_argument('--binding',type=Path)
    p.add_argument('--common',action='store_true',help='operator registers the common source catalogue; no consumer user/team file')
    p.add_argument('--store-version',type=int,choices=[3,4],default=3)
    p.add_argument('--confirm-store',action='store_true')
    p.add_argument('--expected-receipt')
    p.add_argument('--artifact-manifest',type=Path)
    p.add_argument('--confirm-review',action='store_true')
    p.add_argument('--backup-manifest',type=Path,action='append',default=[])
    a=p.parse_args(argv)
    if a.common and (a.principal is not None or a.store_version!=4 or not a.command.startswith('package-')):
        p.error('--common is exclusive with --principal and only supports v4 package commands')
    from lawrag.platform.workspace import load_layout
    runtime=a.runtime or load_layout(a.root).path('runtime')/'semantic'
    path=selected_store(runtime) if a.store_version==4 else runtime/'case-memory'/'cases-v3.sqlite'
    if a.store_version==4:
        from . import shortcut_operations as ops
        from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
        principal=json.loads(a.principal.read_text()) if a.principal else None
        if a.command in {'package-check','package-import','package-verify','package-retire'}:
            if a.source is None or (principal is None and not a.common):p.error('--source and --principal or --common required')
            from . import shortcut_package as packages
            from .legal_wiki_compiler import rebuild
            from semantic_runtime.legal_agent.shortcut_store import store_owner
            source=json.loads(a.source.read_text())
            if a.common and source.get('visibility')!=packages.COMMON_VISIBILITY:
                p.error('--common needs an explicitly common package/receipt')
            if a.command=='package-retire':
                if a.common:principal=packages.common_principal(receipt=source)
                with store_owner(runtime,exclusive=True):
                    repo=ShortcutRepository(path)
                    try:
                        value=packages.retire_package(repo,principal,source)
                        value['legal_wiki']=rebuild(repo,principal,runtime/'case-memory'/'wikis'/'legal_wiki')
                    finally:repo.close()
            else:
                if a.generation is None:p.error('--generation selected source store required')
                from semantic_runtime.storage import Store
                from semantic_runtime.term_index import TermIndex
                from semantic_runtime.unit_fulltext import UnitFulltextIndex
                store=Store(a.generation)
                try:
                    if a.common:principal=packages.common_principal(store=store)
                    index=TermIndex(a.generation/'navigation',store)
                    fulltext=UnitFulltextIndex(a.generation/'fulltext',index.manifest)
                    if a.command=='package-verify':
                        binding={'generation':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256'],
                                 'unit_index_sha256':fulltext.manifest['index_sha256']}
                        if source['source_binding']!=binding:raise MemoryError('registered package source generation changed')
                        with store_owner(runtime):
                            repo=ShortcutRepository(path)
                            try:value=packages.verify_package(repo,principal,source)
                            finally:repo.close()
                    elif a.command=='package-check':
                        binding,records=packages.resolve(source,store,principal)
                        value={'checked':True,'cases':len(records),'source_entries':sum(len(r['targets']) for r in records),'binding':binding}
                        resolved={t['canonical_document_name']:{k:t[k] for k in ('canonical_document_name','document_name','document_id','source_artifact_sha256','source_binding_policy')}
                                  for record in records for t in record['targets']}
                        value['resolved_documents']=[resolved[k] for k in sorted(resolved)]
                    else:
                        with store_owner(runtime,exclusive=True):
                            repo=ShortcutRepository(path)
                            try:
                                value=packages.import_package(repo,principal,source,store)
                                value={**value,'legal_wiki':rebuild(repo,principal,runtime/'case-memory'/'wikis'/'legal_wiki')}
                            finally:repo.close()
                finally:store.close()
            if a.output is not None:ops._atomic(a.output,value)
        elif a.command=='migrate':
            if a.source is None:p.error('--source required')
            value=ops.migrate(a.source,a.output or path,kind=a.legacy_kind,principal=principal,artifact_manifest=a.artifact_manifest)
        elif a.command=='store-plan':
            if a.source is None or a.output is None:p.error('--source candidate DB and --output plan required')
            value=ops.store_plan(runtime,a.source);ops._atomic(a.output,value)
        elif a.command=='store-apply':
            if a.source is None:p.error('--source plan required')
            value=ops.apply_store(json.loads(a.source.read_text()),confirm=a.confirm_store)
        elif a.command=='store-rollback':
            if not a.expected_receipt or a.output is None:p.error('--expected-receipt and --output archive required')
            value=ops.rollback_store(runtime,a.expected_receipt,a.output)
        elif a.command=='restore':
            if a.source is None or a.output is None:p.error('--source snapshot and --output new directory required')
            value=ops.restore(a.source,a.output)
        else:
            if not path.exists():p.error('v4 store does not exist')
            repo=ShortcutRepository(path)
            try:
                if a.command=='review-import':
                    if a.source is None or principal is None:p.error('--source review file and --principal required')
                    value=ops.import_review(repo,principal,json.loads(a.source.read_text()),confirm=a.confirm_review)
                elif a.command=='retention-inventory':
                    if a.source is None:p.error('--source approved policy required')
                    value=ops.retention_inventory(repo,json.loads(a.source.read_text()),backup_manifests=a.backup_manifest)
                elif a.command=='recall-rebuild':
                    from semantic_runtime.legal_agent.wiki_recall import rebuild
                    value=rebuild(repo)
                elif a.command=='status':value=repo.status()
                elif a.command=='reconcile':value=ops.reconcile(repo)
                elif a.command=='backup':
                    if a.output is None:p.error('--output new directory required')
                    value=ops.backup(repo,a.output)
                elif a.command=='wiki-rebuild':
                    if principal is None:p.error('--principal required')
                    from .legal_wiki_compiler import rebuild
                    value=rebuild(repo,principal,runtime/'case-memory'/'wikis')
                else:p.error('catalogue commands use store-version 3')
            finally:repo.close()
        print(json.dumps(value,ensure_ascii=False,indent=2));return 0
    if a.command=='migrate':
        if a.source is None:p.error('--source required')
        value=migrate(a.source,path,kind=a.legacy_kind)
    elif a.command.startswith('catalogue-'):
        if a.source is None:p.error('--source required')
        from semantic_runtime.legal_agent.domain_control import DomainCatalogue,compile_catalogue
        if a.command=='catalogue-compile':
            if a.output is None:p.error('--output required; existing catalogues are immutable')
            value=compile_catalogue(a.source,a.output)
        else:
            catalogue=DomainCatalogue(json.loads(a.source.read_text()))
            value={'ok':True,'catalogue_hash':catalogue.hash,'method_policy_hash':catalogue.method_hash}
    elif a.command=='wiki-rebuild':
        if a.generation is None or a.principal is None or a.binding is None:p.error('--generation, --principal and exact serving --binding required')
        from types import SimpleNamespace
        from semantic_runtime.storage import Store
        from semantic_runtime.legal_agent.memory_rag import NativeRag
        from semantic_runtime.legal_agent.knowledge_repository import KnowledgeRepository
        store=Store(a.generation)
        try:
            binding=json.loads(a.binding.read_text())
            if binding['generation']!=store.manifest['generation_id'] or binding['store_sha256']!=store.manifest['store_sha256']:
                raise MemoryError('rebuild binding differs from selected generation')
            executor=SimpleNamespace(binding=binding,pipeline=SimpleNamespace(store=store))
            executor.verify=lambda read:NativeRag.verify(executor,read)
            cases=CaseRepository(path,executor,None)
            try:value=KnowledgeRepository(cases).rebuild(json.loads(a.principal.read_text()),runtime/'case-memory'/'wikis')
            finally:cases.close()
        finally:store.close()
    else:
        if not path.exists():value={'state':'NOT_BUILT'}
        else:
            with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
                value={'version':db.execute('PRAGMA user_version').fetchone()[0],
                    'questions':db.execute('SELECT count(*) FROM goal').fetchone()[0],
                    'experience_states':dict(db.execute('SELECT status,count(*) FROM knowledge GROUP BY status')),
                    'outbox_states':dict(db.execute('SELECT status,count(*) FROM outbox GROUP BY status'))}
    print(json.dumps(value,ensure_ascii=False,indent=2))
    return 0
