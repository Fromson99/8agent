"""Prepare fixture-only sample queries with the captured build compiler.

The original tests still exercise native CLOB/key equality and rejection. These
sample table queries are intentionally absent from the production catalogue.
"""
from pathlib import Path
import importlib.util,os,pytest
from test_oracle_lookup_overflow import *
from semantic_runtime.oracle_query_plans import PLANS
@pytest.fixture(autouse=True)
def fixture_plans(monkeypatch):
 root=Path(os.environ['LOOP_TEST_CODE_ROOT'])
 spec=importlib.util.spec_from_file_location('prepared_fixture_build',root/'06_TOOLS/maintenance/prepare_oracle_queries.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 for field in ('id','source_id','target'):
  key,entry=module.prepare('SELECT '+field+' FROM sample WHERE '+field+'=?');monkeypatch.setitem(PLANS,key,entry)
 key,entry=module.prepare("SELECT target FROM sample WHERE target='sample'");monkeypatch.setitem(PLANS,key,entry)
