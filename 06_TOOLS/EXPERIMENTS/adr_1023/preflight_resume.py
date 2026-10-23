from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate'];p=C/'05_TESTS/CONTRACTS/test_connection_cycle_guard.py'
p.write_text(p.read_text()+'''

def test_accepted_action_restore_preserves_completed_directory_and_counters(monkeypatch):
    from semantic_runtime.legal_agent import law_navigation as nav, comparison_research, source_investigation, definition_entry
    from semantic_runtime.basis_links import resolver
    inv,data=setup(monkeypatch);a,_=scopes(inv,data);calls=[]
    monkeypatch.setattr(cs,'preview',lambda *a:(calls.append(1) or dict(status='COMPLETE',groups=[],connection_count=0)))
    cs.accept(inv,a,data,'최초 확인');cs.inspect_directory(inv,a)
    saved=deepcopy(inv.p['connection_directories'])
    inv.p.update(decisions=[],turn=0,no_progress=2)
    before=deepcopy(inv.p);before.pop('connection_directories');before['no_progress']=0
    decision={'next_action':'FINISH'}
    inv.p['accepted']={'before':before,'decision':decision,'data':data,'actions':{},'phase':'resume','input_hash':digest(data)}
    inv.control=False;inv.completion=False;inv.left=lambda:100;inv.assessment_handoff=lambda:None
    inv.result=lambda d:{'finished':True};inv.question='모의 질문'
    for module,name in ((resolver,'acquire'),(comparison_research,'acquire'),(source_investigation,'acquire_preferred'),(definition_entry,'acquire_initial')):
        monkeypatch.setattr(module,name,lambda *a:None)
    def execute(*args):
        assert inv.p['connection_directories']==saved and inv.p['no_progress']==2
        assert cs.inspect_directory(inv,a)['status']=='COMPLETE'
        return True
    inv.execute=execute
    assert nav.Investigation.run(inv)=={'finished':True}
    assert len(calls)==1 and inv.p['turn']==1
''')
p=Path(__file__).with_name('finalize.py');t=p.read_text().replace('ADR1021','ADR1022').replace('후보500파일','후보501파일').replace('연결 범위 선확인과 근거 있는 조회 대상','연결 확인 이력과 반복 실행 차단').replace('연결 선확인·검토 위치 출처 검증','연결 이력 보존·순환 차단')
t=t.replace('ADR1022은 연결 범위 선택 없이 FINISH한 뒤 검토가 근거 없는 조항 번호를 만들고 다음 조회로 넘겼다. 목록 보존 수정과 별개인 실행 경로 결함이다.','ADR1022에서 동일 원문 상태로 97조1항과5항 연결 목록을 번갈아 열었다. FOLLOW_CONNECTION은 일반 중복 검사에서 제외되고, 현재 선택 범위 외에는 미선택으로 되돌렸으며 과거 완료 결과를 실행 제한에 쓰지 않았다.')
p.write_text(t)
p=ART/'design-freeze.json';p.rename(ART/'design-freeze-r2-api.json')
