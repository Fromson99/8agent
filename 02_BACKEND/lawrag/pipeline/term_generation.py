"""Source + selected glossary -> source generation + pinned navigation, no model calls."""
from pathlib import Path
from contextlib import closing
import json
import os
import shutil
import tempfile
from semantic_runtime.contracts import digest,sha,write
from semantic_runtime.storage import Store,publish
from semantic_runtime.term_index import compile_index,TermIndex
from . import glossary_linking,glossary_knowledge


def build_generation(source,glossary,output, *, serving=False, scope=None):
    source,glossary,output=map(lambda p:Path(p).resolve(),(source,glossary,output))
    identity={'source_sha256':sha(source),'glossary':glossary_linking.binding(glossary),
              'builder_sha256':sha(__file__),'indexer_sha256':sha(Path(compile_index.__code__.co_filename)),
              'storage_sha256':sha(Path(publish.__code__.co_filename)), 'serving':serving, 'scope':scope,
              'serving_builder_sha256':sha(Path(__file__).with_name('term_serving_bundle.py')),
              'glossary_compiler_sha256':sha(Path(compile_index.__code__.co_filename).with_name('full_glossary.py')),
              'dependencies':{name:sha(Path(compile_index.__code__.co_filename).with_name(name))
                              for name in ('term_links.py','term_references.py','term_tools.py')}}
    if output.exists():
        value=json.loads((output/'result.json').read_text())
        if value['identity']!=identity:raise ValueError('build inputs changed; use a new run ID')
        if sha(output/'generation/manifest.json')!=value['manifest_sha256']:raise ValueError('generation manifest drift')
        with closing(Store(output/'generation')) as store:
            binding=store.manifest['navigation']
            if sha(output/'generation'/binding['path']/'manifest.json')!=binding['manifest_sha256']:
                raise ValueError('navigation binding drift')
            TermIndex(output/'generation'/binding['path'],store)
        if serving:
            from .term_serving_bundle import verify_assets
            verify_assets(output/'generation')
        return value
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    try:
        _,links=glossary_linking.project(source,glossary,temporary/'links')
        generation=temporary/'generation'
        manifest=publish(Path(__file__).resolve().parents[3],source,generation,export_allowed=False,scope=scope)
        manifest['generation_id']='term-source-'+digest(identity)[:20]
        (generation/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        knowledge=glossary_knowledge.selected_for(glossary)
        if knowledge:glossary_knowledge.verify(knowledge)
        legal=knowledge/'legal.sqlite' if knowledge else glossary/'dictionary.sqlite'
        if serving:
            from .term_serving_bundle import prepare_assets
            manifest['glossary']=prepare_assets(glossary,knowledge,generation)
            (generation/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        with closing(Store(generation)) as store:
            index=compile_index(store,legal,temporary/'links/links.sqlite',generation/'navigation',
                                glossary=glossary/'dictionary.sqlite',linkage_report=links,knowledge=knowledge)
        manifest['navigation']={'path':'navigation','manifest_sha256':sha(generation/'navigation/manifest.json')}
        # This generation has not been published. Index binds all other manifest fields.
        (generation/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        with closing(Store(generation)) as store:TermIndex(generation/'navigation',store)
        result={'schema_version':'term-generation-build-v1','identity':identity,'generation':'generation',
                'manifest_sha256':sha(generation/'manifest.json'),'navigation':manifest['navigation'],
                'counts':index['counts'],'llm_calls':0,'quality_certified':False,'activated':False}
        if sha(source)!=identity['source_sha256'] or glossary_linking.binding(glossary)!=identity['glossary']:
            raise ValueError('build input drift')
        write(temporary/'result.json',result)
        if output.exists():raise ValueError('build output appeared during execution')
        os.rename(temporary,output)
        return result
    except BaseException:
        shutil.rmtree(temporary)
        raise
