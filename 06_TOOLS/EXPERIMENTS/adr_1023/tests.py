from common import *
import sys
C=ROOT/read(ART/'stage.json')['roots']['candidate'];base=C/'02_BACKEND/semantic_runtime/legal_agent';tests=C/'05_TESTS/CONTRACTS'
p=base/'decision_projection.py';t=p.read_text().replace("    walk(data.get('references', {}).get('dependency_cards', []))","    walk(data.get('references', {}).get('dependency_cards', []))\n    walk(data.get('references', {}).get('previously_inspected_cards', []))");t=t.replace('FOLLOW_CONNECTION은 필요한 원문의 조건·예외·산식·준용 대상 연결을 연다.','connection_action_history는 실행한 범위·이유·실제 결과다. 이미 확인한 연결은 previously_inspected_cards에서 필요한 원문만 바로 읽는다. 범위를 번갈아 재조회하지 않는다.\\nFOLLOW_CONNECTION은 아직 확인하지 않은 필요한 범위의 연결을 연다.');p.write_text(t)
p=base/'connection_scope.py';t=p.read_text().replace('    for scope, refs in scope_choices:\n',"    shown_directories = set()\n    for scope, refs in sorted(scope_choices, key=lambda row: row[0]['id'] != selected_id):\n",1).replace("        if visible:\n            shown = inline_cards", "        if directory_key(scope) in shown_directories:visible = []\n        if visible:\n            shown_directories.add(directory_key(scope))\n            shown = inline_cards",1);p.write_text(t)
p=tests/'test_connection_cycle_guard.py'
p.write_text('''from copy import deepcopy
import json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import connection_scope as cs, unit_relations as rel
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_final_connection_selection import setup


def scopes(inv,data):
    rows=cs.candidates(inv,data)
    return [next(s for s,_ in rows if s['structural_selection'].get('unit_id')==u) for u in ('6','9')]

@pytest.mark.parametrize('status',['COMPLETE','PARTIAL','FAILED'])
def test_a_b_a_b_and_resume_never_reopen_same_directory(monkeypatch,status):
    inv,data=setup(monkeypatch);a,b=scopes(inv,data);calls=[]
    def lookup(i,s):
        calls.append(s['id'])
        return dict(status=status,groups=[],connection_count=0,absence_proven=False)
    monkeypatch.setattr(cs,'preview',lookup)
    for s in (a,b):
        cs.reject_repeated_follow(inv,s)
        cs.accept(inv,s,data,'해당 범위의 연결 필요')
        cs.inspect_directory(inv,s)
    for target in (a,b,a,b):
        actions={};cs.offer_choices(inv,data,actions)
        assert not any(x['identity'].get('connection_scope',{}).get('id')==target['id'] for x in actions.values())
        with pytest.raises(ProposalError,match='already inspected'):cs.reject_repeated_follow(inv,target)
        assert not data['connection_review']['required_before_finish']
        assert all(not h['repeat_available'] for h in data['connection_action_history'])
        inv.p=json.loads(json.dumps(inv.p))  # persisted checkpoint roundtrip
        assert cs.inspect_directory(inv,target)['status']==status
    assert calls==[a['id'],b['id']]
    assert {h['scope_id'] for h in data['connection_action_history']} >= {a['id'],b['id']}


def test_new_scope_bytes_allow_lookup_but_equivalent_ui_scope_does_not(monkeypatch):
    inv,data=setup(monkeypatch);a,b=scopes(inv,data)
    monkeypatch.setattr(cs,'preview',lambda *a:dict(status='COMPLETE',groups=[],connection_count=0))
    cs.accept(inv,a,data,'읽음');cs.inspect_directory(inv,a)
    alias=deepcopy(a);alias['label']='다른 화면의 동일 원문';alias['id']=digest({k:v for k,v in alias.items() if k!='id'})
    with pytest.raises(ProposalError):cs.reject_repeated_follow(inv,alias)
    expanded=deepcopy(a);expanded['members'][0]['spans']+=b['members'][0]['spans'];expanded['id']=digest({k:v for k,v in expanded.items() if k!='id'})
    cs.reject_repeated_follow(inv,expanded)
    assert cs.directory_receipt(inv,expanded) is None


@pytest.mark.parametrize('change',['hash','binding','acl','source'])
def test_receipt_mutation_never_authorizes_cached_directory(monkeypatch,change):
    inv,data=setup(monkeypatch);a,_=scopes(inv,data)
    monkeypatch.setattr(cs,'preview',lambda *a:dict(status='COMPLETE',groups=[],connection_count=0))
    cs.accept(inv,a,data,'확인');cs.inspect_directory(inv,a)
    if change=='hash':inv.p['connection_directories'][cs.directory_key(a)]['result']['connection_count']=99
    if change=='binding':inv.p['binding']['generation']='other'
    if change=='acl':inv.s.scope=[]
    if change=='source':inv.s.tools.sources[a['members'][0]['source_id']]['document_id']='other'
    with pytest.raises(ContractError):cs.inspect_directory(inv,a)


def test_cached_directory_updates_acquisition_without_another_query(monkeypatch):
    inv,data=setup(monkeypatch);a,_=scopes(inv,data);inv.read_records=lambda:{}
    group={'anchor':{'source_id':'article92','document_id':'d'},'target':{'source_id':'article97','document_id':'d'},
        'connections':[{'endpoint_block_ids':['10'],'already_read':False}]}
    calls=[]
    monkeypatch.setattr(cs,'preview',lambda *args:(calls.append(1) or dict(status='COMPLETE',groups=[group],connection_count=1)))
    known={};monkeypatch.setattr(rel,'acquired_blocks',lambda *a:(known,{}))
    cs.accept(inv,a,data,'선택');assert not cs.inspect_directory(inv,a)['groups'][0]['connections'][0]['already_read']
    before=deepcopy(inv.p['connection_directories']);known['article97']={'10'}
    assert cs.inspect_directory(inv,a)['groups'][0]['connections'][0]['already_read']
    assert len(calls)==1 and before==inv.p['connection_directories']
''')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.register_file(C.parent,'05_TESTS/CONTRACTS/'+p.name,upstream_state='absent')
p=tests/'test_selected_connection_scope_api.py';t=p.read_text();t=t.replace("'premature', 'gap_repair']","'premature', 'gap_repair', 'cycle', 'cycle_repair']")
assert "'cycle', 'cycle_repair']" in t
t=t.replace("nested = route in ('narrow', 'whole')","nested = route in ('narrow', 'whole', 'cycle', 'cycle_repair')")
t=t.replace("            self.reference_calls = 0","            self.reference_calls = 0\n            self.second_scope = False\n            self.stale_proposed = False\n            self.first_target = None")
insert='''                if route in ('cycle','cycle_repair') and view['sources'] and not read_target and self.link_selected:
                    if not self.second_scope:
                        option=next(o for o in view['tool_options'] if o['choice']=='FOLLOW_CONNECTION' and o['selected_scope']['structural_selection']['unit_id']=='2')
                        self.second_scope=True;self.choices.append('SECOND_SCOPE')
                        return wire({'choice':'FOLLOW_CONNECTION','target':option['target'],'issue_id':'Q1',
                            'missing_need':'다른 항의 연결도 확인','relation':'DEPENDENCY','source_ref':view['sources'][0]['id']})
                    assert self.first_target not in [o['target'] for o in view['tool_options']]
                    assert len(view['connection_action_history'])>=2
                    assert all(not h['repeat_available'] for h in view['connection_action_history'])
                    if route=='cycle_repair' and not self.stale_proposed:
                        self.stale_proposed=True;self.choices.append('REJECTED_REPEAT')
                        return wire({'choice':'FOLLOW_CONNECTION','target':self.first_target,'issue_id':'Q1',
                            'missing_need':'동일 범위 재조회 시도','relation':'DEPENDENCY','source_ref':view['sources'][0]['id']})
                    c=next(c for c in view['references']['previously_inspected_cards'] if c.get('read_action') and '제2조' in c['target']['heading'])
                    self.choices.append('READ_SAVED_LINK')
                    return wire({'choice':'READ','selections':[{'target':c['read_action'],'issue_id':'Q1',
                        'missing_need':'저장한 목록에서 필요한 원문 읽기','relation':'DEPENDENCY','source_ref':view['sources'][0]['id']}]})
'''
t=t.replace("                gaps = view.get('assessment_gaps', [])", "                gaps = view.get('assessment_gaps', [])\n"+insert)
t=t.replace("uid='1' if route=='narrow' else '0'", "uid='1' if route in ('narrow','cycle','cycle_repair') else '0'")
t=t.replace("                    self.link_selected=True", "                    self.first_target=option['target']\n                    self.link_selected=True")
t=t.replace("    if route=='gap_repair':profile['max_no_progress']=4", "    if route in ('cycle','cycle_repair'):profile['max_no_progress']=4  # Exercise two deliberate directory actions plus stale proposal repair.\n    if route=='gap_repair':profile['max_no_progress']=4")
t=t.replace("    assert transport.choices == (", "    assert transport.choices == (['READ','FOLLOW_CONNECTION','SECOND_SCOPE',*(['REJECTED_REPEAT'] if route=='cycle_repair' else []),'READ_SAVED_LINK','FINISH'] if route in ('cycle','cycle_repair') else ")
p.write_text(t)
# Saved targets revalidate only scopes explicitly inspected earlier, not arbitrary cumulative sources.
p=Path(__file__).with_name('analyze.py');t=p.read_text().replace("    catalogs=[]; selections=[]; selected=None", "    catalogs=[]; selections=[]; selected=None").replace("matches=selected is not None and keys==expected and set(value['anchors'])<= {x[0] for x in expected} and catalog_sources<=set(value['anchors'])", "matches=any(keys==members_key(v['members']) and set(value['anchors']) <= {x[0] for x in members_key(v['members'])} for v in selections) and catalog_sources<=set(value['anchors'])");p.write_text(t)
print('Added cycle, stale output repair, persisted state, tamper and saved-read contracts')
