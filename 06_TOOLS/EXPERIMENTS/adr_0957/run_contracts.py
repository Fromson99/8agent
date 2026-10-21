"""Load the isolated candidate only; run one bounded pytest process."""
import sys,resource
sys.dont_write_bytecode=True
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
stage=ROOT/'04_EXPERIMENTS/ADR/ADR-0957-multiturn-structured-scope/artifacts/code'
sys.path[:0]=[str(stage/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS')]
import semantic_runtime, semantic_runtime.legal_agent
assert Path(semantic_runtime.__file__).resolve().is_relative_to(stage)
# Test fixtures select the same staged contracts as the imported runtime.
import semantic_runtime.app as app_module
original_create=app_module.create_app
def create(*args,**kwargs):
    if Path(kwargs.get('contracts_root',ROOT)).resolve()==ROOT:
        kwargs['contracts_root']=stage
    return original_create(*args,**kwargs)
app_module.create_app=create
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
