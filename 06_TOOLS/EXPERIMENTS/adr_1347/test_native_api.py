"""Existing native ontology publication tests with the current provider wire fixture."""
from pathlib import Path
import importlib.util
import pytest
from conftest import term_glossary
from test_wiki_workspace import env, ws
import test_wiki_workspace_native as native

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('ontology_wire1347',ROOT/'06_TOOLS/EXPERIMENTS/adr_1332/test_repeat_scope.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
current_wire=prior.current_wire

@pytest.mark.parametrize('mode',['active','withdraw_during_assess','withdraw_on_replay'])
def test_native_ontology_delivery_revocation_and_replay(env,ws,tmp_path,term_glossary,monkeypatch,current_wire,mode):
    native.test_workspace_native_api_delivery_and_revocation(env,ws,tmp_path,term_glossary,monkeypatch,mode)
