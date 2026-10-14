from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0739/integrated/snapshot'
p=C/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';s=p.read_text();old="            self.record_search_outcome()\n";assert s.count(old)==1
new=old+"""            if self.modern:
                # RESEARCH completes outside execute(); credit its actual content
                # before the next decision's no-progress guard. Query changes alone
                # cannot erase a request's monotonic history or bounded budget.
                known = set(self.p.get('request_progress', []))
                if rr.record_progress(self.p):
                    previous = self.p['no_progress']
                    self.p['no_progress'] = 0
                    self.s.repo.event('LAW_SEARCH_PROGRESS', {
                        'new_facts': len(set(self.p['request_progress']) - known),
                        'previous_no_progress': previous,
                        'query_fingerprint': self.p['catalogue']['query_fingerprint']})
                self.save()
"""
p.write_text(s.replace(old,new))
p=C/'05_TESTS/CONTRACTS/test_focused_input_modality.py'
p.write_text(p.read_text()+"""

@pytest.mark.parametrize('version', [cc.V5, cc.V7])
@pytest.mark.parametrize('fresh_content', [True, False])
def test_completed_recall_refreshes_only_new_content_before_stop(session, version, fresh_content):
    from copy import deepcopy
    from test_main50_request_repair import modern
    from semantic_runtime.legal_agent import law_navigation as ln, request_repair as rr
    native, _ = session
    seed = modern(native)
    seed.s.profile['candidate_navigation']['completion_policy_version'] = version
    seed = ln.Investigation(seed.s, seed.question, seed.record, None, 120, None, None)
    state = deepcopy(seed.p)
    if fresh_content:
        # Previous completed catalogue had no candidates; the requested recall
        # now returns the fixture's authorized source. No invented source/ID.
        state['laws'] = {}; state['groups'] = {}; state['structure_page'] = {'items': []}
        state['request_progress'] = []
        rr.record_progress(state)
    prior = set(state['request_progress'])
    limit = seed.s.profile['max_no_progress']
    state.update(awaiting_search=True, no_progress=limit)
    state['catalogue']['query_fingerprint'] = 'previous-query'
    saved = []
    budget = deepcopy(seed.s.repo.budget())
    resumed = ln.Investigation(seed.s, seed.question, seed.record, None, 120, state,
        lambda value: saved.append(deepcopy(value)))
    assert resumed.p['no_progress'] == (0 if fresh_content else limit)
    assert prior <= set(resumed.p['request_progress'])
    assert resumed.p['read_state'] == state['read_state']
    assert seed.s.repo.budget() == budget
    assert saved and saved[-1]['no_progress'] == resumed.p['no_progress']
    assert 'awaiting_search' not in saved[-1]
    def reached(*args):
        raise RuntimeError('next native decision reached')
    resumed.invoke = reached
    if fresh_content:
        with pytest.raises(RuntimeError, match='next native decision reached'):
            resumed.run()
        # Even another query fingerprint cannot credit identical content again.
        again = deepcopy(saved[-1]); again.update(awaiting_search=True, no_progress=limit)
        again['catalogue']['query_fingerprint'] = 'another-query'
        repeated = ln.Investigation(seed.s, seed.question, seed.record, reached, 120, again, None)
        assert repeated.p['no_progress'] == limit
        assert repeated.p['request_progress'] == saved[-1]['request_progress']
        repeated.run()
        assert repeated.p['stop_reason'] == 'NO_PROGRESS'
    else:
        resumed.run()
        assert resumed.p['stop_reason'] == 'NO_PROGRESS'
""")
