"""Build three reviewable handoff ZIPs from exact working bytes; no user data."""
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'src'))
import transport as t


def add(source, target):
    if source.is_symlink():
        raise ValueError('symlink: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def seal(folder, name):
    pins = {str(p.relative_to(folder)): t.sha(p) for p in t.files(folder) if p.name != 'CODE_PINS.json'}
    t.write(folder / 'CODE_PINS.json', {'format': 'pipeline-code-pins-v1', 'files': pins})
    with zipfile.ZipFile(HERE / (name+'.zip'), 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in t.files(folder):
            z.write(path, name+'/'+str(path.relative_to(folder)))
    return {'zip': name+'.zip', 'sha256': t.sha(HERE / (name+'.zip')),
            'bytes': (HERE / (name+'.zip')).stat().st_size, 'files': len(pins)}


def build():
    staging = HERE / 'packages'
    if staging.exists():
        # This directory is exclusively this builder's reproducible code output.
        shutil.rmtree(staging)
    service = staging / 'GENOS_PIPELINE_SERVICE_20261022_R1'
    exporter = staging / 'GENOS_RAW_EXPORT_20261022_R1'
    dataiku = staging / 'DATAIKU_PIPELINE_CLIENT_20261022_R1'
    for name in ['service.py', 'worker.py', 'transport.py']:
        add(HERE / 'src' / name, service / name)
    suffixes = {'.py', '.json', '.yaml', '.yml', '.sql', '.txt', '.sh'}
    roots = ['00_SYSTEM', '02_BACKEND/lawrag/core', '02_BACKEND/lawrag/platform',
             '02_BACKEND/lawrag/pipeline', '02_BACKEND/lawrag/sources', '02_BACKEND/lawrag/datasets',
             '02_BACKEND/semantic_runtime', '06_TOOLS/COMMANDS', '06_TOOLS/OFFLINE']
    for root in roots:
        for p in (ROOT / root).rglob('*'):
            if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts:
                add(p, service / p.relative_to(ROOT))
    for name in ['02_BACKEND/lawrag/__init__.py', '06_TOOLS/pipeline.py', '06_TOOLS/run_tool.py']:
        add(ROOT / name, service / name)
    # Pin the locally installed parsing stack separately from onsite verification.
    from importlib.metadata import version, PackageNotFoundError
    dependencies = ['beautifulsoup4', 'docling', 'docling-core', 'httpx', 'jsonschema', 'pecab', 'pyarrow',
                    'regex', 'emoji', 'numpy', 'openpyxl', 'pdfplumber', 'pyhwp', 'pymupdf',
                    'python-docx', 'python-dotenv', 'pyyaml', 'referencing', 'requests', 'sqlglot']
    pinned = []
    for dep in dependencies:
        try:
            pinned.append(dep+'=='+version(dep))
        except PackageNotFoundError:
            raise ValueError('Unverified dependency: ' + dep)
    (service / 'requirements.txt').write_text('\n'.join(pinned)+'\n')
    add(HERE / 'SERVICE_GUIDE.txt', service / 'GUIDE.txt')
    service_receipt = seal(service, service.name)
    for name in ['transport.py', 'export_inputs.py', 'restore_inputs.py']:
        add(HERE / 'src' / name, exporter / name)
    add(HERE / 'EXPORT_GUIDE.txt', exporter / 'GUIDE.txt')
    add(HERE / 'GENOS_RAW_EXPORT_RUN.txt', exporter / 'GENOS_RAW_EXPORT_RUN.txt')
    export_receipt = seal(exporter, exporter.name)
    for name in ['dataiku_run.py', 'restore_inputs.py', 'transport.py']:
        add(HERE / 'src' / name, dataiku / name)
    # Resolve the maintained Dataiku loader imports; lazy projection modules are explicit.
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    for name in ['lawrag.pipeline.oracle_full_package', 'lawrag.pipeline.oracle_query_dataiku',
                 'lawrag.pipeline.oracle_query_navigation_publish', 'semantic_runtime.filename_versions',
                 'semantic_runtime.legal_agent.errors', 'semantic_runtime.term_index',
                 'semantic_runtime.search_selection', 'semantic_runtime.multi_entry_navigation',
                 'semantic_runtime.folder_navigation']:
        importlib.import_module(name)
    for module in list(sys.modules.values()):
        raw = getattr(module, '__file__', None)
        if raw and Path(raw).resolve().is_relative_to(ROOT / '02_BACKEND'):
            path = Path(raw).resolve()
            if path.suffix == '.py':
                add(path, dataiku / path.relative_to(ROOT))
    (dataiku / 'SERVICE_CODE_SHA256.txt').write_text(t.sha(service / 'CODE_PINS.json')+'\n')
    add(HERE / 'DATAIKU_GUIDE.txt', dataiku / 'GUIDE.txt')
    add(HERE / 'DATAIKU_RECIPE.py', dataiku / 'DATAIKU_RECIPE.py')
    add(HERE / 'DATAIKU_RECIPE.py', dataiku / 'DATAIKU_PIPELINE_RUN.txt')
    dataiku_receipt = seal(dataiku, dataiku.name)
    source_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    integration_revision = subprocess.check_output(['git', 'rev-parse', 'infocz/fde/seungho/integration'], cwd=ROOT, text=True).strip()
    receipt = {'git_parent': source_revision, 'source': 'working-tree bytes pinned; no commit/push',
               'integration_reference': integration_revision, 'packages': [export_receipt, service_receipt, dataiku_receipt],
               'genos_deployed': False, 'oracle_loaded': False, 'local_main_changed': False}
    t.write(HERE / 'BUILD.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    build()
