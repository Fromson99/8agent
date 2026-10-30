"""Exercise the exact sealed CLI under spawn, import and direct execution."""
from pathlib import Path
import os
import subprocess
import sys
import zipfile
import pytest

HERE=Path(__file__).resolve().parent

def extracted(tmp_path):
    with zipfile.ZipFile(HERE/'GENOS_DATAIKU_COMPUTE_20261029_R10.zip') as z:
        z.extractall(tmp_path)
    root=tmp_path/'GENOS_DATAIKU_COMPUTE_20261029_R10'
    env={**os.environ,'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
         'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(root/'02_BACKEND')}
    return root,env

@pytest.mark.parametrize('run_name',['__mp_main__','imported_cli'])
def test_spawn_and_import_do_not_load_absent_engine(tmp_path,run_name):
    root,env=extracted(tmp_path)
    assert not (root/'02_BACKEND/PIPELINE/engine_host.py').exists()
    command='import runpy,sys;runpy.run_path(sys.argv[1],run_name=sys.argv[2]);print("IMPORT_OK")'
    done=subprocess.run([sys.executable,'-B','-c',command,str(root/'06_TOOLS/pipeline.py'),run_name],env=env,text=True,capture_output=True,timeout=15)
    assert done.returncode==0,done.stderr
    assert done.stdout.strip()=='IMPORT_OK'

def test_direct_main_still_dispatches_engine(tmp_path):
    root,env=extracted(tmp_path)
    engine=root/'02_BACKEND/PIPELINE/engine_host.py';engine.parent.mkdir(parents=True,exist_ok=True)
    engine.write_text('def main():\n    print("ENGINE_FALLBACK_OK")\n')
    done=subprocess.run([sys.executable,'-B',str(root/'06_TOOLS/pipeline.py'),'fixture-fallback'],env=env,text=True,capture_output=True,timeout=15)
    assert done.returncode==0,done.stderr
    assert done.stdout.strip()=='ENGINE_FALLBACK_OK'
