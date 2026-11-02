from common import *
S=CAND/'snapshot';p=S/'02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py';s=p.read_text()
a=s.index('    st=state_for(inv,data)\n    if st.get(\'pending\'):',s.index('def gate('));z=s.index('    st=record(',a)
s=s[:a]+'    require_known_outcome(inv)\n'+s[z:]
a=s.index('def gate(')
s=s[:a]+'''def require_known_outcome(inv):
    # Run before primary selection too: a restored pending supervisor must not
    # spend another model call merely to arrive back at its execution gate.
    for state in inv.p.get('investigation_supervisor',{}).values():
        if state.get('binding')!=inv.p['binding'] or state.get('state_hash')!=seal(state):
            raise ContractError('supervisor state binding/hash mismatch')
        if state.get('pending'):
            failure=state.get('failure',{})
            error=TransportError(failure.get('reason','Unknown prior supervisor outcome'),unknown=True)
            error.code=failure.get('code',error.code);error.http_status=failure.get('http_status',error.http_status)
            raise error

''' + s[a:];p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';s=p.read_text()
s=s.replace("    def request_decision(self, data, actions, phase):\n        from . import source_goal_control as source_goals", "    def request_decision(self, data, actions, phase):\n        from .investigation_supervisor import require_known_outcome\n        require_known_outcome(self)\n        from . import source_goal_control as source_goals")
p.write_text(s)
c=read(DES/'criteria.json');c['success']=[v.replace('four scoped','five scoped') for v in c['success']];c['refinement_before_tests']='Guard pending supervisor at request_decision entry as well as gate, so crash/resume cannot issue a primary call or preselected action before the guard.';put(DES/'criteria-refined.json',c)
print('Pending resume guard also applied before native primary choice; product5')
