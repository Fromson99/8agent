from common import *
import sys
C=ROOT/read(ART/'stage.json')['roots']['candidate'];T=C/'05_TESTS/CONTRACTS'
p=T/'test_selected_connection_scope_api.py';s=p.read_text();s=s.replace('selected_connection_scope=True,answer_first=False)','selected_connection_scope=True,answer_first=False,answer_progress_control=False)');p.write_text(s)
s=s.replace('def test_actual_api_reads_link_or_structural_target_and_reuses_request','def test_progress_actual_api_reads_link_or_structural_target_and_reuses_request').replace('answer_progress_control=False','answer_progress_control=True')
s=s.replace('            self.reference_calls = 0','            self.reference_calls = 0\n            self.progress_turns = 0')
s=s.replace("            self.calls.append(phase)\n            if phase",'''            self.calls.append(phase)
            from test_legal_agent_double_harness import wire as encode
            def wire(value):
                if '-read-choice' in phase:
                    self.progress_turns += 1
                    terminal=value['choice']=='FINISH'
                    value['answer_progress']={'status':'ANSWERABLE' if terminal else 'NEEDS_SOURCE',
                        'answer_so_far':'확보한 적용 기준' if view['sources'] else '',
                        'basis_refs':[s['id'] for s in view['sources']][:4],
                        'material_need':'' if terminal else '현재 질문의 필수 기준 원문',
                        'next_answer_change':'' if terminal else '적용 기준의 내용을 확인한다.',
                        'previous_effect':'INITIAL' if self.progress_turns==1 else 'NEED_NARROWED'}
                return encode(value)
            if phase''')
(T/'test_answer_progress_api.py').write_text(s)
text='''from copy import deepcopy
import pytest
from semantic_runtime.legal_agent import connection_scope as cs, decision_projection as dp
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from test_selected_connection_scope import fixture

@pytest.mark.parametrize('change',['extend','different_structure','different_exclusion','remove','changed_bytes','bad_hash'])
def test_same_selected_structure_refresh_preserves_original_bounds(monkeypatch,change):
    inv,add=fixture(monkeypatch);page=add('a','s',6,[6]);data={'sources':[page]}
    old=cs.candidates(inv,data)[0][0];cs.accept(inv,old,data,'최종 선택 범위')
    before=deepcopy(cs.current(inv));new=deepcopy(old)
    extra=deepcopy(new['members'][0]['spans'][0]);extra['block_id']='7';extra['text']='추가 원문';extra['span_hash']=digest('추가 원문')
    new['members'][0]['spans'].append(extra)
    if change=='different_structure':new['structural_selection']['unit_id']='7'
    if change=='different_exclusion':new['structural_selection']['excluded_unit_ids']=['7']
    if change=='remove':new['members'][0]['spans']=new['members'][0]['spans'][1:]
    if change=='changed_bytes':new['members'][0]['spans'][0]['text']+='변조'
    new['id']=digest({k:v for k,v in new.items() if k!='id'})
    if change=='bad_hash':
        new['id']='invalid'
        with pytest.raises(ContractError):cs.refresh_selected_delivery(inv,[(new,['E1'])],before)
        assert inv.p['selected_connection_scope']==before
        return
    after=cs.refresh_selected_delivery(inv,[(new,['E1'])],before)
    if change=='extend':
        assert after['scope']==new and after['scope']['structural_selection']==old['structural_selection']
        assert after['refresh_origin']=='ACQUIRED_WITHIN_SELECTED_STRUCTURE'
        assert after['previous_scope_id']==old['id']
        count=len(inv.p['connection_scope_history'])
        assert cs.refresh_selected_delivery(inv,[(new,['E1'])],after)==after
        assert len(inv.p['connection_scope_history'])==count
    else:assert after==before and inv.p['selected_connection_scope']==before

def test_last_two_investigation_calls_keep_progress_and_narrow_choice(monkeypatch):
    from test_answer_progress import fixture,read_choice
    inv,d,a,events,payloads=fixture(monkeypatch,read_choice())
    inv.s.repo.budget=lambda:dict(model_limit=5,model_reserved=0,finalization_reserve=3)
    result=dp.choose_read(inv,d,a,'test')
    assert result['next_action']=='READ_ARTICLES' and len(payloads)==1
    assert any(e[0]=='ANSWER_PROGRESS_REVIEWED' for e in events)
'''
name='05_TESTS/CONTRACTS/test_connection_scope_refresh.py';(C/name).write_text(text)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.register_file(C.parent,name,upstream_state='absent')
