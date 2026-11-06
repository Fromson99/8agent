from pathlib import Path
import importlib.util
import pytest
from conftest import term_glossary
from semantic_runtime.legal_agent import bounded_source_session
from semantic_runtime.legal_agent.connection_scope import FINISH_GUIDANCE

@pytest.mark.parametrize('fault', [None,'scope_twice'])
def test_single_scope_instruction_in_actual_navigation_and_final_review(tmp_path,term_glossary,monkeypatch,fault):
    seen = set()
    original = bounded_source_session._Gateway.request
    def inspect(self, phase, view, name, **kwargs):
        request = original(self,phase,view,name,**kwargs)
        stage = view.get('source_stage','')
        if '-read-choice' in stage or stage.startswith('memory-assess'):
            prompt = request['messages'][0]['content']
            assert prompt.count(FINISH_GUIDANCE)==1
            assert '대상 원문이 다른 규정의 요건에 의존하면' in FINISH_GUIDANCE
            seen.add('assessment' if stage.startswith('memory-assess') else 'navigation')
        return request
    monkeypatch.setattr(bounded_source_session._Gateway,'request',inspect)
    path = Path(__file__).resolve().parents[1]/'adr_1367/test_review_input.py'
    spec = importlib.util.spec_from_file_location('input_fixture_1367',path)
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    prior.test_actual_intent_and_assessment_inputs(tmp_path,term_glossary,monkeypatch,fault)
    assert seen=={'navigation','assessment'}
