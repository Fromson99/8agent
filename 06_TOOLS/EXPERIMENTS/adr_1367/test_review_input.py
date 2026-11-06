from copy import deepcopy
from pathlib import Path
import gzip
import importlib.util
import json
import pytest
from conftest import term_glossary
from semantic_runtime.legal_agent import bounded_source_session, wire_schema

ROOT = Path(__file__).resolve().parents[3]


def test_recorded_entry_keeps_question_before_issue_classification():
    saved = ROOT/'04_EXPERIMENTS/ADR/ADR-1351-integration-oneclick-provider-matrix/artifacts/public-live/B03-03-parasail/raw/call-001/request.json.gz'
    with gzip.open(saved, 'rt') as f:
        original = json.load(f)['response_format']['json_schema']['schema']
    projected, _ = wire_schema.discriminator_first(original)
    def issue_orders(value):
        if isinstance(value, dict):
            fields = value.get('properties', {})
            if {'question', 'subject', 'kind', 'request_quote'} <= fields.keys():
                yield list(fields)
            for child in value.values():
                yield from issue_orders(child)
        elif isinstance(value, list):
            for child in value:
                yield from issue_orders(child)
    assert projected == original
    assert list(issue_orders(projected)) == list(issue_orders(original)) == [
        ['id', 'question', 'subject', 'kind', 'request_quote']]


def test_referenced_union_choices_and_literal_values_keep_their_contracts():
    def row(choices):
        return {'type':'object','properties':{'text':{'type':'string'},'choice':{'enum':choices}},
                'required':['text','choice']}
    schema = {'$defs':{'D1':row(['A','B']),'D2':row(['C']),'other':row(['X'])},
              'anyOf':[{'$ref':'#/$defs/D1'},{'$ref':'#/$defs/D2'}],
              'default':{'anyOf':[{'$ref':'#/$defs/other'}]}}
    saved = deepcopy(schema)
    wire, changes = wire_schema.discriminator_first(schema)
    assert wire == saved == schema and changes == 2
    assert list(wire['$defs']['D1']['properties']) == list(wire['$defs']['D2']['properties']) == ['choice','text']
    assert list(wire['$defs']['other']['properties']) == ['text','choice']
    assert wire_schema.discriminator_first(wire)[1] == 0


@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice'])
def test_actual_intent_and_assessment_inputs(tmp_path,term_glossary,monkeypatch,fault):
    seen = []
    original = bounded_source_session._Gateway.request
    def capture(self, phase, view, schema_name, **kwargs):
        request = original(self, phase, view, schema_name, **kwargs)
        stage = view.get('source_stage', '')
        if stage.startswith('request-entry'):
            assert 'TIMING' in request['messages'][0]['content']
            seen.append('entry')
        elif stage.startswith('memory-assess'):
            assert 'reentry_budget' not in view
            seen.append('assess')
        return request
    monkeypatch.setattr(bounded_source_session._Gateway,'request',capture)
    spec = importlib.util.spec_from_file_location('prior_scope1366',ROOT/'06_TOOLS/EXPERIMENTS/adr_1366/test_scope.py')
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    prior.test_actual_api_scope_guidance_and_correct_generation_contract(tmp_path,term_glossary,monkeypatch,fault)
    assert 'entry' in seen and 'assess' in seen
