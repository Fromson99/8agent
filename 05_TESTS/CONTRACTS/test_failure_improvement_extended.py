"""Additional ordinary CLI, SQLite and multi-turn contracts; no real model calls."""
import copy
import json
from pathlib import Path
import sqlite3
import subprocess

import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
from lawrag.pipeline import failure_improvement as f, golden
from lawrag.pipeline.native_trace import read_trace, native_result_stages
from test_failure_improvement import completed, damageable, case_for, design, results, reseal
from test_unified_legal_agent import unified, structured_generation, ok
from test_memory_runtime_v2 import command

ROOT = Path(__file__).resolve().parents[2]


def cli(*args, code=0):
    r = subprocess.run([str(ROOT/'.venv/bin/python'), str(ROOT/'06_TOOLS/pipeline.py'), *map(str,args)],
        cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert r.returncode == code, r.stdout + r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize('method', ['FACT_UPDATE','ANSWER_PRESENT'])
def test_changed_case_has_valid_native_score(unified, method):
    _, send, _, _, runtime = unified
    first = ok(send())
    options = {'facts':[{'name':'対象','value':'A'}]} if method=='FACT_UPDATE' else {'format':'table'}
    result = ok(send(command(method,target=first['question_id'],**options)))
    journal = next((runtime/'legal-agent/runs').glob('*/'+result['run_id']+'/journal.sqlite'))
    trace = native_result_stages(result,journal)
    assert trace['stages']['selected'] == sorted(s['id'] for s in result['assembly']['context'])
    row = golden.score(case_for(result),result,
        {'generation_id':result['answer']['generation_id'],'store_sha256':result['answer']['source_store_sha256']},native_journal=journal)
    assert row['answer_quality']=='PENDING_HUMAN_REVIEW'


def test_self_hashed_stage_without_matching_acceptance_is_rejected(completed):
    _, journal = completed; damageable(journal)
    with sqlite3.connect(journal) as db:
        payload, = db.execute("SELECT payload_json FROM entity_version WHERE kind='case_stage' AND entity_id='case:READ'").fetchone()
        value=json.loads(payload);value['record']['read_partial']=['unrecorded-source']
        db.execute("UPDATE entity_version SET payload_json=?,payload_hash=? WHERE kind='case_stage' AND entity_id='case:READ'",(json.dumps(value),digest(value)))
    with pytest.raises(ValueError):read_trace(journal)


def test_proposal_cannot_invent_issue_missing_from_trace(completed,tmp_path):
    _,journal=completed
    report=f.diagnose([journal],tmp_path/'diagnostics')
    value=f.read(f.read(report['report'])['records'][0]['path'])
    value['issues'].append({'type':'tool_partial','stage':'READ','confirmed':True,'refs':[{'table':'observation','id':'invented','hash':'a'*64}]})
    value=reseal(value);f.publish(tmp_path/'invented.json',value)
    with pytest.raises(ValueError):f.propose(tmp_path/'invented.json',tmp_path/'proposals')


def test_subprocess_pipeline_diagnose_propose_score_and_gate(completed,tmp_path):
    result,journal=completed
    # Append a native mock observation using the production receipt writer.
    repo=UnifiedRepository(journal)
    try:repo.record_observation({'tool':'read','args':{'fixture':True}},{'status':'PARTIAL','items':[],'evidence_ids':[],'next_cursor':'mock-next'},verify=lambda e:None)
    finally:repo.close()
    out=cli('action-memory','diagnose','--journal',journal,'--runtime',tmp_path/'empty','--output',tmp_path/'diag')
    diagnosis=f.read(out['report'])['records'][0]['path']
    p=cli('action-memory','propose','--diagnosis',diagnosis,'--output',tmp_path/'proposals')
    assert p['proposals']==1
    proposal=f.read(f.read(p['report'])['candidates'][0]['path'])
    assert proposal['runtime_loadable'] is False and proposal['layer']=='Tool'
    suite=golden.seal({'binding':{'generation_id':result['answer']['generation_id'],'store_sha256':result['answer']['source_store_sha256']},'cases':[case_for(result)]})
    f.publish(tmp_path/'suite.json',suite);f.publish(tmp_path/'response.json',result)
    cli('golden','score-native','--suite',tmp_path/'suite.json','--case-id','c1','--response',tmp_path/'response.json','--journal',journal,'--output',tmp_path/'score.json')
    assert f.read(tmp_path/'score.json')['answer_quality']=='PENDING_HUMAN_REVIEW'
    f.publish(tmp_path/'design.json',design())
    cli('action-memory','comparison-plan','--design',tmp_path/'design.json','--output',tmp_path/'plan.json')
    plan=f.read(tmp_path/'plan.json')
    f.publish(tmp_path/'parent.json',results(plan,'parent','FAIL'))
    f.publish(tmp_path/'candidate.json',results(plan,'candidate','PASS'))
    gate=cli('action-memory','compare','--plan',tmp_path/'plan.json','--parent',tmp_path/'parent.json','--candidate',tmp_path/'candidate.json','--output',tmp_path/'gate.json')
    assert gate['acceptance_criteria_met'] is True and gate['main_promotion_automatic'] is False
    failed=results(plan,'candidate','FAIL');f.publish(tmp_path/'no-gain.json',failed)
    gate=cli('action-memory','compare','--plan',tmp_path/'plan.json','--parent',tmp_path/'parent.json','--candidate',tmp_path/'no-gain.json','--output',tmp_path/'rejected.json',code=2)
    assert gate['acceptance_criteria_met'] is False
    pending=results(plan,'candidate','PENDING_HUMAN_REVIEW');f.publish(tmp_path/'pending.json',pending)
    refused=cli('action-memory','compare','--plan',tmp_path/'plan.json','--parent',tmp_path/'parent.json','--candidate',tmp_path/'pending.json','--output',tmp_path/'pending-gate.json',code=1)
    assert refused['state']=='FAILED' and not (tmp_path/'pending-gate.json').exists()


def test_committed_wal_is_in_snapshot_and_budget_is_enforced(completed):
    _,journal=completed
    before=read_trace(journal)
    with sqlite3.connect(journal) as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute("UPDATE run SET started_at='mock-wal-change'");db.commit()
        current=read_trace(journal)
        assert before['snapshot_sha256'] != current['snapshot_sha256']
        with pytest.raises(ValueError,match='budget'):read_trace(journal,max_rows=1)


def test_cli_locked_output_and_empty_input_fail_cleanly(completed,tmp_path):
    import fcntl
    _,journal=completed;folder=tmp_path/'locked';folder.mkdir()
    with (folder/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        value=cli('action-memory','diagnose','--journal',journal,'--runtime',tmp_path/'empty','--output',folder,code=1)
        assert value['error_type']=='BlockingIOError'
    value=cli('action-memory','diagnose','--runtime',tmp_path/'empty','--output',tmp_path/'out',code=1)
    assert value['state']=='FAILED'


def test_completed_later_page_resolves_partial_without_new_proposal(completed,tmp_path):
    _,journal=completed
    repo=UnifiedRepository(journal)
    try:
        partial=repo.record_observation({'tool':'read','args':{'target':'mock-target','extent':'article','cursor':None}},
            {'status':'PARTIAL','coverage':{'complete':False},'items':[]},verify=lambda e:None)
        complete=repo.record_observation({'tool':'read','args':{'target':'mock-target','extent':'article','cursor':'next'}},
            {'status':'OK','coverage':{'complete':True},'items':[]},verify=lambda e:None)
    finally:repo.close()
    trace=read_trace(journal)
    issue=next(i for i in trace['issues'] if any(ref.get('id')==partial['observation_id'] for ref in i['refs']))
    assert issue['resolved'] is True and issue['recovery_ref']['id']==complete['observation_id']
    report=f.diagnose([journal],tmp_path/'diagnostics')
    diagnosis=f.read(report['report'])['records'][0]['path']
    assert f.propose(diagnosis,tmp_path/'proposals')['proposals']==0


@pytest.mark.parametrize('mutation',['request','status'])
def test_observation_must_match_request_and_result_receipts(completed,mutation):
    _,journal=completed;damageable(journal)
    with sqlite3.connect(journal) as db:
        ident,raw=db.execute('SELECT observation_id,request_json FROM observation LIMIT 1').fetchone()
        if mutation=='request':
            request=json.loads(raw);request['args']['target']='invented'
            db.execute('UPDATE observation SET request_json=? WHERE observation_id=?',(json.dumps(request),ident))
        else:db.execute("UPDATE observation SET status='ERROR' WHERE observation_id=?",(ident,))
    with pytest.raises(ValueError,match='observation'):read_trace(journal)


def test_stale_projection_requires_rediagnosis(completed,tmp_path):
    _,journal=completed
    result=f.diagnose([journal],tmp_path/'diagnostics')
    diagnosis=f.read(f.read(result['report'])['records'][0]['path'])
    trace=f.read(diagnosis['trace_path'])
    trace.pop('published_result_sha256');trace=reseal(trace)
    f.publish(tmp_path/'older-projection.json',trace)
    diagnosis['trace_path']=str(tmp_path/'older-projection.json')
    diagnosis['trace_sha256']=trace['content_sha256'];diagnosis=reseal(diagnosis)
    f.publish(tmp_path/'older-diagnosis.json',diagnosis)
    with pytest.raises(ValueError,match='projection changed'):f.propose(tmp_path/'older-diagnosis.json',tmp_path/'proposals')
