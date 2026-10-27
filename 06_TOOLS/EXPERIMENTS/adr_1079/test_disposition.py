import importlib.util
from pathlib import Path
import sys


def test_completion_and_transition_are_not_quality(monkeypatch):
    here=Path(__file__).parent
    monkeypatch.syspath_prepend(str(here))
    for name in ('common','replay_transport','profile_capture','run_case','extract_timing','finish_live'):
        spec=importlib.util.spec_from_file_location(name,here/(name+'.py'))
        module=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,name,module);spec.loader.exec_module(module)
    choose=sys.modules['finish_live'].disposition
    assert choose(True,True,True)=='TRANSITION_VERIFIED'
    assert choose(True,True,False)=='NOT_OBSERVED'
    assert choose(True,False,True)=='FAILED'
    assert choose(False,False,False)=='FAILED'
