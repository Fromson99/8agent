import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]

@pytest.mark.parametrize('prior_r2',[False,True])
def test_exact_handoff_applies_only_modules_and_pins_and_refuses_drift(tmp_path,prior_r2):
    binding=json.loads((HERE/'BASE_BINDING.json').read_text())
    manifest=json.loads((ROOT/binding['manifest_path']).read_text())
    base=ROOT/manifest['code_root'];checkout=tmp_path/'DEV'
    shutil.copytree(base,checkout)
    subprocess.run(['git','init','-q'],cwd=checkout,check=True)
    subprocess.run(['git','add','.'],cwd=checkout,check=True)
    subprocess.run(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],cwd=checkout,check=True)
    if prior_r2:
        prior=HERE.with_name('vector_silver_20261029_r2')
        subprocess.run(['bash',str(prior/'GENOS_COMPACT_APPLY.txt'),'apply',str(checkout)],cwd=prior,check=True,capture_output=True)
        subprocess.run(['git','add','.'],cwd=checkout,check=True)
        subprocess.run(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','r2 fixture'],cwd=checkout,check=True)
    def run(mode):
        return subprocess.run(['bash',str(HERE/'GENOS_COMPACT_APPLY.txt'),mode,str(checkout)],cwd=HERE,capture_output=True,text=True)
    before={n:hashlib.sha256((checkout/n).read_bytes()).hexdigest() for n in manifest['files']}
    checked=run('check');assert checked.returncode==0,checked.stdout+checked.stderr
    applied=run('apply');assert applied.returncode==0,applied.stdout+applied.stderr
    patch=json.loads((HERE/'genos_patch/PATCH_MANIFEST.json').read_text())
    changed=[]
    for n,h in before.items():
        actual=hashlib.sha256((checkout/n).read_bytes()).hexdigest()
        if actual!=h:changed.append(n)
        if n in patch['code']:assert actual==patch['code'][n]['after']
    assert len(changed)>2
    assert all(n in patch['code'] or n.startswith('02_BACKEND/ENGINES/') or n=='00_SYSTEM/PIPELINE.json' for n in changed)
    assert run('check').returncode==0
    assert len(list(tmp_path.glob('vector-compact-backup-*/RECEIPT.json')))==(2 if prior_r2 else 1)
    target=checkout/next(iter(patch['code']));target.write_bytes(target.read_bytes()+b'\n# other work\n')
    saved=target.read_bytes();failed=run('check')
    assert failed.returncode!=0 and target.read_bytes()==saved
