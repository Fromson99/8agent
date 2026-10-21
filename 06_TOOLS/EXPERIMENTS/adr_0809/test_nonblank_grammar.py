import re
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent.model_contract import genos_wire_schema

@pytest.mark.parametrize('text',['',' ','\t\r\n','상','두 규정의 승인 기준을 확인한다.','\n 원문을 확인한다.\n','A B','① 승인한다.\n② 보고한다.','🙂','\u00a0','\u200b'])
def test_nonblank_full_match_grammar_matches_canonical_search(text):
    canonical={'type':'string','pattern':r'\S','maxLength':512}
    wire=genos_wire_schema(canonical)
    assert bool(re.fullmatch(wire['pattern'],text))==Draft202012Validator(canonical).is_valid(text)
    assert canonical['pattern']==r'\S'

def test_unrelated_patterns_and_literal_source_data_unchanged():
    schema={'type':'object','properties':{'id':{'type':'string','pattern':'^[A-Z][0-9]+$'}},'const':{'pattern':r'\S'}}
    assert genos_wire_schema(schema)==schema
