"""Compare a supplied image inventory to requirements and actual Python imports.

Read-only with respect to product code. An inventory omission is not evidence of
an on-site import failure. Dynamic imports/platform modules are reported separately.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
ALIASES = {'bs4': 'beautifulsoup4', 'docling_core': 'docling-core', 'docx': 'python-docx',
           'dotenv': 'python-dotenv', 'fitz': 'pymupdf', 'hwp5': 'pyhwp',
           'sentence_transformers': 'sentence-transformers', 'yaml': 'pyyaml',
           'socketio': 'python-socketio'}
INTERNAL = {'lawrag', 'semantic_runtime', 'workflow', 'service', 'main', 'genos_diagnostics',
            'genos_reindex_logging', 'genos_reindex_only', 'genos_reindex_runner',
            'stream_app', 'start_sse', 'ontology_console', 'ontology_dashboard',
            'ontology_dashboard_model', 'ontology_dashboard_demo'}
CLASSIFICATION = {
    'sqlglot': 'developer-only prepared SQL build; current working Oracle serving has no runtime import',
    'pyarrow': 'required transitive runtime: PeCab tokenizer dictionary',
    'emoji': 'required transitive runtime: PeCab emoji processing',
    'pytest': 'declared PeCab install dependency and test runner; not a PeCab runtime import',
    'genos': 'platform SDK: Oracle REST replacement is now available if absent',
    'anthropic': 'conditional external Anthropic backend; GENOS branch does not require it',
    'chardet': 'optional encoding detector with existing ImportError fallback',
    'dataiku': 'Dataiku-hosted UI/folder integration; not base GENOS RAG',
    'streamlit': 'separate ontology management UI host',
    'genon': 'same-Pod preprocessor vendor source, enabled by GENOS_PREPROCESSOR_TRANSPORT=pod',
    'main-socketio': 'workflow-host platform module; distinct from python-socketio',
    'scripts': 'legacy internal tool namespace; not an installable external dependency',
}


def canonical(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def inventory(path):
    values = defaultdict(list)
    for number, line in enumerate(path.read_text().splitlines(), 1):
        value = line.split('#', 1)[0].strip()
        if not value:
            continue
        match = re.fullmatch(r'([\w.-]+)==([^\s]+)', value)
        if not match:
            raise ValueError(f'invalid inventory line {number}')
        values[canonical(match[1])].append(match[2])
    return dict(values)


def audit(image_path):
    image = inventory(image_path)
    required = inventory(ROOT/'requirements.txt')
    active = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    release = json.loads((ROOT/active['manifest_path']).read_text())
    files = [p for p in (ROOT/'02_BACKEND').rglob('*.py')
             if not {'GENERATIONS', 'research', '__pycache__'}.intersection(p.parts)]
    files.extend(ROOT/p for p in ['service.py', 'main.py', 'genos_diagnostics.py',
                 '08_DEPLOYMENT/GENOS/start_sse.py', '08_DEPLOYMENT/GENOS/stream_app.py',
                 '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',
                 '08_DEPLOYMENT/GENOS/preprocessor/preprocessor.py'])
    files.extend(p for p in (ROOT/'03_FRONTEND/APPS/legal-knowledge-streamlit').glob('*.py')
                 if not p.name.startswith(('test_', 'check_')))
    imports = defaultdict(list)
    errors = []
    hashes = {}
    for file in sorted(set(files)):
        rel = file.relative_to(ROOT).as_posix()
        raw = file.read_bytes()
        hashes[rel] = hashlib.sha256(raw).hexdigest()
        try:
            tree = ast.parse(raw, filename=rel)
        except SyntaxError as exc:
            errors.append({'path': rel, 'line': exc.lineno})
            continue
        for node in ast.walk(tree):
            names = []
            kind = 'import'
            if isinstance(node, ast.Import):
                names = [v.name for v in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                names = [node.module]
            elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
                target = ast.unparse(node.func)
                if target in ('importlib.import_module', '__import__') and isinstance(node.args[0].value, str):
                    names = [node.args[0].value]
                    kind = 'literal_dynamic_import'
            for name in names:
                top = name.split('.')[0]
                if not top or top in sys.stdlib_module_names or top in INTERNAL:
                    continue
                package = canonical(ALIASES.get(top, top))
                imports[package].append({'module': name, 'path': rel, 'line': node.lineno,
                                        'kind': kind, 'listed_in_main136': rel in release['files']})
    pecab = {'version': metadata.version('pecab'), 'requires': metadata.requires('pecab'), 'runtime_imports': []}
    distribution = metadata.distribution('pecab')
    for file in distribution.files or []:
        if not str(file).startswith('pecab/') or not str(file).endswith('.py'):
            continue
        raw = distribution.locate_file(file).read_bytes()
        for node in ast.walk(ast.parse(raw)):
            names = ([v.name for v in node.names] if isinstance(node, ast.Import) else
                     [node.module] if isinstance(node, ast.ImportFrom) and not node.level and node.module else [])
            for name in names:
                if name.split('.')[0] in ('pyarrow', 'emoji', 'pytest'):
                    pecab['runtime_imports'].append({'module': name, 'path': str(file), 'line': node.lineno,
                                                     'sha256': hashlib.sha256(raw).hexdigest()})
    return {
        'source': 'user OCR inventory; no live image introspection',
        'inventory_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
        'image_entries': sum(map(len, image.values())), 'image_unique_packages': len(image),
        'duplicate_packages': {k: v for k, v in image.items() if len(v) > 1},
        'selected_release': active['release_id'],
        'missing_declared_requirements': {k: {'version': v, 'classification': CLASSIFICATION.get(k)}
                                          for k, v in required.items() if k not in image},
        'declared_version_differences': {k: {'required': v, 'image': image[k]}
                                       for k, v in required.items() if k in image and v != image[k]},
        'imports_not_in_inventory': {k: {'classification': CLASSIFICATION.get(k, 'REVIEW_REQUIRED'), 'uses': v}
                                     for k, v in sorted(imports.items()) if k not in image},
        'all_external_imports': dict(sorted(imports.items())), 'pecab_local_same_version_evidence': pecab,
        'scanned_files': len(hashes), 'scan_errors': errors, 'source_hashes': hashes,
        'limitations': ['No on-site runtime/ABI/native-library/model-asset verification.',
                       'Computed dynamic module names and arbitrary plugins are not statically resolved.',
                       'PeCab metadata/code evidence is the locally installed package; image bytes are unknown.',
                       'Other third-party packages were not exhaustively checked for transitive version compatibility.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.inventory)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ['image_entries', 'image_unique_packages', 'duplicate_packages',
          'scanned_files', 'scan_errors', 'missing_declared_requirements', 'declared_version_differences']}, ensure_ascii=False))
    print('Imports absent from inventory:', ', '.join(result['imports_not_in_inventory']))


if __name__ == '__main__':
    main()
