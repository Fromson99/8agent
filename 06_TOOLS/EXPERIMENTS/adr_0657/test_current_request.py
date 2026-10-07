from types import SimpleNamespace
from semantic_runtime.legal_agent.memory_rag import NativeExecution

def test_assessment_receives_unabridged_current_scope_correction():
    source = {'source_id':'article:one','text':'금지 대상에서 제외한다.'}
    utterance = '지위를 정정합니다. 금지 대상인지만 판단하고 다른 영업 요건은 미확인입니다.'
    calls = []
    def invoke(system, data, schema, phase):
        calls.append(data)
        return {'claims':[{'text':'이 금지 대상에서 제외됨','source_id':'article:one','quote':source['text']}], 'limitations':['다른 영업 요건은 미확인']}
    host = SimpleNamespace(question=lambda state:'과거의 더 넓은 질문', verify=lambda _:None, invoke=invoke)
    session = SimpleNamespace(work=SimpleNamespace(event=lambda *args:None))
    execution = NativeExecution(host, session, {}, {})
    execution.selected_originals = lambda _: [source]
    result = execution.stage('ASSESS', {'facts':[]}, {'READ':{'payload':{}},'SELECT':{'payload':{'final_ids':['article:one']}}}, utterance, 'text')
    assert calls[0]['current_request'] == utterance
    assert calls[0]['question'] == '과거의 더 넓은 질문'
    assert result['limitations'] == ['다른 영업 요건은 미확인']
    assert len(calls) == 1
