"""Explicit candidate binding for the existing glossary learn operator CLI."""
from contextlib import contextmanager
from types import SimpleNamespace
import importlib.util,os
from runtime import *

@contextmanager
def mapping_context(args):
    mod,parent,multi,mods,root=load(not bool(os.getenv('ADR451_TEST_MUTABLE')))
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    store=Store(args.generation);tools=None
    try:
        scope=read(args.authorized_documents)
        if not isinstance(scope,list) or not scope or any(not isinstance(d,str) for d in scope):raise ValueError('nonempty document ID allowlist required')
        documents={r[0]:r[1] for r in store.db.execute('SELECT document_id,name FROM document')}
        if not set(scope)<=documents.keys():raise ValueError('document allowlist outside selected generation')
        binding=store.manifest['navigation'];index_path=(args.generation/binding['path']).resolve();index_path.relative_to(args.generation.resolve())
        if sha(index_path/'manifest.json')!=binding['manifest_sha256']:raise ValueError('navigation index manifest mismatch')
        index=TermIndex(index_path,store);tools=index.tools(scope)
        units={(r['document_id'],str(r['unit_id'])):json.loads(r['json']) for r in store.db.execute('SELECT document_id,unit_id,json FROM source_unit') if r['document_id'] in scope}
        matcher=SimpleNamespace(documents=documents,tools=tools,units=units,sources={})
        matcher=multi.folders.bind_catalogue(matcher,store,read(args.origin_projection) if args.origin_projection else None)
        yield mod.MappingStore(args.ledger,matcher,store.manifest,scope,args.actor),mod.EntityRegistry(matcher,scope,'',[])
    finally:
        if tools:tools.db.close()
        store.close()

def main(argv=None,context_factory=mapping_context):
    mutable=bool(os.getenv('ADR451_TEST_MUTABLE'));path=C/'snapshot'
    if not mutable:
        load();cm=read(C/'candidate.json');path=C/'revisions'/cm['revisions'][-1]['revision_id']/'snapshot'
    spec=importlib.util.spec_from_file_location('mapped_learning_cli',path/'02_BACKEND/lawrag/pipeline/glossary_learning.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.main(argv,mapping_context=context_factory)
if __name__=='__main__':raise SystemExit(main())
