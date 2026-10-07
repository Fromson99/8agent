"""Prepare and verify generation-local glossary resources before serving."""
import json
import shutil
from pathlib import Path
from semantic_runtime.contracts import sha, write
from semantic_runtime.full_glossary import Glossary
from semantic_runtime.full_glossary_connections import ConnectionReader
from . import glossary_knowledge


def prepare_assets(glossary, knowledge, generation, *, storage_profile="legacy"):
    if knowledge is None:
        raise ValueError('Serving requires an explicitly selected full knowledge bundle')
    if storage_profile == 'compact-v1':
        from . import glossary_serving
        root = Path(generation) / 'glossary'
        root.mkdir(parents=True)
        dictionary = root / 'dictionary.sqlite'
        shutil.copyfile(Path(glossary) / 'dictionary.sqlite', dictionary)
        bundle = root / 'bundle'
        glossary_serving.project(knowledge, dictionary, bundle)
        cache = root / 'cache'
        reader = Glossary(bundle, dictionary, cache, manifest_sha256=sha(bundle/'manifest.json'),
                          connection_factory=ConnectionReader, allow_cache_build=True)
        reader.close()
        receipts = list(cache.glob('*.json'))
        if len(receipts) != 1: raise ValueError('Expected one glossary projection cache receipt')
        return {'schema_version': glossary_serving.VERSION, 'bundle': 'glossary/bundle',
                'dictionary': 'glossary/dictionary.sqlite', 'cache': 'glossary/cache',
                'manifest_sha256': sha(bundle/'manifest.json'), 'cache_receipt': receipts[0].name,
                'cache_receipt_sha256': sha(receipts[0])}
    if storage_profile != 'legacy': raise ValueError('Unknown storage profile')
    manifest = glossary_knowledge.verify(knowledge, force=True)
    root = Path(generation) / 'glossary'
    bundle = root / 'bundle'
    bundle.mkdir(parents=True)
    for item in manifest['files']:
        target = bundle / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(knowledge) / item['path'], target)
        if sha(target) != item['sha256']:
            raise ValueError('Copied knowledge payload changed')
    dictionary = root / 'dictionary.sqlite'
    shutil.copyfile(Path(glossary) / 'dictionary.sqlite', dictionary)
    # A derived manifest selects the reviewed dictionary while preserving source ledgers.
    selected = {**manifest, 'dictionary_sha256': sha(dictionary),
                'parent_manifest_sha256': sha(Path(knowledge) / 'manifest.json'),
                'source_dictionary_sha256': manifest['dictionary_sha256'],
                'canonical_approval': False}
    write(bundle / 'manifest.json', selected)
    cache = root / 'cache'
    with_glossary = Glossary(bundle, dictionary, cache, manifest_sha256=sha(bundle / 'manifest.json'),
                            connection_factory=ConnectionReader)
    with_glossary.close()
    receipts = list(cache.glob('*.json'))
    if len(receipts) != 1:
        raise ValueError('Expected one immutable glossary cache receipt')
    return {'bundle': 'glossary/bundle', 'dictionary': 'glossary/dictionary.sqlite',
            'cache': 'glossary/cache', 'manifest_sha256': sha(bundle / 'manifest.json'),
            'cache_receipt': receipts[0].name, 'cache_receipt_sha256': sha(receipts[0])}


def verify_assets(generation, *, verify_fulltext=True):
    from semantic_runtime.navigation_agent import glossary_assets
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    from semantic_runtime.fulltext import open_index
    generation = Path(generation)
    with_store = Store(generation)
    try:
        nav = with_store.manifest['navigation']
        path = (generation / nav['path']).resolve()
        path.relative_to(generation.resolve())
        if sha(path / 'manifest.json') != nav['manifest_sha256']:
            raise ValueError('Navigation manifest mismatch')
        index = TermIndex(path, with_store)
        fulltext = with_store.manifest.get('fulltext')
        if fulltext is not None and verify_fulltext:
            fulltext_path = (generation / fulltext['path']).resolve()
            fulltext_path.relative_to(generation.resolve())
            if sha(fulltext_path / 'manifest.json') != fulltext['manifest_sha256']:
                raise ValueError('Fulltext manifest mismatch')
            if fulltext['navigation_index_sha256'] != index.manifest['index_sha256']:
                raise ValueError('Fulltext/navigation binding mismatch')
            open_index(fulltext_path, index.manifest)
        bundle = (generation / with_store.manifest['glossary']['bundle']).resolve()
        bundle.relative_to(generation.resolve())
        if with_store.manifest['glossary'].get('schema_version') == 'glossary-serving-v2':
            from . import glossary_serving
            glossary_serving.verify(bundle, force=True)
        else:
            glossary_knowledge.verify(bundle, force=True)
        glossary = glossary_assets(generation, {})
        try:
            glossary.check_unchanged()
        finally:
            glossary.close()
    finally:
        with_store.close()
    return {'verified': True, 'manifest_sha256': sha(generation / 'manifest.json')}
