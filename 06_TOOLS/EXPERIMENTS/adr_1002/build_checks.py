from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');D=ROOT/s['candidate_dir'];C=D/'snapshot'
# A separate contract fixture exercises the actual API with the opt-in enabled.
src=(C/'05_TESTS/CONTRACTS/test_selected_connection_scope_api.py').read_text()
src=src.replace("@pytest.mark.parametrize('route', ['connection', 'missing', 'failure', 'context', 'chain'])", "@pytest.mark.parametrize('route,stall', [('connection',False),('missing',False),('failure',False),('context',False),('chain',False),('context',True)])")
src=src.replace('def test_actual_api_reads_link_or_structural_target_and_reuses_request(tmp_path, term_glossary, route, monkeypatch):','def test_progress_actual_api_originals_links_handoff_and_duplicate(tmp_path, term_glossary, route, stall, monkeypatch):')
src=src.replace('self.reference_calls = 0','self.reference_calls = 0\n            self.progress_turns = 0\n            self.events = []')
src=src.replace("            self.calls.append(phase)","""            self.calls.append(phase)
            from test_legal_agent_double_harness import wire as encode
            def wire(value):
                if '-read-choice' in phase:
                    self.progress_turns += 1
                    terminal=value['choice']=='FINISH'
                    value['answer_progress']={
                        'status':'ANSWERABLE' if terminal else 'NEEDS_SOURCE',
                        'answer_so_far':'확보한 적용 기준' if view['sources'] else '',
                        'basis_refs':[s['id'] for s in view['sources']][:4],
                        'material_need':'' if terminal else '현재 질문의 필수 기준 원문',
                        'next_answer_change':'' if terminal else '적용 기준의 내용을 확인한다.',
                        'previous_effect':'INITIAL' if self.progress_turns==1 else 'NO_CHANGE' if stall else 'NEED_NARROWED'}
                return encode(value)""")
src=src.replace('selected_connection_scope=True,answer_first=False)', 'selected_connection_scope=True,answer_first=False,answer_progress_control=True)')
src=src.replace("assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == 'COVERED'", "assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage'] in ('COVERED','PARTIAL')\n        # A resumed duplicate uses the persisted response without another model call.")
src=src.replace("    if route=='context':\n        assert transport.reference_calls==2\n        assert transport.choices==['READ','FOLLOW_CONNECTION','FOLLOW_CONNECTION','FINISH']", """    if stall:
        assert transport.reference_calls==1
        assert transport.choices==['READ','FOLLOW_CONNECTION','FOLLOW_CONNECTION']
        assert len([p for p in transport.calls if '-read-choice' in p])==3
        assert any(p.startswith('memory-assess') for p in transport.calls)
        journals=list(tmp_path.rglob('journal.sqlite'))
        events=[]
        for p in journals:
            with sqlite3.connect(p) as db:
                events += [(k,json.loads(v)) for k,v in db.execute('select kind,payload_json from event')]
        assert any(k=='ANSWER_PROGRESS_HANDOFF' for k,v in events)
        assert any(k=='INVESTIGATION_BOUNDED_STOP' and v['reason']=='NO_ANSWER_PROGRESS' for k,v in events)
    elif route=='context':
        assert transport.reference_calls==2
        assert transport.choices==['READ','FOLLOW_CONNECTION','FOLLOW_CONNECTION','FINISH']""")
(C/'05_TESTS/CONTRACTS/test_answer_progress_api.py').write_text(src)
for name in ['02_BACKEND/semantic_runtime/legal_agent/answer_progress.py','05_TESTS/CONTRACTS/test_answer_progress_api.py','05_TESTS/CONTRACTS/test_answer_progress.py']:
 if (C/name).exists():ac.register_file(D,name,upstream_state='absent')
