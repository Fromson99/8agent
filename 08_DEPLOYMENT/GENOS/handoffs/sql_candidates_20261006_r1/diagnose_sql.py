"""Bounded GENOS storage discovery; never open an operational database."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


NETWORK = {'nfs', 'nfs4', 'cifs', 'smb3'}
VOLATILE = {'tmpfs', 'ramfs', 'devtmpfs', 'proc', 'sysfs'}
SETTINGS = ('GENOS_RUNTIME_DIR', 'GENOS_STATE_DIR', 'GENOS_MEMORY_JOURNAL_MODE',
            'PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD',
            'POSTGRES_HOST', 'POSTGRES_PORT', 'MYSQL_HOST', 'MYSQL_PORT',
            'MYSQL_PASSWORD', 'MSSQL_HOST', 'MSSQL_PORT', 'SQLSERVER_HOST',
            'SQLSERVER_PORT', 'DATABASE_URL', 'SQLALCHEMY_DATABASE_URI',
            'GENOS_SQL_HOST', 'GENOS_SQL_PORT', 'GENOS_SQL_URL')


def mount_rows():
    rows = []
    if Path('/proc/self/mountinfo').is_file():
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            left, right = line.split(' - ', 1)
            bits, tail = left.split(), right.split()
            target = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), bits[4])
            rows.append({'target': target, 'fs': tail[0], 'readonly': 'ro' in bits[5].split(',')})
    return rows


def mount_for(path, rows):
    path = Path(path).resolve()
    eligible = [m for m in rows if path.is_relative_to(Path(m['target']))]
    return max(eligible, key=lambda m: len(m['target'])) if eligible else {'target': '/', 'fs': 'UNKNOWN', 'readonly': False}


def classify(mount):
    if mount['readonly']: return 'READ_ONLY'
    if mount['fs'] in NETWORK: return 'NETWORK_STORAGE'
    if mount['fs'] in VOLATILE: return 'VOLATILE_NOT_DURABLE'
    if mount['fs'] in {'overlay', 'aufs'}: return 'CONTAINER_LAYER_PERSISTENCE_UNKNOWN'
    return 'LOCAL_MOUNT_PERSISTENCE_UNKNOWN'


def settings_present(env):
    # Values of credentials, URLs, database names and user names are never logged.
    return {k: bool(env.get(k)) for k in SETTINGS}


def configured_endpoints(env):
    candidates = []
    for host_key, port_key, default, kind in (
        ('PGHOST', 'PGPORT', 5432, 'postgresql'),
        ('POSTGRES_HOST', 'POSTGRES_PORT', 5432, 'postgresql'),
        ('MYSQL_HOST', 'MYSQL_PORT', 3306, 'mysql'),
        ('MSSQL_HOST', 'MSSQL_PORT', 1433, 'sqlserver'),
        ('SQLSERVER_HOST', 'SQLSERVER_PORT', 1433, 'sqlserver'),
        ('GENOS_SQL_HOST', 'GENOS_SQL_PORT', None, 'explicit-sql')):
        host = env.get(host_key, '').strip()
        if not host or host.startswith('/') or ',' in host: continue
        try: port = int(env.get(port_key) or default)
        except (TypeError, ValueError): continue
        if 1 <= port <= 65535: candidates.append({'host': host, 'port': port, 'kind': kind, 'source': host_key})
    for key in ('DATABASE_URL', 'SQLALCHEMY_DATABASE_URI', 'GENOS_SQL_URL'):
        try:
            value = urlsplit(env.get(key, ''))
            kind = value.scheme.split('+')[0]
            default = {'postgres': 5432, 'postgresql': 5432, 'mysql': 3306, 'mariadb': 3306, 'mssql': 1433}.get(kind)
            if default and value.hostname:
                candidates.append({'host': value.hostname, 'port': value.port or default, 'kind': kind, 'source': key})
        except ValueError: pass
    candidates.extend({'host': '127.0.0.1', 'port': port, 'kind': kind, 'source': 'loopback-only'}
                      for port, kind in ((5432, 'postgresql'), (3306, 'mysql'), (1433, 'sqlserver')))
    # Endpoint values are kept in memory and not exported to reports.
    unique = {}
    for c in candidates: unique.setdefault((c['host'], c['port']), c)
    return list(unique.values())[:12]


PROBE = r'''
import fcntl,json,os,sqlite3,subprocess,sys,time
from pathlib import Path
p=Path(sys.argv[1]); result={}
# Only this newly-created private directory is touched. Never select an existing DB.
f=p/'lock'; f.touch(); holder=f.open('r+')
fcntl.flock(holder,fcntl.LOCK_EX|fcntl.LOCK_NB)
child="import fcntl,sys; f=open(sys.argv[1],'r+');\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError: sys.exit(0)\nsys.exit(3)"
r=subprocess.run([sys.executable,'-c',child,str(f)],capture_output=True,timeout=4)
result['same_host_flock_exclusion']=r.returncode==0
fcntl.flock(holder,fcntl.LOCK_UN);holder.close()
dbpath=p/'synthetic-delete.sqlite';db=sqlite3.connect(dbpath,timeout=.2,isolation_level=None)
result['journal_mode']=db.execute('PRAGMA journal_mode=DELETE').fetchone()[0]
db.execute('PRAGMA synchronous=FULL');db.execute('CREATE TABLE probe(id INTEGER PRIMARY KEY,value INTEGER NOT NULL)')
db.execute('INSERT INTO probe VALUES(1,11)');db.execute('BEGIN IMMEDIATE')
child="import sqlite3,sys; d=sqlite3.connect(sys.argv[1],timeout=.2,isolation_level=None);\ntry: d.execute('BEGIN IMMEDIATE')\nexcept sqlite3.OperationalError as e: sys.exit(0 if getattr(e,'sqlite_errorcode',None) in (5,6) else 4)\nsys.exit(3)"
r=subprocess.run([sys.executable,'-c',child,str(dbpath)],capture_output=True,timeout=4)
result['same_host_sql_writer_exclusion']=r.returncode==0
db.execute('UPDATE probe SET value=22');db.execute('ROLLBACK')
result['rollback_preserved']=db.execute('SELECT value FROM probe').fetchone()[0]==11
db.close()
child="import os,sqlite3,sys; d=sqlite3.connect(sys.argv[1],isolation_level=None); d.execute('PRAGMA synchronous=FULL'); d.execute('BEGIN IMMEDIATE');d.execute('UPDATE probe SET value=99');os._exit(7)"
r=subprocess.run([sys.executable,'-c',child,str(dbpath)],capture_output=True,timeout=4)
db=sqlite3.connect(dbpath,timeout=1)
result['interrupted_transaction_recovery']=r.returncode==7 and db.execute('SELECT value FROM probe').fetchone()[0]==11
result['integrity_check']=db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
db.close()
result['status']='PASS' if all(result[k] for k in ('same_host_flock_exclusion','same_host_sql_writer_exclusion','rollback_preserved','interrupted_transaction_recovery','integrity_check')) and result['journal_mode']=='delete' else 'FAIL'
print(json.dumps(result))
'''


def scratch_probe(base):
    folder = None
    try:
        # Parent must already exist. Do not create missing guessed mount paths.
        folder = Path(tempfile.mkdtemp(prefix='.sql-candidate-probe-', dir=base))
        os.chmod(folder, 0o700)
        done = subprocess.run([sys.executable, '-c', PROBE, str(folder)],
                              capture_output=True, text=True, timeout=15)
        result = json.loads(done.stdout) if done.returncode == 0 else {'status': 'ERROR', 'error_type': 'ProbeExit', 'exit_code': done.returncode}
        # Small synthetic files are retained for inspection; no operational cleanup.
        return {**result, 'scratch_path': str(folder)}
    except subprocess.TimeoutExpired:
        return {'status': 'TIMEOUT', 'scratch_path': str(folder) if folder else None}
    except Exception as error:
        return {'status': 'ERROR', 'error_type': type(error).__name__}


def endpoint_probe(candidate):
    # DNS + connect are bounded by a separate process. No login or SQL writes.
    code = "import socket,sys; s=socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=2);s.close()"
    try:
        result = subprocess.run([sys.executable, '-c', code, candidate['host'], str(candidate['port'])],
                                capture_output=True, timeout=3)
        status = 'TCP_REACHABLE_AUTH_AND_SQL_UNVERIFIED' if result.returncode == 0 else 'NOT_REACHABLE'
    except subprocess.TimeoutExpired: status = 'TIMEOUT'
    return {'source': candidate['source'], 'kind': candidate['kind'], 'status': status}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--context', default='codespace')
    args = parser.parse_args(argv)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    rows = mount_rows()
    print('SQL DIAGNOSTIC: context=' + args.context, flush=True)
    state = os.environ.get('GENOS_STATE_DIR')
    paths = [('runtime', args.runtime), ('output', out), ('checkout', Path.cwd())]
    if state: paths.insert(0, ('explicit-state', Path(state)))
    for name in ('/data', '/var/lib', '/mnt', '/workspace', '/app', '/tmp'):
        if Path(name).is_dir(): paths.append(('known-path', Path(name)))
    # Add actual mounted directories, not recursively scan the filesystem.
    extra = [Path(m['target']) for m in rows if m['fs'] not in NETWORK | VOLATILE
             and m['target'] != '/' and not m['target'].startswith(('/proc', '/sys', '/dev', '/etc', '/run/secrets'))
             and Path(m['target']).is_dir()]
    paths.extend(('mounted-directory', p) for p in extra[:16])
    info, unique = [], set()
    for source, path in paths:
        path = path.resolve()
        if str(path) in unique: continue
        unique.add(str(path))
        m = mount_for(path, rows)
        info.append({'source': source, 'path': str(path), 'exists': path.is_dir(),
                     'writable_access': os.access(path, os.W_OK) if path.is_dir() else False,
                     'mount': m, 'classification': classify(m), 'persistence': 'NOT_VERIFIED'})
    # Test runtime, explicit state and at most two distinct local mount candidates.
    tested, mounts_seen = 0, set()
    for item in info:
        if not item['exists'] or not item['writable_access'] or item['mount']['readonly']: continue
        selected = item['source'] in ('runtime', 'explicit-state')
        local = item['classification'] == 'LOCAL_MOUNT_PERSISTENCE_UNKNOWN'
        key = (item['mount']['target'], item['mount']['fs'])
        if not selected and (not local or key in mounts_seen or tested >= 3): continue
        if tested >= 4: break
        mounts_seen.add(key); tested += 1
        print('SCRATCH CHECK ' + item['source'] + ' ' + item['path'], flush=True)
        item['probe'] = scratch_probe(item['path'])
        print('SCRATCH RESULT ' + item['probe']['status'], flush=True)
    endpoints = []
    for candidate in configured_endpoints(os.environ):
        print('SQL ENDPOINT CHECK source=' + candidate['source'], flush=True)
        endpoints.append(endpoint_probe(candidate))
    sockets = []
    for base in ('/var/run/postgresql', '/run/postgresql'):
        if Path(base).is_dir():
            sockets.extend(str(p) for p in list(Path(base).glob('.s.PGSQL.*'))[:8] if p.is_socket())
    for path in ('/var/run/mysqld/mysqld.sock', '/run/mysqld/mysqld.sock', '/tmp/mysql.sock'):
        if Path(path).is_socket(): sockets.append(path)
    modules = {name: importlib.util.find_spec(name) is not None
               for name in ('psycopg', 'psycopg2', 'pymysql', 'pyodbc', 'sqlalchemy', 'duckdb')}
    resolved_base = Path(state).resolve() if state else args.runtime.resolve()
    report = {'schema': 'genos-sql-candidates-diagnostic-v1', 'context': args.context,
              'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'python': {'executable': sys.executable, 'version': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version},
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'settings_present_only': settings_present(os.environ),
              'selected_state_base': str(resolved_base),
              'default_shortcut_path': str(resolved_base / 'case-memory/cases-v4.sqlite'),
              'shortcut_pointer_exists': (resolved_base / 'case-memory/SHORTCUT_CURRENT.json').is_file(),
              'storage': info, 'sql_endpoints': endpoints, 'unix_socket_candidates': sorted(set(sockets)),
              'python_drivers': modules, 'clients': {name: bool(shutil.which(name)) for name in ('psql', 'mysql', 'sqlcmd')},
              'deployment_persistence': 'NOT_VERIFIED', 'cross_host_locking': 'NOT_VERIFIED',
              'operational_database_opened': False, 'production_ready': False}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['GENOS SQL 후보 진단 결과', '실행 위치: ' + args.context,
             '현재 상태 경로: ' + str(resolved_base),
             '기존 DB/코드/환경 설정은 변경하지 않았습니다.', '', '저장소 후보:']
    for item in info:
        lines.append(f"- {item['path']} | {item['mount']['fs']} | {item['classification']} | 시험={item.get('probe', {}).get('status', 'NOT_TESTED')}")
    lines += ['', '서버형 SQL 후보 (주소·인증정보는 출력하지 않음):']
    lines.extend(f"- {e['source']} / {e['kind']}: {e['status']}" for e in endpoints)
    lines += ['', '판정과 다음 조치:',
              '1. TCP 연결 가능: 서버형 SQL 후보입니다. DB 종류·권한·인증과 실제 SQL 처리는 미확인입니다. 현재 SQLite 코드의 backend 변경이 필요합니다.',
              '2. 로컬 mount: 재배포 후 영속성과 코드서빙 컨테이너에서 같은 볼륨 사용 가능 여부는 별도 확인이 필요합니다.',
              '3. NFS DELETE 시험 PASS: 같은 호스트의 짧은 잠금·rollback·중단 복구 시험만 통과한 것입니다. NFS 운영 승인 또는 데이터 안전 인증이 아닙니다.',
              '4. NFS만 가능: WAL은 사용할 수 없습니다. 단일 저장 서비스+DELETE와 NFS 잠금/장애복구 검증, 또는 플랫폼 서버형 SQL 제공 방안을 검토해야 합니다. 현재 코드를 자동 변경하지 않습니다.',
              '5. DuckDB/SQLite를 다른 이름으로 설치하는 것만으로 공유 저장소 동시 쓰기 조건은 해결되지 않습니다.',
              '6. 코드를 실행한 코드스페이스와 실제 코드서빙은 다른 환경일 수 있습니다. 발견 실패는 GENOS 전체에서 SQL이 없다는 뜻이 아닙니다.',
              '비밀 값은 출력하지 않았습니다. 결과 전체를 외부로 보낼 필요 없이 위 후보/시험 상태를 확인하면 됩니다.',
              '근거: https://sqlite.org/wal.html / https://sqlite.org/useovernet.html',
              '운영 준비 판정: 미확인; 운영 DB 접근: 없음']
    (out / 'SUMMARY_UTF8.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines), flush=True)
    print('REPORT=' + str(out / 'report.json'), flush=True)
    print('SUMMARY=' + str(out / 'SUMMARY_UTF8.txt'), flush=True)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        # Do not expose arbitrary provider messages or environment values.
        print('DIAGNOSTIC FAILED error_type=' + type(error).__name__, file=sys.stderr, flush=True)
        raise SystemExit(2)
