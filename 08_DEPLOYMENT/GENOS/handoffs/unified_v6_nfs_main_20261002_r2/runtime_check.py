"""Check this host's shared-directory SQLite and POSIX locks, without user data."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);a=p.parse_args()
r=a.runtime
if not r.is_absolute() or r.is_symlink():raise ValueError('absolute non-symlink runtime required')
r.mkdir(parents=True,exist_ok=True,mode=0o700)
probe=r/'storage-checks'/uuid.uuid4().hex
probe.mkdir(parents=True,mode=0o700)
dbpath=probe/'probe.sqlite'
db=sqlite3.connect(dbpath,isolation_level=None,timeout=.2)
assert db.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete'
db.execute('PRAGMA synchronous=FULL');db.execute('CREATE TABLE probe(value INTEGER)')
db.execute('INSERT INTO probe VALUES(1)');db.execute('BEGIN IMMEDIATE')
child="""import sqlite3,sys
c=sqlite3.connect(sys.argv[1],timeout=.2,isolation_level=None)
try:c.execute('BEGIN IMMEDIATE')
except sqlite3.OperationalError as e:
 if 'locked' not in str(e):raise
 sys.exit(0)
sys.exit(9)
"""
subprocess.run([sys.executable,'-c',child,str(dbpath)],check=True,timeout=5)
db.execute('INSERT INTO probe VALUES(2)');db.execute('ROLLBACK')
assert db.execute('SELECT value FROM probe').fetchall()==[(1,)]
assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
db.close()
with (probe/'owner.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 child="""import fcntl,sys
with open(sys.argv[1],'a') as f:
 try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:sys.exit(0)
 sys.exit(9)
"""
 subprocess.run([sys.executable,'-c',child,str(probe/'owner.lock')],check=True,timeout=5)
record={'status':'PASS','runtime':str(r.resolve()),'python':sys.version,'executable':sys.executable,
 'journal_mode':'DELETE','synchronous':'FULL','sqlite_version':sqlite3.sqlite_version,
 'sqlite_write_exclusion':True,'rollback':True,'posix_owner_lock':True,
 'scope':'same-host only; run from the actual code-serving environment too',
 'cross_host_or_multiple_replicas_certified':False}
(probe/'receipt.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False));print('STORAGE_RECEIPT',probe/'receipt.json')
