"""Exercise the lazy definition import before network or long projection work."""
import hashlib
import importlib
import json
from pathlib import Path
import sys


def preflight(root):
    root = Path(root).resolve()
    pins = json.loads((root/'PACKAGE_FILES.json').read_text())
    for name in ('semantic_runtime.contracts', 'semantic_runtime.full_glossary', 'semantic_runtime.term_links',
                 'semantic_runtime.term_index', 'lawrag.pipeline.oracle_query_navigation_publish'):
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(root):
            raise RuntimeError('PROJECTION_PREFLIGHT_MODULE_ORIGIN: '+name)
        relative = str(path.relative_to(root))
        if hashlib.sha256(path.read_bytes()).hexdigest() != pins.get(relative):
            raise RuntimeError('PROJECTION_PREFLIGHT_CODE_HASH: '+name)
    from semantic_runtime.term_index import definition_summary
    from semantic_runtime import contracts, full_glossary
    test_path = root/'client/MAPPING_BINDING.json'
    expected = hashlib.sha256(test_path.read_bytes()).hexdigest()
    if contracts.sha(test_path) != expected or full_glossary.sha(test_path) != expected:
        raise RuntimeError('PROJECTION_PREFLIGHT_FILE_HASH')
    value = definition_summary('preflight-definition',
        {'source_id':'preflight-source', 'key':'Ａ B\t가', 'scope_status':'EXPLICIT'})
    if value != ('preflight-definition','preflight-source','Ａ B\t가','ab가','EXPLICIT'):
        raise RuntimeError('PROJECTION_PREFLIGHT_NORMALIZATION')
    print('DEPENDENCY_PREFLIGHT_PASS: Python '+'.'.join(map(str,sys.version_info[:3]))+
          ' / 정의문·모듈·파일해시 확인', flush=True)
