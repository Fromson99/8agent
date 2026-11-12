"""Local Oracle (docker a8-legal-mapped-20261023) direct-SQL bridge standing in for the ORDS envelope.

Only the HTTP envelope is replaced: the serving code sends the same statements and binds it
would send to ORDS. Every statement is counted and timed for the experiment record.
"""
import json as _json,subprocess,time,threading
from pathlib import Path

CONTAINER='a8-legal-mapped-20261023'
GOLD_OWNER='A8_GR12_CM1208'
CHANNEL='cm-r12-engine'

def connection_info():
 info=_json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
 assert info['State']['Running'] and info['Config']['Labels'].get('a8.task')=='legal-mapped-20261023'
 ep=info['HostConfig']['PortBindings']['1521/tcp'];assert len(ep)==1 and ep[0]['HostIp']=='127.0.0.1'
 return {'dsn':'127.0.0.1:'+ep[0]['HostPort']+'/FREEPDB1','password':dict(x.split('=',1) for x in info['Config']['Env'])['ORACLE_PASSWORD'],'image':info['Config']['Image']}

def connect(user='system'):
 import oracledb
 oracledb.defaults.fetch_lobs=False
 info=connection_info()
 conn=oracledb.connect(user=user,password=info['password'],dsn=info['dsn']);conn.call_timeout=60000
 return conn

class Bridge:
 SQL_PATH='/local-oracle-direct-sql'
 def __init__(self,mapping,log_path=None,slow_ms=200):
  import oracledb
  self.schema_map=mapping;self.conn=connect();self.lock=threading.Lock();self.types={'CLOB':oracledb.DB_TYPE_CLOB,'VARCHAR2':oracledb.DB_TYPE_VARCHAR,'NUMBER':oracledb.DB_TYPE_NUMBER}
  self.count=0;self.seconds=0.0;self.slow=[];self.writes=0;self.log=open(log_path,'a') if log_path else None;self.slow_ms=slow_ms
 def request(self,method,path,json=None):
  assert method=='POST' and path==self.SQL_PATH,(method,path)
  body=json;stmt=body['statementText'];binds=body.get('binds',[]);begin=time.monotonic()
  with self.lock:
   with self.conn.cursor() as cur:
    cur.setinputsizes(**{b['name']:self.types[b['data_type']] for b in binds})
    cur.execute(stmt,{b['name']:b['value'] for b in binds})
    is_write=cur.description is None
    if is_write:
     self.writes+=1;result={'items':[{'result':cur.rowcount}]}
     if not stmt.lstrip().upper().startswith(('SELECT','WITH')):self.conn.commit()
    else:
     columns=[c[0] for c in cur.description];limit=body['limit'];rows=cur.fetchmany(limit+1)
     result={'items':[{'resultSet':{'offset':0,'hasMore':len(rows)>limit,'items':[dict(zip(columns,row)) for row in rows[:limit]]}}]}
  elapsed=time.monotonic()-begin;self.count+=1;self.seconds+=elapsed
  if elapsed*1000>=self.slow_ms:self.slow.append({'ms':round(elapsed*1000),'statement':stmt[:160]})
  if self.log:self.log.write(_json.dumps({'n':self.count,'ms':round(elapsed*1000,1),'write':is_write,'statement':stmt[:120]})+'\n');self.log.flush()
  return result
 def summary(self):
  return {'sql_calls':self.count,'sql_seconds':round(self.seconds,3),'writes':self.writes,'slow_over_ms':self.slow_ms,'slow':self.slow[:40],'slow_count':len(self.slow)}

RENAMES={'SRCH_ROW':{'RFRN_DTA_HASH_VALU':'RFRN_DATA_HASH_VALU','RFRN_DTA_CTNT':'RFRN_DATA_CTNT'}}

def local_gold_mapping(registered,conn,owner=GOLD_OWNER):
 """Registered R5 mapping with the local Gold's physical names and column types.

 Local Gold predates the metadata registration: tables are IDD_B03_* (not IDD_B003_*), two
 SRCH_ROW columns keep the RFRN_DATA_ prefix and a few ID columns are wider. Logical columns,
 keys and readers are unchanged; the variant is recorded next to the registered digest.
 """
 from dataclasses import replace
 from semantic_runtime.physical_mapping import _freeze,digest
 cur=conn.cursor()
 cur.execute("select table_name,column_name,data_type,data_length,data_precision,data_scale,nullable from all_tab_columns where owner=:o",{'o':owner})
 local={}
 for t,c,dt,dl,dp,ds,nu in cur.fetchall():local.setdefault(t,{})[c]=(dt,dl,dp,ds,nu)
 variant={k:_json.loads(_json.dumps(t,default=dict)) for k,t in registered.tables.items()};changes=[]
 for key,table in variant.items():
  if table['owner']!=owner:continue
  name=table['name'].replace('IDD_B003_','IDD_B03_');changes.append((table['name'],name));table['name']=name
  cols=local[name]
  for logical,col in table['columns'].items():
   phys=RENAMES.get(key,{}).get(col['name'],col['name']);col['name']=phys
   dt,dl,dp,ds,nu=cols[phys]
   if dt in ('VARCHAR2','CHAR'):typ=f'{dt}({dl} BYTE)'
   elif dt=='NUMBER':typ=f'NUMBER({dp},0)'
   elif dt.startswith('TIMESTAMP'):typ=col['type']
   elif dt=='VECTOR':typ='VECTOR(*,FLOAT32)'
   else:typ=dt
   if typ!=col['type'] or (nu=='N')!=col['required']:changes.append((name+'.'+phys,col['type'],typ,col['required'],nu=='N'))
   col['type']=typ;col['required']=(nu=='N')
 return replace(registered,tables=_freeze(variant),target_sha256=digest(variant)),changes
