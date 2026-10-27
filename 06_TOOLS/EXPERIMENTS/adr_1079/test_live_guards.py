"""Pure admission failures: no model, API service or corpus loading."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest


@pytest.fixture
def runner(tmp_path,monkeypatch):
    here=Path(__file__).parent
    monkeypatch.syspath_prepend(str(here))
    for name in ('common','replay_transport','profile_capture','run_case'):
        spec=importlib.util.spec_from_file_location(name,here/(name+'.py'))
        module=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,module);spec.loader.exec_module(module)
    runner=sys.modules['run_case'];monkeypatch.setattr(runner,'ROOT',tmp_path)
    monkeypatch.setattr(runner,'ART',tmp_path/'audit');runner.ART.mkdir()
    return runner


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value))


def ready(runner):
    root=runner.ROOT
    save(runner.ART/'design-freeze.json',{'frozen':True})
    active=root/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';save(active,{'generation':105})
    evidence=root/'service-selection.json';save(evidence,{'selected':105})
    value={'schema_version':'adr1079-main-selection-binding-v1','verified':True,
        'actual_service_verified':True,'main_generation':105,
        'design_freeze_sha256':runner.sha(runner.ART/'design-freeze.json'),
        'active_release_sha256':runner.sha(active),
        'evidence':[{'path':'service-selection.json','sha256':runner.sha(evidence)}]}
    save(runner.ART/'main-selection-binding.json',value)
    return value


def test_missing_main_receipt_blocks_before_execution(runner):
    with pytest.raises(runner.IntegrityFailure,match='selection receipt'):
        runner.verify_main_ready({})


@pytest.mark.parametrize('field,value',[('verified',False),('actual_service_verified',False),
    ('main_generation',103),('design_freeze_sha256','bad')])
def test_main_or_experiment_mismatch_blocks(runner,field,value):
    receipt=ready(runner);receipt[field]=value
    save(runner.ART/'main-selection-binding.json',receipt)
    with pytest.raises(runner.IntegrityFailure):runner.verify_main_ready({})


@pytest.mark.parametrize('path',['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json','service-selection.json'])
def test_changed_pointer_or_evidence_blocks(runner,path):
    ready(runner);save(runner.ROOT/path,{'changed':True})
    with pytest.raises(runner.IntegrityFailure):runner.verify_main_ready({})


def test_verified_selection_allows_same_frozen_experiment(runner):
    receipt=ready(runner)
    assert runner.verify_main_ready({})==receipt
