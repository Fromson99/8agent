"""Exercise the shipped entrypoints from an extracted, data-free code snapshot."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[3]


def test_extracted_delivery_loads_pipeline_and_frozen_authoring(tmp_path):
    spec = importlib.util.spec_from_file_location(
        'delivery_code_ship', ROOT / '06_TOOLS/COMMANDS/code_ship.py')
    ship = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ship)
    archive = ship.pack(tmp_path / 'code.zip')
    extracted = tmp_path / 'extracted'
    with zipfile.ZipFile(archive) as z:
        z.extractall(extracted)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('LAWRAG_', 'GENOS_', 'PYTHONPATH'))}
    commands = [
        ['06_TOOLS/pipeline.py', '--help'],
        ['06_TOOLS/pipeline.py', 'build-all', '--help'],
        ['06_TOOLS/pipeline.py', 'build-data-stages', '--help'],
        ['06_TOOLS/pipeline.py', 'glossary', 'review', '--help'],
        ['-c', "import sys; sys.path.insert(0, '02_BACKEND'); "
         "from lawrag.pipeline.genos_build import authoring; "
         "a=authoring(); a.source_module(); a.contract_module().load_contract(a.ROOT); "
         "import service; print('authoring dependencies and service imported')"],
    ]
    for command in commands:
        result = subprocess.run([sys.executable, '-B', *command], cwd=extracted,
                                env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
