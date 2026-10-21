"""Run only with the chosen checkout's Python imports; no models or NFS writes."""
import json
from pathlib import Path
import sys
from contextlib import closing

root, action, generation, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
sys.path.insert(0, str(root/'02_BACKEND'))
from lawrag.pipeline.search_selection import plan, encode
from semantic_runtime.storage import Store
from semantic_runtime.contracts import sha

if action == 'plan':
    # Ensure the later deployment gate is importable before modifying DEV.
    from lawrag.pipeline.term_serving_bundle import verify_assets
    value = plan(generation, latest=True, exceptions=root/'00_SYSTEM/FILENAME_EXCEPTIONS.json')
    output.write_bytes(encode(value))
    imports={}
    for module in list(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if not filename: continue
        source=Path(filename).resolve()
        if source.is_relative_to(root): imports[str(source.relative_to(root))]=sha(source)
    output.with_suffix('.imports.json').write_bytes(encode(imports))
elif action == 'verify':
    from semantic_runtime.deployment_paths import install, verify_generation
    env = {}; config = install(root, environment=env)
    verify_generation(config, generation)
    with closing(Store(generation, verify=False)) as store:
        store.selection.require_latest()
        if store.selection.path != root/'00_SYSTEM/SEARCH_SELECTION/generation.json':
            raise ValueError('runtime did not select deployed code JSON')
        value = dict(state='CODE_SELECTION_VERIFIED', generation=str(generation),
            generation_id=store.manifest['generation_id'],
            manifest_sha256=sha(generation/'manifest.json'),
            selection_path=str(store.selection.path), selection_sha256=sha(store.selection.path),
            counts=store.selection.value['counts'], python=sys.executable, version=sys.version)
    output.write_bytes(encode(value)); print(json.dumps(value,ensure_ascii=False),flush=True)
else:
    raise ValueError('unknown worker action')
