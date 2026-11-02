"""Request-level stop state survives creation of a different native run."""
import json
import sqlite3

import pytest

from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.completion_budget import prior_stop
from semantic_runtime.legal_agent.errors import ContractError


@pytest.fixture
def journal():
    db=sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE event(seq INTEGER PRIMARY KEY,kind,payload_json,payload_hash);
        CREATE TABLE model_attempt(attempt_id TEXT,status TEXT);''')
    yield db
    db.close()


def fail(db, code, *, resumable=False, wrong_hash=False):
    value={'code':code,'diagnostics':{'stage':'ASSESS',
        'investigation':{'resume_available':resumable,'cause_codes':['ASSESSMENT_CONTRACT_UNRESOLVED']},
        'output_contract':{'category':'FINAL_READ_REVIEW_INVALID','repairable':False}}}
    db.execute('INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)',
        ('RUN_FAILED',json.dumps(value),'wrong' if wrong_hash else digest(value)))


@pytest.mark.parametrize('status',['SENT','UNKNOWN'])
def test_unknown_or_interrupted_send_cannot_become_new_attempt(journal,status):
    journal.execute('INSERT INTO model_attempt VALUES(?,?)',('M1',status))
    assert prior_stop(journal)=={'kind':'UNKNOWN','attempt_id':'M1','code':'MODEL_TRANSPORT_ERROR'}


def test_deadline_code_survives_unknown_resume(journal):
    journal.execute("INSERT INTO model_attempt VALUES('M1','UNKNOWN')")
    fail(journal,'MODEL_DEADLINE_EXCEEDED')
    assert prior_stop(journal)['code']=='MODEL_DEADLINE_EXCEEDED'


def test_exhausted_final_review_remains_terminal(journal):
    fail(journal,'SOURCE_INVESTIGATION_INCOMPLETE')
    result=prior_stop(journal)
    assert result['kind']=='TERMINAL' and result['stage']=='ASSESS'
    assert result['output_contract']['category']=='FINAL_READ_REVIEW_INVALID'


@pytest.mark.parametrize('case',['empty','prepared','accepted','known_rejection','explicit_resume'])
def test_safe_known_outcome_is_not_blanket_blocked(journal,case):
    if case in ('prepared','accepted','known_rejection'):
        journal.execute('INSERT INTO model_attempt VALUES(?,?)',('M1',
            {'prepared':'PREPARED','accepted':'SUCCEEDED','known_rejection':'FAILED'}[case]))
    if case=='known_rejection':fail(journal,'MODEL_UPSTREAM_UNAVAILABLE')
    if case=='explicit_resume':fail(journal,'SOURCE_INVESTIGATION_INCOMPLETE',resumable=True)
    assert prior_stop(journal) is None


def test_failure_hash_tampering_cannot_grant_retry(journal):
    fail(journal,'SOURCE_INVESTIGATION_INCOMPLETE',wrong_hash=True)
    with pytest.raises(ContractError,match='hash'):
        prior_stop(journal)
