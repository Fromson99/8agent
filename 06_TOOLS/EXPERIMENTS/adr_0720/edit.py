from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0720/resumed/snapshot';L=C/'02_BACKEND/semantic_runtime/legal_agent'
p=L/'law_navigation.py';s=p.read_text()
old="            self.p['reopened'] = {'turn': self.p.get('turn', 0), 'reason': 'USER_REENTRY'}"
new="""            if rr.enabled(session.profile):
                self.p=rr.new_epoch(self.p,reason='USER_REENTRY')
                if self.p.get('gap_rounds'):
                    self.p.setdefault('prior_request_gap_rounds',[]).extend(self.p.pop('gap_rounds'))
                self.p.pop('request_progress',None)
            self.p['reopened'] = {'turn': self.p.get('turn', 0), 'reason': 'USER_REENTRY'}"""
assert old in s;s=s.replace(old,new)
old="        self.save()\n        self.s.repo.event('LAW_DECISION_RETRY'"
new="""        if self.modern:
            self.p['decision_retry'].update(data=deepcopy(data),actions=deepcopy(actions),actions_hash=digest(actions))
        self.save()
        self.s.repo.event('LAW_DECISION_RETRY'"""
assert old in s;s=s.replace(old,new)
old="                data, actions = self.view(); phase = 'source-law-navigation-'+str(self.p['turn']+1)"
new="""                retry=self.p.get('decision_retry') if self.modern else None
                if retry:
                    # Rejection feedback changes a freshly rendered menu. The
                    # corrective attempt belongs to its original immutable view.
                    data,actions=deepcopy(retry['data']),deepcopy(retry['actions'])
                    phase=retry['phase']
                    if (retry['input_hash']!=digest(data) or retry['actions_hash']!=digest(actions)
                            or retry['epoch']!=self.p.get('investigation_epoch',0)):
                        raise ContractError('immutable retry snapshot changed')
                    self.s.repo.event('LAW_DECISION_RETRY_RESUMED',{'epoch':retry['epoch'],
                        'presentation_id':data['presentation_id'],'phase':phase,'additional_model_call':False})
                else:
                    data, actions = self.view(); phase = 'source-law-navigation-'+str(self.p['turn']+1)"""
assert old in s;s=s.replace(old,new);p.write_text(s)
p=C/'05_TESTS/CONTRACTS/test_main50_request_repair.py';s=p.read_text()+'''


def test_interrupted_corrective_transport_resumes_original_view_without_third_call(session):
    native,_=session;i=modern(native);calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:return {'presentation_id':'stale-invalid'}
        raise RuntimeError('synthetic interruption during corrective transport')
    i.invoke=invoke
    with pytest.raises(RuntimeError,match='synthetic interruption'):i.run()
    retry=deepcopy(i.p['decision_retry']);assert len(calls)==2
    assert retry['input_hash']!=__import__('semantic_runtime.contracts',fromlist=['digest']).digest(i.view()[0])
    reopened=modern(native,deepcopy(i.p))
    reopened.invoke=lambda *args:pytest.fail('unknown corrective outcome must not trigger a third attempt')
    reopened.bounded_result=lambda reason:{'bounded':reason}
    assert reopened.run()=={'bounded':'MODEL_DECISION_UNRESOLVED'}
    assert reopened.p['decision_retry']['input_hash']==retry['input_hash']


def test_retry_menu_tamper_is_rejected_before_execution(session):
    native,_=session;i=modern(native);d,a=i.view()
    i.p['decision_retry']={**rr.decision_identity(i.p,d,'test'), 'data':d,'actions':a,'actions_hash':'changed','attempt':1}
    with pytest.raises(ContractError,match='snapshot'):i.run()


def test_new_user_request_preserves_old_gap_audit_but_can_reconsider(session):
    native,_=session;i=modern(native);g=rr.bind_gap(GAP,i.s);g.update(gap_id=ln.gap_id(g),gap_key=cc.gap_key(g))
    i.p['assessment_gaps']=[g];i.open_gap_round();i.close_gap_round([],'previous request stop')
    assert not rr.may_reopen(g,i.p)
    i.s.investigation_prior_route=True
    try:again=modern(native,deepcopy(i.p))
    finally:i.s.investigation_prior_route=False
    assert again.p['prior_request_gap_rounds'] and not again.p.get('gap_rounds')
    assert rr.may_reopen(g,again.p) and again.p['investigation_epoch']==1 and again.p['no_progress']==0
''';p.write_text(s)
print('immutable retry and fresh-request boundary connected')
