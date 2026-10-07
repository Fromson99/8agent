"""Exercise the shipped entrypoints from an extracted, data-free code snapshot."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('full_code', [False, True])
def test_extracted_delivery_loads_pipeline_and_service(tmp_path, full_code):
    spec = importlib.util.spec_from_file_location(
        'delivery_code_ship', ROOT / '06_TOOLS/COMMANDS/code_ship.py')
    ship = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ship)
    archive = ship.pack(tmp_path / 'code.zip', ROOT / 'genosIgnore' if full_code else None)
    extracted = tmp_path / 'extracted'
    with zipfile.ZipFile(archive) as z:
        z.extractall(extracted)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('LAWRAG_', 'GENOS_', 'PYTHONPATH'))}
    commands = [
        ['06_TOOLS/pipeline.py', '--help'],
        ['06_TOOLS/pipeline.py', 'build-all', '--help'],
        ['06_TOOLS/pipeline.py', 'build-data-stages', '--help'],
        ['06_TOOLS/pipeline.py', 'document-release', '--help'],
        ['06_TOOLS/pipeline.py', 'glossary', 'review', '--help'],
        ['-c', "import sys; sys.path.insert(0, '02_BACKEND'); "
         "from lawrag.pipeline import genos_build; "
         "assert callable(genos_build.inventory); "
         "from lawrag.pipeline.structure_selection import select_completed; "
         "assert callable(select_completed); "
         "import service; print('build dependencies and service imported')"],
    ]
    if full_code:
        commands.append(['06_TOOLS/run_tool.py', 'genos_preflight.py', '--help'])
        commands.append(['-c', "import runpy; from pathlib import Path; "
                         "m=runpy.run_path('06_TOOLS/COMMANDS/genos_preflight.py'); "
                         "assert {'fastapi', 'httpx', 'docling-core', 'kiwipiepy'} <= m['_requirements'](); "
                         "r=runpy.run_path('06_TOOLS/run_tool.py'); "
                         "assert all(p.is_dir() for p in r['_targets'](Path.cwd()))"])
    for command in commands:
        result = subprocess.run([sys.executable, '-B', *command], cwd=extracted,
                                env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
