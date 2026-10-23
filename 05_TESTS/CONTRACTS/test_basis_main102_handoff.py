"""Exact sent MAIN102 plus packaged CLI: synthetic service, zero model calls."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

from test_authority import generation

R = Path(__file__).resolve().parents[2]
A = R/'09_ARTIFACTS/AUDITS/20261023-basis-main102'
P = R/'08_DEPLOYMENT/GENOS/handoffs/basis_main102_20261023_r1'
NAME = 'GENOS_BASIS_MAIN102_20261023_R1'

def test_main102_exact_zip_service_plan_preservation_and_guards(tmp_path, generation):
    from lawrag.pipeline.fulltext_stage import derive
    from lawrag.pipeline.search_selection import plan, activate
    selected = tmp_path/'generation'
    derive(generation, selected, workers=1)
    activate(plan(selected, latest=True))
    root = tmp_path/'checkout'
    with zipfile.ZipFile(R/'08_DEPLOYMENT/GENOS/handoffs/main95_comparison_scope_20261020_r1/code.zip') as z:
        z.extractall(root)
        for n, src in json.loads((A/'TEST_SOURCE_MAP.json').read_text()).items():
            dest=root/n
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(z.read(n) if src=='MAIN95_ZIP' else (R/src).read_bytes())
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    (root/'01_DATA').mkdir(exist_ok=True)
    runtime=tmp_path/'runtime'
    runtime.mkdir()
    old=runtime/'basis-batch/pilot-review-user-all'
    old.mkdir(parents=True)
    (old/'OLD_FAILURE.txt').write_text('preserve old failure and budget')
    cfg={'schema_version':'genos-serving-paths-v1','selection':'operator-fixed',
         'generation':str(selected),'runtime':str(runtime),
         'generation_manifest_sha256':hashlib.sha256((selected/'manifest.json').read_bytes()).hexdigest()}
    (root/'00_SYSTEM/GENOS_SERVING_PATHS.json').write_text(json.dumps(cfg))
    transfer=tmp_path/'actual-upload-folder'
    transfer.mkdir()
    kit=transfer/NAME
    with zipfile.ZipFile(P/(NAME+'.zip')) as z:
        assert all(Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
        z.extractall(kit)
    shutil.copyfile(P/(NAME+'_RUN.txt'),transfer/(NAME+'_RUN.txt'))
    spec=json.loads((kit/'PACKAGE.json').read_text())
    names=[*spec['payload'],'06_TOOLS/pipeline.py']
    before={n:(root/n).read_bytes() if (root/n).exists() else None for n in names}
    base_before={n:(root/n).read_bytes() for n in spec['required_base']}
    # Default DEV is a symlink in GENOS; use an explicit test alias, not HOME mutation.
    alias=tmp_path/'DEV'
    alias.symlink_to(root,target_is_directory=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('GENOS_','SEMANTIC_','LEGAL_AGENT_','LAWRAG_','WORKFLOW_','SOURCE_PROVIDER_','PYTHON'))}
    env.update(PATH=str(R/'.venv/bin')+':'+env['PATH'],PYTHONDONTWRITEBYTECODE='1',GENOS_BASIS_ROOT=str(alias))
    trace=[]
    def call(action,*args,rc=0):
        out=subprocess.run(['bash',str(transfer/(NAME+'_RUN.txt')),action,*args],cwd=transfer,
                           env=env,text=True,capture_output=True,timeout=60)
        trace.append({'action':action,'args':args,'exit':out.returncode,'output':out.stdout+out.stderr})
        (A/'COMMAND_TRACE.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
        assert out.returncode==rc,trace[-1]
        return out
    call('check')
    assert before=={n:(root/n).read_bytes() if (root/n).exists() else None for n in names}
    call('apply'); call('apply'); call('install-status'); call('paths'); call('jobs')
    call('plan')
    job=runtime/'basis-batch/pilot-review-user-main102-links-20261023-r1'
    saved={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*PLAN.json')}
    assert saved
    call('plan')
    assert saved=={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*PLAN.json')}
    call('status');call('report')
    assert (transfer/'basis-report-main102-links-20261023-r1/INDEX.html').is_file()
    call('start',rc=1)
    assert 'GENOS' in trace[-1]['output'] or 'model' in trace[-1]['output']
    call('resume',rc=1)
    assert saved=={str(p.relative_to(job)):p.read_bytes() for p in job.rglob('*PLAN.json')}
    assert not (runtime/'basis-links/authority.sqlite').exists()
    assert (old/'OLD_FAILURE.txt').read_text()=='preserve old failure and budget'
    assert base_before=={n:(root/n).read_bytes() for n in spec['required_base']}
    # Exact MAIN102 and command tampering both stop before model/source execution.
    target=root/'02_BACKEND/semantic_runtime/basis_links/resolver.py'
    data=target.read_bytes();target.write_bytes(data+b'\n# drift\n')
    call('start',rc=1)
    assert 'MAIN102' in trace[-1]['output']
    target.write_bytes(data)
    target=root/'06_TOOLS/COMMANDS/basis_work.py'
    data=target.read_bytes();target.write_bytes(data+b'\n# drift\n')
    call('start',rc=1);call('rollback',rc=1)
    target.write_bytes(data)
    call('rollback');call('rollback')
    assert before=={n:(root/n).read_bytes() if (root/n).exists() else None for n in names}
    assert (old/'OLD_FAILURE.txt').exists()
    assert len(list((transfer/'basis-main102-logs').glob('*.log.exit')))==len(trace)
