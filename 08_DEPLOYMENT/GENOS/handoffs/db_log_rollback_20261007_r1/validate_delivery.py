"""Run the exact mailed TXT on prior code inventories using temporary DEV roots."""
from tempfile import TemporaryDirectory
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_DB_LOG_ROLLBACK_20261007_R1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    spec = json.loads((OUT/'PATCH_SPEC.json').read_bytes())
    folders = [ROOT/'08_DEPLOYMENT/GENOS/handoffs'/('query_latency_20261007_r'+str(i))
               for i in range(1, 5)]
    folders.append(ROOT/'08_DEPLOYMENT/GENOS/handoffs/system_logging_20261007_r1')
    report = []
    transcript = []
    for folder in folders:
        record = json.loads((folder/'HANDOFF.json').read_bytes())
        with TemporaryDirectory(prefix='db-log-rollback-') as temporary:
            dev = Path(temporary)/'DEV'
            dev.mkdir()
            with zipfile.ZipFile(folder/(record['version']+'.zip')) as archive:
                archive.extractall(dev)
            originals = {p.relative_to(dev).as_posix():p.read_bytes()
                         for p in dev.rglob('*') if p.is_file()}
            runtime = dev/'runtime/preserved.sqlite'
            runtime.parent.mkdir()
            runtime.write_bytes(b'synthetic-existing-runtime-do-not-touch')
            current = dev/'CURRENT.json'
            current.write_bytes(b'{"generation":"preserve"}\n')
            env = {**os.environ,'GENOS_DEV_ROOT':str(dev),'GENOS_QUERY_LATENCY':'1',
                   'GENOS_PYTHON_DIR':str(Path(sys.executable).parent)}
            env.pop('GENOS_GENERATION',None)
            def run(mode, *args, ok=True):
                result = subprocess.run(['bash',str(OUT/(NAME+'_RUN.txt')),mode,*args],
                    env=env,cwd=dev,capture_output=True,text=True)
                transcript.append(record['version']+' '+mode+' exit='+str(result.returncode)+'\n'
                                  +result.stdout+result.stderr)
                assert (result.returncode==0)==ok, transcript[-1]
                return result
            run('check')
            assert all((dev/n).read_bytes()==b for n,b in originals.items())
            run('apply')
            backup = next((dev/'TRANSFER/db-log-rollback-r1').glob('backup-*'))
            assert json.loads((backup/'receipt.json').read_bytes())['state']=='VERIFIED'
            run('apply')
            run('verify')
            installed = json.loads((dev/'CODE_MANIFEST.json').read_bytes())
            modified = set(installed['db_log_rollback']['modified_paths'])|{'CODE_MANIFEST.json'}
            assert len(modified)==33
            assert all((dev/n).read_bytes()==b for n,b in originals.items() if n not in modified)
            assert runtime.read_bytes()==b'synthetic-existing-runtime-do-not-touch'
            assert current.read_bytes()==b'{"generation":"preserve"}\n'
            # Verify the applied ZIP against the same committed Git checkout,
            # using the real gate's comparison; no remotes or model requests.
            subprocess.run(['git','init','-q',str(dev)],check=True)
            subprocess.run(['git','-C',str(dev),'add','-f','--',*originals],check=True)
            subprocess.run(['git','-C',str(dev),'-c','user.name=Fixture',
                '-c','user.email=fixture@example.invalid','commit','-qm','Fixture'],check=True)
            gate_path=dev/'06_TOOLS/COMMANDS/genos_release_gate.py'
            loader=importlib.util.spec_from_file_location('gate_fixture',gate_path)
            gate=importlib.util.module_from_spec(loader);loader.loader.exec_module(gate)
            comparison=gate.compare_zip_to_checkout(backup/'APPLIED_CODE.zip',dev)
            assert comparison['code_files']==len(originals)-1
            # Unknown later bytes must block undo before any file is restored.
            module=dev/'02_BACKEND/semantic_runtime/query_latency.py'
            patched=module.read_bytes();module.write_bytes(patched+b'\n# unknown later edit\n')
            before_manifest=(dev/'CODE_MANIFEST.json').read_bytes()
            run('undo',str(backup),ok=False)
            assert (dev/'CODE_MANIFEST.json').read_bytes()==before_manifest
            module.write_bytes(patched)
            run('undo',str(backup))
            assert all((dev/n).read_bytes()==b for n,b in originals.items())
            # A corrupt target must be preserved on check and apply.
            module.write_bytes(originals[module.relative_to(dev).as_posix()]+b'\n# unknown\n')
            run('check',ok=False)
            run('apply',ok=False)
            assert (dev/'CODE_MANIFEST.json').read_bytes()==originals['CODE_MANIFEST.json']
            assert len(list((dev/'TRANSFER/db-log-rollback-r1').glob('backup-*')))==1
            report.append({'basis':record['version'],'checks':10,'passed':True,
                           'unchanged_code_files':len(originals)-33,
                           'same_committed_checkout_zip_comparison':comparison,
                           'runtime_and_current_preserved':True})
    (OUT/'DELIVERY_TESTS.log').write_text('\n'.join(transcript))
    validation={'status':'PASS','contract_tests':38,'delivery_cases':len(report)*10,
        'basis_results':report,'external_model_calls':0,
        'field_generation_gate':'NOT_RUN','field_deployed':False,
        'scope':'deterministic contract and exact attachment application checks'}
    (OUT/'VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PASS','contract_tests':38,'delivery_cases':len(report)*10}))


if __name__ == '__main__':
    main()
