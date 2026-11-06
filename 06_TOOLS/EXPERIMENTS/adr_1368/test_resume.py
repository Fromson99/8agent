import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ContractError
from test_wiki_workspace import env, ws


def reject(value):
    raise ContractError('invalid reference in submitted node')


def test_old_reserved_repair_still_has_one_remaining_send(ws):
    scope, stage, context, prompt, schema = ws.scope(ws.document_ids), 'WIKI_PROPOSE', {}, 'old', {}
    ident = digest([ws.namespace, ws.actor, stage, context, prompt, schema, ws.producer_binding])
    old = {'kind': 'JOB', 'scope': scope, 'stage': stage, 'identity': ident,
           'context_hash': digest(context), 'phase': 'REPAIR_READY', 'deadline': ws.clock()+360,
           'attempt': 0, 'attempts': [{'response': {}, 'receipt': {}, 'error': 'first'}],
           'actor': ws.actor, 'response': {}, 'receipt': {}}
    ws._job_write('job-'+ident, old, 0)
    calls = []
    def generate(prompt, context, schema):
        calls.append(context['call_budget'])
        return {}, {}
    ws.generate = generate
    with pytest.raises(ContractError, match='invalid reference'):
        ws._job(stage, context, prompt, schema, reject)
    assert [(c['attempt'],c['maximum']) for c in calls] == [(2,2)]
    assert ws.load('job-'+ident)['phase'] == 'INVALID'


def test_resume_fourth_rejection_only_sends_fifth_attempt(ws, monkeypatch):
    write = ws._job_write
    def crash_after_commit(bid, document, expected):
        result = write(bid, document, expected)
        if document['phase']=='REPAIR_READY' and document['attempt']==3:
            raise InterruptedError('restart after fourth rejection')
        return result
    seen = []
    def generate(prompt, context, schema):
        attempt = context['call_budget']['attempt']
        seen.append(attempt)
        return {'attempt': attempt}, {}
    def validate(value):
        if value['attempt']<5:
            reject(value)
    ws.generate = generate
    monkeypatch.setattr(ws, '_job_write', crash_after_commit)
    def run():
        return ws._job('WIKI_PROJECT', {}, 'restart', {}, validate)
    with pytest.raises(InterruptedError):
        run()
    monkeypatch.setattr(ws,'_job_write',write)
    assert run()[0]=={'attempt':5}
    assert run()[0]=={'attempt':5}
    assert seen==[1,2,3,4,5]


def test_expired_deadline_stops_additional_repairs(ws):
    now = [1.]
    ws.clock = lambda: now[0]
    sends = []
    def generate(prompt, context, schema):
        sends.append(1)
        now[0] = context['call_budget']['absolute_deadline']+1
        return {}, {}
    ws.generate = generate
    with pytest.raises(ContractError, match='late model result'):
        ws._job('WIKI_PROJECT', {}, 'deadline', {}, reject)
    with pytest.raises(ContractError, match='BUDGET_EXHAUSTED'):
        ws._job('WIKI_PROJECT', {}, 'deadline', {}, reject)
    assert sends == [1]
