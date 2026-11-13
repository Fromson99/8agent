"""같은 문장을 로컬 Gold(소유자만 다름)에서 실행해 확인한다. 읽기 전용 계정."""
import json, sys, time
from pathlib import Path
import oracledb
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import statements

cred = json.loads((Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json').read_text())
result = []
with oracledb.connect(**cred) as c:
    cur = c.cursor()
    for key, title, sql in statements('A8_GR12_CM1208'):
        t = time.time()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            out = {'key': key, 'ok': True, 'seconds': round(time.time()-t, 2), 'columns': cols,
                   'rows': [[str(v)[:70] for v in r] for r in rows[:6]], 'row_count': len(rows)}
        except oracledb.DatabaseError as exc:
            out = {'key': key, 'ok': False, 'seconds': round(time.time()-t, 2), 'error': str(exc).split('\n')[0]}
        result.append(out)
        print(json.dumps(out, ensure_ascii=False)[:600])
(Path(__file__).resolve().parent/'local_check.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
