"""Source + selected glossary -> source generation + pinned navigation, no model calls."""
from pathlib import Path
from contextlib import closing
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from semantic_runtime.contracts import digest,sha,write
from semantic_runtime.storage import Store,publish
from semantic_runtime.term_index import compile_index,TermIndex
from semantic_runtime import fulltext
from semantic_runtime import navigation_storage
from . import glossary_linking,glossary_knowledge


def build_generation(source,glossary,output, *, serving=False, scope=None, fulltext_granularity='article', storage_profile='legacy', audit_profile='materialized', fulltext_workers=None):
    source,glossary,output=map(lambda p:Path(p).resolve(),(source,glossary,output))
    reference_scope_mode=os.environ.get('GENOS_REFERENCE_SCOPE_V2','0')
    if reference_scope_mode not in {'0','1'}:
        raise ValueError('GENOS_REFERENCE_SCOPE_V2 must be 0 or 1')
    reference_scope_v2=reference_scope_mode=='1'
    if fulltext_granularity not in {'article','unit'}: raise ValueError('invalid fulltext granularity')
    if fulltext_workers is not None and (type(fulltext_workers) is not int or fulltext_workers < 1):
        raise ValueError('fulltext_workers must be positive')
    if storage_profile not in {'legacy','compact-v1','compact-v2'}: raise ValueError('invalid storage profile')
    if audit_profile not in {'materialized', 'factorized-v1'} or (audit_profile != 'materialized' and storage_profile != 'compact-v2'):
        raise ValueError('factorized audit requires compact-v2')
    started=time.monotonic()
    phase_started=started
    def progress(phase):
        nonlocal phase_started
        now=time.monotonic()
        print(f'GENERATION {phase} elapsed={now-started:.1f}s phase={now-phase_started:.1f}s',flush=True)
        phase_started=now
    identity={'source_sha256':sha(source),'glossary':glossary_linking.binding(glossary),
              'builder_sha256':sha(__file__),'indexer_sha256':sha(Path(compile_index.__code__.co_filename)),
              'storage_sha256':sha(Path(publish.__code__.co_filename)), 'serving':serving, 'scope':scope,
              'reference_scope_v2':reference_scope_v2,
              'serving_builder_sha256':sha(Path(__file__).with_name('term_serving_bundle.py')),
              'glossary_compiler_sha256':sha(Path(compile_index.__code__.co_filename).with_name('full_glossary.py')),
              'dependencies':{name:sha(Path(compile_index.__code__.co_filename).with_name(name))
                              for name in ('term_links.py','term_references.py','term_references_legacy.py','term_tools.py','reference_build.py','navigation_build.py','factorized_audit.py')},
              'structure_scope_sha256':sha(Path(__file__).resolve().parents[1]/'core/structure/anchors.py'),
              'navigation_storage_sha256':sha(Path(navigation_storage.__file__)),
              'reference_grammar_sha256':sha(Path(__file__).resolve().parents[1]/'core/reference_coordinate.py'),
              'legal_coordinate_sha256':sha(Path(__file__).resolve().parents[1]/'core/legal_coordinate.py'),
              'fulltext_builder_sha256':sha(Path(fulltext.__file__)) if serving else None,
              'fulltext_tokenizer':{'name':'pecab','version':fulltext.tokenizer_version()} if serving else None}
    if fulltext_workers is not None:
        identity['fulltext_workers'] = fulltext_workers
    if storage_profile in {'compact-v1','compact-v2'}:
        identity.update(storage_profile=storage_profile, audit_profile=audit_profile, compact_storage_sha256=sha(Path(publish.__code__.co_filename).with_name('compact_storage.py')),
            glossary_serving_sha256=sha(Path(__file__).with_name('glossary_serving.py')),
            checkpoint_builder_sha256=sha(Path(__file__).with_name('generation_build_steps.py')))
    if serving and fulltext_granularity == 'unit':
        from semantic_runtime import unit_fulltext
        identity.update(fulltext_granularity='unit',unit_fulltext_builder_sha256=sha(unit_fulltext.__file__))
    if output.exists():
        progress('verify-existing.start')
        value=json.loads((output/'result.json').read_text())
        if value['identity']!=identity:raise ValueError('build inputs changed; use a new run ID')
        if sha(output/'generation/manifest.json')!=value['manifest_sha256']:raise ValueError('generation manifest drift')
        with closing(Store(output/'generation')) as store:
            if store.manifest.get('source_storage'):
                from semantic_runtime.compact_storage import verify_source_audit
                verify_source_audit(output/'audit/source',store.manifest['source_storage'],store.manifest['store_sha256'])
            binding=store.manifest['navigation']
            if sha(output/'generation'/binding['path']/'manifest.json')!=binding['manifest_sha256']:
                raise ValueError('navigation binding drift')
            TermIndex(output/'generation'/binding['path'],store)
            audit=value.get('navigation_audit')
            if audit:
                index=json.loads((output/'generation'/binding['path']/'manifest.json').read_text())
                if audit.get('path')!='audit/navigation' or index.get('storage',{}).get('audit_manifest_sha256')!=audit['manifest_sha256']:
                    raise ValueError('navigation audit binding drift')
                navigation_storage.verify_audit(output/audit['path'],
                    expected_manifest_sha256=audit['manifest_sha256'],
                    expected_index_sha256=index['index_sha256'])
        if serving:
            from .term_serving_bundle import verify_assets
            verify_assets(output/'generation')
        progress('verify-existing.done')
        return value
    if storage_profile in {'compact-v1','compact-v2'}:
        from .generation_build_steps import build
        return build(source,glossary,output,identity,serving=serving,scope=scope,
                     reference_scope_v2=reference_scope_v2,fulltext_granularity=fulltext_granularity)
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    try:
        progress('link-documents.start')
        _,links=glossary_linking.project(source,glossary,temporary/'links')
        progress('link-documents.done')
        generation=temporary/'generation'
        progress('publish-source.start')
        manifest=publish(Path(__file__).resolve().parents[3],source,generation,export_allowed=False,scope=scope)
        progress('publish-source.done')
        # Refine only this unpublished copy. The selected structured source and
        # its original blocks remain immutable; navigation compiles from the
        # actual marker roles and character spans in the refined copy.
        if reference_scope_v2:
            from lawrag.core.structure.anchors import refine_store
            progress('refine-structure.start')
            with sqlite3.connect(generation/'store.sqlite') as structure:
                manifest['structure']=refine_store(structure)
                structure.commit()
                manifest['counts']={table:structure.execute('SELECT count(*) FROM '+table).fetchone()[0]
                                    for table in ('document','source_unit','source_block')}
            manifest['store_sha256']=sha(generation/'store.sqlite')
            progress('refine-structure.done')
        manifest['generation_id']='term-source-'+digest(identity)[:20]
        (generation/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        knowledge=glossary_knowledge.selected_for(glossary)
        if knowledge:glossary_knowledge.verify(knowledge)
        legal=knowledge/'legal.sqlite' if knowledge else glossary/'dictionary.sqlite'
        if serving:
            from .term_serving_bundle import prepare_assets
            progress('prepare-glossary-assets.start')
            manifest['glossary']=prepare_assets(glossary,knowledge,generation)
            (generation/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
            progress('prepare-glossary-assets.done')
        with closing(Store(generation)) as store:
            progress('compile-navigation.start')
            total_documents=store.db.execute('SELECT count(*) FROM document').fetchone()[0]
            navigation_db=generation/'navigation/navigation.sqlite'
            monitor_stop=threading.Event()
            def monitor_navigation():
                while not monitor_stop.wait(30):
                    done='unknown'
                    if navigation_db.is_file():
                        try:
                            with closing(sqlite3.connect(navigation_db.as_uri()+'?mode=ro',uri=True,timeout=0.2)) as snapshot:
                                done=str(snapshot.execute('SELECT count(DISTINCT document_id) FROM source').fetchone()[0])
                        except sqlite3.Error:
                            pass
                    size=navigation_db.stat().st_size if navigation_db.is_file() else 0
                    print(f'GENERATION compile-navigation.working elapsed={time.monotonic()-started:.1f}s '
                          f'indexed_documents={done}/{total_documents} navigation_bytes={size}',flush=True)
            monitor=threading.Thread(target=monitor_navigation,daemon=True)
            monitor.start()
            try:
                index=compile_index(store,legal,temporary/'links/links.sqlite',generation/'navigation',
                                    glossary=glossary/'dictionary.sqlite',linkage_report=links,knowledge=knowledge,
                                    reference_scope_v2=reference_scope_v2,
                                    audit_output=temporary/'audit/navigation')
            finally:
                monitor_stop.set()
                monitor.join(timeout=1)
            progress('compile-navigation.done')
        manifest['navigation']={'path':'navigation','manifest_sha256':sha(generation/'navigation/manifest.json')}
        if serving:
            progress('compile-fulltext.start')
            worker_options = {'workers': fulltext_workers} if fulltext_workers is not None else {}
            fulltext_manifest=(fulltext.build(generation/'navigation',generation/'fulltext',granularity='unit',generation=generation,**worker_options)
                               if fulltext_granularity=='unit' else fulltext.build(generation/'navigation',generation/'fulltext',**worker_options))
            manifest['fulltext']={'path':'fulltext',
                                  'manifest_sha256':sha(generation/'fulltext/manifest.json'),
                                  'navigation_index_sha256':fulltext_manifest['navigation_index_sha256']}
            progress('compile-fulltext.done')
        # This generation has not been published. Index binds all other manifest fields.
        (generation/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        with closing(Store(generation)) as store:TermIndex(generation/'navigation',store)
        progress('verify-navigation.done')
        result={'schema_version':'term-generation-build-v1','identity':identity,'generation':'generation',
                'manifest_sha256':sha(generation/'manifest.json'),'navigation':manifest['navigation'],
                'counts':index['counts'],'llm_calls':0,'quality_certified':False,'activated':False}
        if index.get('storage'):
            result['navigation_audit']={'path':'audit/navigation',
                'manifest_sha256':index['storage']['audit_manifest_sha256']}
        if sha(source)!=identity['source_sha256'] or glossary_linking.binding(glossary)!=identity['glossary']:
            raise ValueError('build input drift')
        write(temporary/'result.json',result)
        if output.exists():raise ValueError('build output appeared during execution')
        os.rename(temporary,output)
        progress('publish-generation.done')
        return result
    except BaseException:
        shutil.rmtree(temporary)
        raise
