"""Exercise the build installer with the qualified code/dependencies and real CLI."""
import gzip,hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path

O=Path(__file__).resolve().parent;R=O.parents[3]

def test_build_check_apply_resume_unknown_and_undo(tmp_path):
    root=tmp_path/'DEV';root.mkdir();transfer=tmp_path/'uploaded TRANSFER';transfer.mkdir()
    m=json.loads((R/'08_DEPLOYMENT/RELEASES/schema-recovery-20261014-r1/release.json').read_bytes())
    for name in m['files']:
        dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/m['code_root']/name,dest)
    for name in ('core','pipeline','platform'):
        shutil.copytree(R/'02_BACKEND/lawrag'/name,root/'02_BACKEND/lawrag'/name,dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    spec=json.loads((O/'BUILD_SOURCE_BINDING.json').read_bytes())
    with zipfile.ZipFile(R/'04_EXPERIMENTS/ADR/ADR-0777-schema-recovery-main/artifacts/working-preintegration.zip') as z:
        for row in spec['files']:(root/row['path']).write_bytes(z.read(row['path']))
    before={row['path']:(root/row['path']).read_bytes() for row in spec['files']}
    manifest={'files':[{'path':n,'sha256':h,'bytes':(root/n).stat().st_size} for n,h in m['files'].items()]}
    (root/'CODE_MANIFEST.json').write_text(json.dumps(manifest))
    manifest_before=(root/'CODE_MANIFEST.json').read_bytes()
    env={**os.environ,'GENOS_DEV_ROOT':str(root),'PATH':str(R/'.venv/bin')+os.pathsep+os.environ['PATH'],
        'PYTHONPATH':str(root/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root)}
    transcript=[]
    def run(args,success=True):
        result=subprocess.run(args,cwd=transfer,env=env,text=True,capture_output=True,timeout=180)
        transcript.append({'args':args,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (O/'BUILD_TEST_TRANSCRIPT.json.gz').write_bytes(gzip.compress(json.dumps(transcript).encode(),mtime=0))
        assert (result.returncode==0)==success,result.stdout+result.stderr
        return result
    command=['bash',str(O/'GENOS_SCHEMA_BUILD_20261014_R1_RUN.txt')]
    target=root/spec['files'][0]['path'];saved=target.read_bytes();target.write_bytes(saved+b'\n# unknown\n')
    run(command+['apply'],False)
    assert all((root/n).read_bytes()==b for n,b in before.items() if root/n!=target)
    target.write_bytes(saved)
    run(command+['check']);run(command+['apply']);run(command+['apply']);run(command+['verify'])
    assert (root/'CODE_MANIFEST.json').read_bytes()==manifest_before
    run([str(R/'.venv/bin/python'),str(O/'build_runner.py'),str(root),
        str(R/'05_TESTS/REGRESSION/core/test_output_contract_build.py'),
        str(R/'05_TESTS/REGRESSION/core/test_recipe_runtime.py'),
        str(R/'05_TESTS/REGRESSION/core/test_recipe_output.py'),
        '--junitxml='+str(O/'INSTALLED_BUILD.xml')])
    backup=next((root/'TRANSFER/schema-build-r1').glob('backup-*'))
    after=target.read_bytes();target.write_bytes(after+b'\n# unknown\n')
    run(command+['undo',str(backup)],False);assert target.read_bytes()==after+b'\n# unknown\n'
    target.write_bytes(after);run(command+['undo',str(backup)])
    assert all((root/n).read_bytes()==b for n,b in before.items())
    assert (root/'CODE_MANIFEST.json').read_bytes()==manifest_before
    assert list(transfer.glob('schema-build-*.log'))
