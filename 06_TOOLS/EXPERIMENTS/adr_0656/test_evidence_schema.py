import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent.memory_rag import ASSESS,evidence_schema,NativeExecution
from semantic_runtime.legal_agent.corrected_memory import MemoryError

def test_fact_label_cannot_be_cited_as_legal_source():
 sources=[{'source_id':'article:one','text':'원문 규정'}];schema=evidence_schema(ASSESS,sources)
 value={'claims':[{'text':'법인 사실에 적용한 판단','source_id':'current_facts','quote':'대상: 법인'}],'limitations':[]}
 with pytest.raises(ValidationError):validate(value,schema)
 value['claims'][0].update(source_id='article:one',quote='원문 규정');validate(value,schema)
 assert 'enum' not in ASSESS['properties']['claims']['items']['properties']['source_id']

def test_quote_error_identifies_exact_claim_and_source():
 e=NativeExecution(None,None,None,None)
 with pytest.raises(MemoryError,match=r'claim\[0\].*article:one'):
  e.verify_claims([{'text':'판단','source_id':'article:one','quote':'허위 인용'}],[{'source_id':'article:one','text':'실제 원문'}])
