"""A model-selected original keeps its identity across v6/v7/v8 wire expansion."""
import pytest
from test_focused_input_modality import tree, session, focused
from test_investigation_completion_adr0678 import apply
from semantic_runtime.legal_agent import decision_projection as dp, completion_contracts as cc

@pytest.mark.parametrize('version',[cc.V6,cc.V7,cc.V8])
@pytest.mark.parametrize('relation',['DIRECT','DEPENDENCY'])
def test_selected_original_compiles_into_requested_contract(session, version, relation):
    native,_=session
    inv=focused(native)
    inv.s.profile['candidate_navigation']['completion_policy_version']=version
    inv.p['completion_contract']=version
    inv.modern=True
    selected=[]
    def invoke(system,payload,schema,phase,timeout):
        refs=[s for s in payload['sources'] if s.get('text')]
        mode=relation if refs else 'DIRECT'
        choice='READ' if payload['read_candidates'] else payload['tool_options'][0]['choice']
        target=(payload['read_candidates'][0]['target'] if choice=='READ' else
                next(o['target'] for o in payload['tool_options'] if o['choice']==choice))
        row={'target':target,'issue_id':payload['issues'][0]['id'],
             'missing_need':'질문한 승인 기준의 실제 원문 확인','relation':mode,
             'source_ref':refs[0]['id'] if mode=='DEPENDENCY' else None}
        selected.append(row)
        if choice=='READ':return {'choice':'READ','selections':[row]}
        result={'choice':choice,**row}
        branch=next(b for b in schema['anyOf'] if b['properties']['choice'].get('const')==choice)
        if 'queries' in branch['properties']:result['queries']=['승인 예외']
        return result
    inv.invoke=invoke
    data,actions=inv.view()
    value=dp.choose_read(inv,data,actions,'contract-version-1')
    if relation=='DEPENDENCY' and not data['sources']:
        apply(inv,value,data,actions)
        data,actions=inv.view()
        value=dp.choose_read(inv,data,actions,'contract-version-2')
    assert selected[-1]['relation']==relation
    row=value['exploration'][0]
    assert row['target']==selected[-1]['target'] and row['issue_id']==selected[-1]['issue_id']
    if version==cc.V8:
        assert row['source_ref']==selected[-1]['source_ref'] and row['source_quote']==''
    else:
        assert 'source_ref' not in row
        if relation=='DEPENDENCY':
            original=next(s for s in data['sources'] if s['id']==selected[-1]['source_ref'])
            assert row['source_quote']==original['text']
        else:assert row['source_quote']==''
    inv.validate(value,data,actions)
