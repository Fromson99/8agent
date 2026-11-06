"""Reuse prepared manifests; no large SQLite SHA, source COUNT or new projection.
Metadata hashes identify the same release. They do not certify current data bytes.
"""
from pathlib import Path
from gold_io import Stop, digest


def inputs(loader, old_job, directory, prior, progress):
    from lawrag.pipeline import oracle_query_package as pack
    from lawrag.pipeline.oracle_deferred_import import prepared_descriptor
    from strict_resume import source_descriptor
    full = loader.read(old_job/'full-state.json')
    root = Path(full['identity']['generation']).resolve(strict=True)
    if old_job.parent not in root.parents or root.name != 'generation' or str(root) != prior['binding']['generation']:
        raise Stop('INPUT_GENERATION_CHANGED')
    cache = directory/'input-descriptors-r5.json'
    if cache.exists():
        saved = loader.read(cache)
        if saved['binding'] != {k: prior['binding'][k] for k in ('generation','files','source_release','query_release')}:
            raise Stop('INPUT_DESCRIPTOR_BINDING_CHANGED')
        return root, saved['binding']['files'], saved['source'], saved['query'], saved['paths']
    descriptor = loader.read(old_job/'projection-descriptor-r7.json')
    files = descriptor['binding']['files']
    if files != prior['binding']['files']: raise Stop('INPUT_FILES_BINDING_CHANGED')
    manifest = loader.read(root/'manifest.json')
    # Preserve byte length / part counts of the original source descriptor. The
    # prepared hashes are reused, not recomputed from multi-GB SQLite files.
    items = []
    for relative, sha in sorted(files.items()):
        path = (root/relative).resolve(strict=True)
        if root not in path.parents: raise Stop('INPUT_PATH_OUTSIDE_GENERATION')
        if relative not in {'store.sqlite','manifest.json'}:
            size = path.stat().st_size
            items.append({'path':relative,'sha256':sha,'bytes':size,'parts':(size+1024**2-1)//1024**2})
    selection = root.parent/'SEARCH_SELECTION'/(root.name+'.json')
    selected = loader.read(selection) if selection.exists() else None
    counts = {k:manifest['counts']['source_block' if k=='block_payload' else k] for k in loader.SOURCE_MAP}
    source = source_descriptor(root,manifest,items,files,selected,old_job,full['identity']['target'],counts)
    paths,tables = prepared_descriptor(root,source,files,old_job,strict=True)
    if 'projection_policy' in prior['binding']:
        query = loader.read(directory/'query-reduced.json')
    else:
        query = pack.query_manifest(root,source,paths,tables,items)
    if digest(source) != prior['binding']['source_release'] or digest(query) != prior['binding']['query_release']:
        raise Stop('INPUT_RELEASE_CHANGED')
    saved = {'binding':{k:prior['binding'][k] for k in ('generation','files','source_release','query_release')},
             'source':source,'query':query,'paths':paths,'data_rehashed':False}
    loader.atomic(cache,saved)
    progress.emit('PREPARED_INPUTS_REUSED',large_file_sha=False,source_count_scan=False)
    return root,files,source,query,paths
