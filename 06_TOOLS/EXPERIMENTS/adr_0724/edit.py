from pathlib import Path

R = Path(__file__).resolve().parents[3]
C = R/'02_BACKEND/lawrag/research/candidates/adr_0724/integrated/snapshot'
p = C/'02_BACKEND/semantic_runtime/legal_agent/request_repair.py'
s = p.read_text()
s = s.replace("        offers = []\n        for pair", """        offers = []
        documents = set(target.get('document_candidates', []))
        documents.update(pair['document_id'] for pair in target.get('pairs', []))
        # Gap resolution can locate a document outside the paged catalogue.
        # Register its scoped identity before offering an executable read.
        investigation.add_laws([{'document_id': did, 'article_count': None, 'unit_count': None}
                                for did in sorted(documents)
                                if lc.token(investigation.s, 'L', did) not in investigation.p['laws']])
        if not documents <= set(investigation.s.scope):
            raise ContractError('gap target escaped request scope')
        for pair""")
s = s.replace("                   'queries': decision.get('queries', []),", """                   'queries': sorted({text_key(q) if decision['next_action'] == 'SEARCH_STRUCTURE'
                                      else re.sub(r'\\s+', ' ', unicodedata.normalize('NFKC', q)).strip().casefold()
                                      for q in decision.get('queries', [])}),""")
s = s.replace("    investigation.p['no_progress'] += 1\n    step.update(status='FAILED', outcome={'failure_code': code, 'absence_proven': False, 'changed': False})", """    changed = record_progress(investigation.p)
    investigation.p['no_progress'] = 0 if changed else investigation.p['no_progress'] + 1
    step.update(status='FAILED', outcome={'failure_code': code, 'absence_proven': False, 'changed': changed},
                progress={'changed': changed, 'unchanged_turns': investigation.p['no_progress']})
    if investigation.control: investigation.p['state_version'] += 1
    investigation.s.repo.event('INVESTIGATION_CHAIN_STEP', step)""")
p.write_text(s)
p = C/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py'
s = p.read_text()
start = s.index("                ident=actions[target]['identity'];sid=ident['source_id']", s.index("        if kind == 'READ_ARTICLES':", s.index('    def execute_tool')))
end = s.index("                plan['completed'][target]=gid;", start)
old = s[start:end]
old = old.replace("                    try:self.execute_tool", "                    self.execute_tool")
old = old.replace("                    except Exception:\n                        plan['status']='INTERRUPTED';plan['remaining_target']=target;self.save();raise\n", '')
s = s[:start]+"                plan['remaining_target']=target;self.save()\n                try:\n"+''.join('    '+line+'\n' for line in old.splitlines())+"                except Exception:\n                    plan['status']='INTERRUPTED';self.save();raise\n"+s[end:]
needle = "                self.p = deepcopy(accepted['before']); self.p.update(progressed); self.p['accepted'] = accepted"
replacement = """                if self.modern and accepted['decision']['next_action']=='READ_ARTICLES':
                    # This accepted action is read-only. Completed target receipts
                    # and their acquired originals survive a process interruption.
                    # Restoring only its pre-action state would reacquire them.
                    for key in ('read_plans','laws','groups','selected','contexts','law_reasons',
                                'basis_history','material_history','window','window_groups','focus',
                                'structure_location','gap_rounds'):
                        if key in self.p:progressed[key]=deepcopy(self.p[key])
"""+needle
assert needle in s
s = s.replace(needle, replacement)
p.write_text(s)

tests = C/'05_TESTS/CONTRACTS/test_main50_request_repair.py'
extra = (R/'06_TOOLS/EXPERIMENTS/adr_0723/test_cross_catalogue.py').read_text().split('from test_main50_request_repair import *',1)[1]
extra = extra.replace("    again.request_decision =", "    reopen_offset = len(acquired)\n    again.request_decision =")
extra = extra.replace("    assert acquired == ['0', '1', '1']", "    assert acquired[:2] == ['0', '1']\n    assert acquired[reopen_offset:] == ['1']")
tests.write_text(tests.read_text()+extra+'''

def test_gap_target_outside_authorized_scope_never_becomes_action(session):
    native, _ = session
    investigation = modern(native)
    gap = rr.bind_gap(GAP, investigation.s)
    gap['target_binding']['document_candidates'] = ['other']
    investigation.p['assessment_gaps'] = [gap]
    with pytest.raises(ContractError, match='scope'):
        rr.add_target_actions(investigation, {})


def test_transient_partial_batch_retains_completed_original_without_adoption(session, monkeypatch):
    native, _ = session
    investigation = modern(native)
    gap = rr.bind_gap(GAP, investigation.s)
    gap.update(gap_id=ln.gap_id(gap), gap_key=cc.gap_key(gap))
    investigation.p['assessment_gaps'] = [gap]
    investigation.open_gap_round()
    data, actions = investigation.view()
    first = data['gap_targets'][0]['read_actions'][0]
    actions['second'] = {**deepcopy(actions[first]), 'id': 'second'}
    actions['second']['identity']['unit_id'] = '1'
    value = decision(data, 'READ_ARTICLES', first)
    value['targets'] = [first, 'second']
    original = ur.acquire_batch
    calls = []
    def acquire(source, hits, state):
        calls.append(hits[0]['unit_id'])
        if len(calls) == 2:raise TimeoutError('synthetic partial read timeout')
        return original(source, hits, state)
    monkeypatch.setattr(ur, 'acquire_batch', acquire)
    assert investigation.execute(value, data, actions) is False
    plan = next(iter(investigation.p['read_plans'].values()))
    assert plan['status'] == 'INTERRUPTED' and plan['remaining_target'] == 'second'
    assert first in plan['completed'] and investigation.p['selected']
    assert not inv.originals_for(investigation.s, investigation.p)
    shown, offered = investigation.view()
    assert shown['sources'] and shown['tool_recovery'][0]['absence_proven'] is False
    assert investigation.current_gap_round()['action_receipts'][-1]['status'] == 'FAILED'
''')
print('Four reproduced boundaries repaired; two scope and partial failure contracts added.')
