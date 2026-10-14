"""Explicit compact build stages; verified completed stages survive interruption."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import shutil
import time
from semantic_runtime.contracts import sha, write, digest
from semantic_runtime import storage, compact_storage, term_index, fulltext
from . import glossary_linking, glossary_knowledge, term_serving_bundle


class Stages:
    def __init__(self, root, identity):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.receipts=self.root/'checkpoints'
        self.receipts.mkdir(exist_ok=True)
        pin=self.receipts/'identity.json'
        if pin.exists():
            if json.loads(pin.read_text())!=identity:raise ValueError('resume inputs/code changed; use a new output')
        else:write(pin,identity)
        self.metrics=[]

    def run(self, name, outputs, build, *, preserve_partial=False):
        receipt=self.receipts/(name+'.json')
        started=time.monotonic()
        if receipt.exists():
            saved=json.loads(receipt.read_text())
            for rel,expected in saved['files'].items():
                path=self.root/rel
                if path.is_symlink() or not path.is_file() or sha(path)!=expected:
                    raise ValueError('completed stage drift: '+name+'/'+rel)
            value=saved['value'];reused=True
        else:
            # Only this stage's incomplete products are replaceable. Earlier receipts
            # are immutable and never accepted merely because a directory exists.
            for rel in ([] if preserve_partial else outputs):
                path=self.root/rel
                if path.is_symlink():raise ValueError('symlink in stage output')
                if path.is_dir():shutil.rmtree(path)
                elif path.exists():path.unlink()
            value=build()
            paths=[]
            for rel in outputs:
                path=self.root/rel
                paths.extend(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else paths.append(path) if path.is_file() else None
            saved={'schema_version':'genos-build-checkpoint-v1','stage':name,'value':value,
                   'files':{str(p.relative_to(self.root)):sha(p) for p in paths}}
            if not saved['files']:raise ValueError('empty stage cannot be checkpointed')
            temporary=receipt.with_suffix('.pending')
            temporary.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n');os.replace(temporary,receipt);reused=False
        elapsed=time.monotonic()-started
        self.metrics.append({'stage':name,'seconds':elapsed,'reused':reused,'files':len(saved['files'])})
        print(f'GENERATION {name} seconds={elapsed:.3f} reused={reused}',flush=True)
        return value


def build(source, glossary, output, identity, *, serving, scope, reference_scope_v2, fulltext_granularity):
    output.parent.mkdir(parents=True,exist_ok=True)
    lock=output.parent/('.'+output.name+'.build.lock')
    with lock.open('a+') as guard:
        try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('this generation is already building') from None
        if output.exists():raise ValueError('output appeared; reopen and verify completed generation')
        temporary=output.parent/('.'+output.name+'.building')
        stages=Stages(temporary,identity)
        profile=identity.get('storage_profile','compact-v1')
        generation=temporary/'generation'
        links=stages.run('links',['links'],lambda:glossary_linking.project(source,glossary,temporary/'links',copy_source=False)[1])
        def publish():
            generation.mkdir(exist_ok=True)
            # Stage cleanup is limited to the source payload and native audit.
            raw=temporary/'native-source'
            manifest=storage.publish(None,source,raw,export_allowed=False,scope=scope)
            if reference_scope_v2:
                import sqlite3
                from lawrag.core.structure.anchors import refine_store
                with closing(sqlite3.connect(raw/'store.sqlite')) as db:
                    manifest['structure']=refine_store(db);db.commit()
                    manifest['counts']={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in storage.TABLES}
                manifest['store_sha256']=sha(raw/'store.sqlite')
            manifest=compact_storage.source(raw,temporary/'audit/source',manifest)
            os.replace(raw/'store.sqlite',generation/'store.sqlite')
            manifest['generation_id']='term-source-'+digest(identity)[:20]
            write(temporary/'source-stage.json',manifest)
            shutil.rmtree(raw)
            return manifest
        manifest=stages.run('source',['generation/store.sqlite','audit/source','native-source','source-stage.json'],publish)
        # native-source is intentionally consumed, so the stage inventory records only existing paths.
        knowledge=glossary_knowledge.selected_for(glossary)
        if knowledge:glossary_knowledge.verify(knowledge)
        legal=knowledge/'legal.sqlite' if knowledge else glossary/'dictionary.sqlite'
        if serving:
            manifest['glossary']=stages.run('glossary',['generation/glossary'],lambda:
                term_serving_bundle.prepare_assets(glossary,knowledge,generation,storage_profile='compact-v1'))
        (generation/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        def navigation():
            with closing(storage.Store(generation)) as store:
                return term_index.compile_index(store,legal,temporary/'links/links.sqlite',generation/'navigation',
                    glossary=glossary/'dictionary.sqlite',linkage_report=links,knowledge=knowledge,
                    reference_scope_v2=reference_scope_v2,audit_output=temporary/'audit/navigation',storage_profile=profile,
                    audit_profile=identity.get('audit_profile','materialized'))
        index=stages.run('navigation',['generation/navigation','audit/navigation'],navigation,preserve_partial=profile=='compact-v2')
        manifest['navigation']={'path':'navigation','manifest_sha256':sha(generation/'navigation/manifest.json')}
        if serving:
            worker_options = {'workers': identity['fulltext_workers']} if 'fulltext_workers' in identity else {}
            ft=stages.run('fulltext',['generation/fulltext'],lambda:
                fulltext.build(generation/'navigation',generation/'fulltext',granularity='unit',generation=generation,**worker_options)
                if fulltext_granularity=='unit' else fulltext.build(generation/'navigation',generation/'fulltext',**worker_options))
            manifest['fulltext']={'path':'fulltext','manifest_sha256':sha(generation/'fulltext/manifest.json'),
                                  'navigation_index_sha256':ft['navigation_index_sha256']}
        (generation/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        with closing(storage.Store(generation)) as store:term_index.TermIndex(generation/'navigation',store)
        if serving:term_serving_bundle.verify_assets(generation)
        if sha(source)!=identity['source_sha256'] or glossary_linking.binding(glossary)!=identity['glossary']:
            raise ValueError('build input drift')
        result={'schema_version':'term-generation-build-v2','identity':identity,'generation':'generation',
                'manifest_sha256':sha(generation/'manifest.json'),'navigation':manifest['navigation'],
                'counts':index['counts'],'llm_calls':0,'quality_certified':False,'activated':False,
                'navigation_audit':{'path':'audit/navigation','manifest_sha256':index['storage']['audit_manifest_sha256']},
                'source_audit':{'path':'audit/source','manifest_sha256':manifest['source_storage']['audit_manifest_sha256']},
                'stages':stages.metrics}
        write(temporary/'result.json',result)
        os.rename(temporary,output)
        return result
