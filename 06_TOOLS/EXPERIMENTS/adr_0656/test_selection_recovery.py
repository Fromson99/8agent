import pytest
from test_bounded_source_selection import record
from semantic_runtime.legal_agent.source_selection import select_sources, digest

@pytest.mark.parametrize('recover',[True,False])
def test_empty_first_choice_reads_real_text_without_forcing_irrelevant_sources(recover):
    source=record();before=digest(source);calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(data)
        if len(calls)==1:return {'issues':['승인'],'choices':[]}
        assert data['selection_deviation']['reason']=='EMPTY_INITIAL_SELECTION'
        assert data['candidate_original_excerpts'][0]['excerpts'][0]['text']==source['evidence'][0]['spans'][0]['text']
        return {'issues':['승인'],'choices':[{'id':'C001','reason':'원문 확인'}] if recover else []}
    result=select_sources('승인 대상은?',source,invoke,remaining_seconds=60)
    assert result['final_ids']==(['0'] if recover else [])
    assert len(calls)==2 and digest(source)==before
    assert any(x['phase']=='empty-recovery' for x in result['actual_selector_excerpts'])
