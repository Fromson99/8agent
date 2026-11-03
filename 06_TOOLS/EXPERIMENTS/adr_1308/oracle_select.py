"""Read-only Oracle SQL equivalence over bind-supplied synthetic rows; no DDL."""
from pathlib import Path
from types import SimpleNamespace as NS
import importlib.util,json,sys,time,sqlite3,math
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1308-gold-query-optimization'
freeze=json.loads((ADR/'artifacts/design-final/freeze.json').read_text());C=ROOT/freeze['code_root']
sys.path.insert(0,str(C/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime import oracle_query_fulltext as new
spec=importlib.util.spec_from_file_location('semantic_runtime._baseline_fts',ROOT/'02_BACKEND/semantic_runtime/oracle_query_fulltext.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
from semantic_runtime.oracle_dp_io import digest
import oracledb
out=ADR/'artifacts'/sys.argv[1];out.mkdir(exist_ok=False)
from resource_guard import Guard
guard=Guard(out);guard.start();start=time.monotonic();calls=[]
credential=Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json'
assert credential.stat().st_mode & 0o077==0
credentials=json.loads(credential.read_text());assert credentials['dsn'].startswith('127.0.0.1:')
db=oracledb.connect(**credentials);db.call_timeout=10000
# All data is supplied as a bounded CLOB bind. No source or schema mutation.
fixture=[];bodies=['alpha alpha beta','alpha beta gamma','gamma delta','delta','alpha','epsilon','zeta','eta']
for n,body in enumerate(bodies):
    key='k'+str(n);did='D1' if n<4 else 'D2';sid='s'+str(n//2)
    row={'release':'r','kind':'length','key':key,'document':did,'owner':sid,'target':None,
         'value':json.dumps({'length':len(body.split()),'source_id':sid})}
    fixture.append(row)
    for token in set(body.split()):
        offsets=[i for i,t in enumerate(body.split()) if t==token]
        fixture.append(dict(row,kind='post',key=token,owner=key,target='body',value=json.dumps({'positions':offsets,'tf':len(offsets)})))
relation="(SELECT x.*,ROWNUM AS fixture_ordinal FROM JSON_TABLE(:fixture,'$[*]' COLUMNS(RELEASE_ID VARCHAR2(64) PATH '$.release',KIND VARCHAR2(64) PATH '$.kind',LOOKUP_ID VARCHAR2(512) PATH '$.key',DOCUMENT_ID VARCHAR2(512) PATH '$.document',OWNER_ID VARCHAR2(512) PATH '$.owner',TARGET_ID VARCHAR2(512) PATH '$.target',VALUE_JSON CLOB PATH '$.value')) x)"
new.ROW=old.ROW=relation
def query(sql,binds,limit=100):
    assert sql.lstrip().upper().startswith(('SELECT','WITH'))
    values={k:v for k,v,t in binds};values['fixture']=json.dumps(fixture)
    types={'CLOB':oracledb.DB_TYPE_CLOB,'VARCHAR2':oracledb.DB_TYPE_VARCHAR,'NUMBER':oracledb.DB_TYPE_NUMBER}
    started=time.monotonic()
    with db.cursor() as cur:
        cur.setinputsizes(fixture=oracledb.DB_TYPE_CLOB,**{k:types[t] for k,v,t in binds})
        cur.execute(sql,values);names=[d[0] for d in cur.description];rows=cur.fetchmany(limit+1)
        assert len(rows)<=limit
        result=[{k:(v.read() if isinstance(v,oracledb.LOB) else v) for k,v in zip(names,r)} for r in rows]
    calls.append({'sql_sha256':digest(sql),'seconds':time.monotonic()-started,'rows':len(rows)})
    return result
def index(module):
    i=module.UnitIndex.__new__(module.UnitIndex)
    i.records=NS(manifest={});i.request=NS(release_id='r',sources=NS(allowed=frozenset({'D1'})),snapshot=NS(binding_hash='p'),records=i.records)
    i.sql=i.request.sql=NS(query=query,deadline=time.monotonic()+120)
    i.kinds={'unit_fts_posting':'post','unit_fts_length':'length','unit':'unit'}
    i.statistics={'documents':len(bodies),'tokens':sum(len(t.split()) for t in bodies)};i.check_unchanged=lambda:None
    return i
results=[]
try:
    for terms in (['alpha'],['alpha beta'],['alpha alpha'],['alpha','gamma'],['absent']):
        for allowed in (None,{'s0'},NS(document_ids={'D1'})):
            a,b=index(old),index(new)
            def rows(i):
                cte,binds=i._matches(terms,allowed)
                return query(cte+'SELECT k,did,sid,score FROM matches ORDER BY score,k',binds)
            before,after=rows(a),rows(b);assert before==after,(terms,before,after)
            projection=b._projection(terms,allowed)
            assert projection==[[r[k] for k in ('K','DID','SID','SCORE')] for r in after]
            results.append({'terms':terms,'scope':repr(allowed),'hits':len(after),'equal':True})
    (out/'result.json').write_text(json.dumps({'passed':len(results),'checks':results,'queries':calls,'seconds':time.monotonic()-start,'DDL':0,'writes':0,'model_calls':0,'code_root':freeze['code_root']},indent=2)+'\n')
    print('Oracle SELECT equivalence:',len(results),'cases;',len(calls),'queries')
except BaseException as e:
    (out/'failure.json').write_text(json.dumps({'error':str(e),'queries':calls,'completed':results},indent=2)+'\n');raise
finally:
    db.close();guard.done.set();guard.thread.join(timeout=3)
