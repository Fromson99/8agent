"""Offline contract checks against real synthetic v6 journals/projections."""
import importlib.util,json,sys,sqlite3
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
from conftest import term_glossary
from test_unified_legal_agent import unified
from test_structure_first_search import structured_generation
from test_memory_runtime_v2 import command
from fastapi.testclient import TestClient
import main,service
spec=importlib.util.spec_from_file_location('vf',Path(__file__).with_name('verify_field.py'))
vf=importlib.util.module_from_spec(spec);spec.loader.exec_module(vf)

@pytest.fixture
def confirmed(unified,monkeypatch,tmp_path,structured_generation):
    client,send,transport,principal,runtime=unified
    monkeypatch.setattr(service,'_bootstrap_application',lambda:client.app)
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(runtime))
    monkeypatch.setenv('GENOS_MEMORY_ENABLED','0')
    monkeypatch.setenv('GENOS_MEMORY_JOURNAL_MODE','DELETE')
    monkeypatch.delenv('TEAM_ID',raising=False)
    def call(n):
        return TestClient(main.app).post('/chat',json={'question':'모의승인규정 제1조의 승인 대상은?',
            'session_id':'s','request_id':'verify'+str(n),'memory_authorization':{'issued_at':1,'signature':'fixture'}}).json()
    first=call(1)
    transport.command=command('EXPERIENCE_CONFIRM',target=first['data']['question_id'])
    result=call(2)
    path=tmp_path/'result.json';path.write_text(json.dumps(result,ensure_ascii=False))
    return runtime,path,structured_generation,result,principal

@pytest.mark.parametrize('damage',['none','adapter','run','generation','revision','wiki','runtime','binding_hash','commit_hash','experience_hash','wal'])
def test_field_real_journal(confirmed,damage,tmp_path):
    runtime,path,generation,result,principal=confirmed
    if damage=='adapter':result['data']['chat_adapter_revision']='old'
    if damage=='run':result['data']['run_id']='0'*32
    if damage=='revision':result['data']['revision']+=1
    if damage=='generation':
        generation=tmp_path/'wrong-generation';generation.mkdir()
        (generation/'manifest.json').write_text(json.dumps({'generation_id':'WRONG','store_sha256':'0'*64}))
    if damage=='wiki':
        folder=runtime/'case-memory/wikis'/vf.digest([principal['user_id'],principal['team_id']])/'legal_wiki'
        snap=json.loads((folder/'index.json').read_text());snap['pages'][0]['experience_hash']='bad'
        (folder/'index.json').write_text(json.dumps(snap))
    if damage=='binding_hash' or damage=='commit_hash':
        journal=list((runtime/'legal-agent/runs').glob('*/'+result['data']['run_id']+'/journal.sqlite'))[0]
        with sqlite3.connect(journal) as db:
            # Corruption injection into synthetic pytest DB only, bypassing immutable guards.
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                db.execute('DROP TRIGGER '+chr(34)+name.replace(chr(34),chr(34)*2)+chr(34))
            db.execute("UPDATE run SET binding_hash=? WHERE singleton=1",('0'*64,)) if damage=='binding_hash' else db.execute("UPDATE case_commit SET payload_hash=? WHERE singleton=1",('0'*64,))
    if damage=='experience_hash' or damage=='wal':
        with sqlite3.connect(runtime/'case-memory/cases-v3.sqlite') as db:
            if damage=='wal':db.execute('PRAGMA journal_mode=WAL')
            else:db.execute('UPDATE knowledge SET hash=? WHERE id=?',('0'*64,result['data']['experience_id']))
    if damage=='runtime':runtime=tmp_path/'wrong-runtime'
    path.write_text(json.dumps(result,ensure_ascii=False))
    if damage=='none':
        assert vf.check_result(runtime,path,generation)['scope']=='workflow_answer_and_run_binding'
        assert vf.check_result(runtime,path,generation,wiki=True)['wiki_projection']=='PASS'
    else:
        with pytest.raises(ValueError):vf.check_result(runtime,path,generation,wiki=True)

def test_verify_is_only_registration(tmp_path):
    path=tmp_path/'probe.json';path.write_text(json.dumps({'code':0,'data':{'text':'verified'}}))
    assert vf.check_result(tmp_path,path,tmp_path)['scope']=='registration_probe_only'
    with pytest.raises(ValueError):vf.check_result(tmp_path,path,tmp_path,wiki=True)
