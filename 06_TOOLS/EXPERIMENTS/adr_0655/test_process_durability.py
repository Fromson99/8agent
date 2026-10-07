"""Real child-process exits and concurrent writers, no model or provider calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.corrected_memory import MemoryError
from lawrag.pipeline.shortcut_operations import backup,restore,reconcile

ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0655/integrated/revisions/rev-001/snapshot/02_BACKEND'
P={'user_id':'durability','team_id':'legal','authenticated':True,'document_ids':['law']}
SCRIPT='''
import json,os,sys
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
p=json.loads(sys.argv[2]);r=ShortcutRepository(sys.argv[1]);mode=sys.argv[3]
body={'question':'수신 원문','session_id':'s','request_id':'same','document_ids':['law']}
i=r.intake(body,p)
if mode=='intake':os._exit(73)
c=r.connect(i['id'],p)
if mode=='artifact':
 with r.transaction():
  r.trace(c['id'],p,kind='TEST',payload={'original':'보존할 도구 결과'},documents=['law'])
  os._exit(73)
if mode in ('uncommitted','committed'):
 with r.transaction():
  r.fact(c['id'],p,expected_revision=c['revision'],event=i['event'],subject='A',predicate='duration',value={'kind':'duration','value':8,'unit':'month'})
  if mode=='uncommitted':os._exit(73)
 os._exit(73)
r.close()
'''
def child(path,mode):
 return subprocess.Popen([sys.executable,'-c',SCRIPT,str(path),json.dumps(P),mode],env={**os.environ,'PYTHONPATH':str(CODE),'PYTHONDONTWRITEBYTECODE':'1'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)

def test_exit_after_intake_commit_retains_unclassified_original(tmp_path):
 path=tmp_path/'cases-v4.sqlite';proc=child(path,'intake');assert proc.wait(timeout=30)==73
 r=ShortcutRepository(path)
 try:
  row=r.db.execute('SELECT * FROM sw_intake').fetchone()
  assert r.event(row['event'],P)['payload']['text']=='수신 원문'
  assert r.db.execute('SELECT count(*) FROM sw_fact').fetchone()[0]==0
  assert reconcile(r)['ok']
 finally:r.close()

@pytest.mark.parametrize('mode,count',[('uncommitted',0),('committed',1)])
def test_exit_at_fact_commit_boundary(tmp_path,mode,count):
 path=tmp_path/'cases-v4.sqlite';proc=child(path,mode);assert proc.wait(timeout=30)==73
 r=ShortcutRepository(path)
 try:
  assert r.db.execute('SELECT count(*) FROM sw_fact').fetchone()[0]==count
  assert r.db.execute('SELECT count(*) FROM sw_fact_head').fetchone()[0]==count
  assert reconcile(r)['ok']
 finally:r.close()

def test_artifact_written_before_db_commit_is_not_visible_after_exit(tmp_path):
 path=tmp_path/'cases-v4.sqlite';proc=child(path,'artifact');assert proc.wait(timeout=30)==73
 r=ShortcutRepository(path)
 try:
  assert r.db.execute('SELECT count(*) FROM sw_trace').fetchone()[0]==0
  assert r.db.execute('SELECT count(*) FROM sw_artifact').fetchone()[0]==0
  assert len(list(r.artifacts.glob('*/*')))==1  # preserved orphan, never served
  assert reconcile(r)['ok']
 finally:r.close()

def test_two_processes_same_intake_have_one_original(tmp_path):
 path=tmp_path/'cases-v4.sqlite';r=ShortcutRepository(path);r.close()
 children=[child(path,'intake') for _ in range(2)]
 assert [c.wait(timeout=30) for c in children]==[73,73]
 r=ShortcutRepository(path)
 try:
  assert r.db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]==1
  assert r.db.execute("SELECT count(*) FROM sw_event WHERE kind='UTTERANCE_RECEIVED'").fetchone()[0]==1
 finally:r.close()

def test_restore_snapshot_after_process_restart_preserves_queue_and_original(tmp_path):
 path=tmp_path/'live/cases-v4.sqlite';proc=child(path,'committed');assert proc.wait(timeout=30)==73
 r=ShortcutRepository(path)
 try:receipt=backup(r,tmp_path/'backup')
 finally:r.close()
 restored=restore(tmp_path/'backup',tmp_path/'restored');assert restored['restored']
 r=ShortcutRepository(tmp_path/'restored/cases-v4.sqlite')
 try:
  assert reconcile(r)['ok']
  assert r.db.execute('SELECT count(*) FROM sw_fact').fetchone()[0]==1
  assert r.db.execute('SELECT count(*) FROM sw_queue').fetchone()[0]==receipt['counts']['sw_queue']
 finally:r.close()
