from pathlib import Path
import hashlib,json,os
import pytest
ROOT=Path(os.environ['WORKFLOW_TEST_CODE_ROOT'])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
@pytest.mark.parametrize('version',['5.0.0','6.0.0'])
@pytest.mark.parametrize('stage',['select','retrieve','assemble','answer'])
def test_grant_dependency(version,stage):
    n=f'02_BACKEND/ENGINES/legal_agent/{version}/{stage}.json';engine=read(ROOT/n)
    grant='00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'
    assert engine['files'][grant]==sha(ROOT/grant)
    config=read(ROOT/'00_SYSTEM/PIPELINE.json');declared=[e for e in config['engines'].values() if e['manifest']==n]
    assert declared and all(e['sha256']==sha(ROOT/n) for e in declared)
    for p,h in engine['files'].items():assert sha(ROOT/p)==h,p
@pytest.mark.parametrize('workflow',['risk_team_compare_workflow','internal_basis_discovery_workflow'])
def test_workflow_package_binding(workflow):
    config=read(ROOT/'00_SYSTEM/PIPELINE.json');d=next(d for d in config['workflows']['registered'] if d['id']==workflow)
    assert sha(ROOT/d['manifest'])==d['sha256']
    m=read(ROOT/d['manifest']);assert m['version']==d['version']
    for p,h in m['files'].items():assert sha(ROOT/'02_BACKEND/workflow'/p)==h,p
