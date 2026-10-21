"""Dataiku JDBC connection bridge for the existing bounded Oracle SQL port.

No credentials in the notebook. Only fixed SQL templates supplied by the
publisher are accepted; bind values are escaped/typed, never interpolated raw.
"""
import math
import re
from semantic_runtime.oracle_dp_io import DPError, digest

_TOKEN = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*(?:\n|$)|/\*[\s\S]*?\*/|:([A-Za-z][A-Za-z0-9_]*)")


def literal(value):
    if value is None:return 'NULL'
    if type(value) is int:return str(value)
    if type(value) is not str or '\x00' in value:raise DPError('JDBC_BIND: unsupported value')
    if len(value.encode())>4000:raise DPError('JDBC_BIND: VARCHAR2 literal exceeds 4000 bytes')
    return "'"+value.replace("'","''")+"'"


def render(statement,binds,*,write=False):
    values={};declarations=[];initializers=[];cleanup=[]
    for i,(name,value,kind) in enumerate(binds):
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name) or name in values:raise DPError('JDBC_BIND: duplicate/invalid name')
        if kind=='CLOB' and value is not None:
            if not write or not isinstance(value,str):raise DPError('JDBC_CLOB: CLOB only in write blocks')
            var=f'qp_lob_{i}';declarations.append(var+' CLOB;');values[name]=var
            initializers.append(f'DBMS_LOB.CREATETEMPORARY({var},TRUE);')
            for start in range(0,len(value),900):
                text=literal(value[start:start+900]);initializers.append(f'DBMS_LOB.APPEND({var},TO_CLOB({text}));')
            cleanup.append(f'IF DBMS_LOB.ISTEMPORARY({var})=1 THEN DBMS_LOB.FREETEMPORARY({var}); END IF;')
        elif kind=='NUMBER':
            if type(value) is not int:raise DPError('JDBC_NUMBER: integer required')
            values[name]=literal(value)
        elif kind in ('VARCHAR2','CLOB'):values[name]=literal(value)
        else:raise DPError('JDBC_BIND: unsupported Oracle bind type')
    used=set()
    def replace(match):
        name=match.group(1)
        if name is None:return match.group()
        if name not in values:raise DPError('JDBC_BIND: missing bind '+name)
        used.add(name);return values[name]
    compiled=_TOKEN.sub(replace,statement)
    if used!=set(values):raise DPError('JDBC_BIND: unused bind')
    if declarations:
        free=' '.join(cleanup)
        compiled='DECLARE '+' '.join(declarations)+' BEGIN '+' '.join(initializers)+' '+compiled+' '+free+' EXCEPTION WHEN OTHERS THEN '+free+' RAISE; END;'
    return compiled


class DataikuClient:
    SQL_PATH='/dataiku-jdbc'
    def __init__(self,executor,connection,project):
        self.executor=executor;self.connection=connection;self.project=project
    def request(self,method,path,json):
        if (method,path)!=('POST',self.SQL_PATH):raise DPError('JDBC_METHOD: unsupported')
        text=json['statementText'];write=text.startswith(('BEGIN ','DECLARE '))
        if not write and not text.startswith('SELECT '):raise DPError('JDBC_SQL: expected SELECT or maintained PL/SQL block')
        if json.get('offset',0)!=0:raise DPError('JDBC_OFFSET: nonzero offset')
        binds=[(b['name'],b['value'],b['data_type']) for b in json.get('binds',[])]
        rendered=render(text,binds,write=write)
        try:
            if write:
                # One JDBC session. The inner maintained block owns COMMIT/ROLLBACK.
                self.executor.query_to_df('SELECT 1 AS OK FROM DUAL',pre_queries=[rendered],post_queries=['COMMIT'])
                return {'items':[{'result':0}]}
            frame=self.executor.query_to_df(rendered)
            frame=frame.astype(object).where(frame.notna(),None)
            rows=frame.to_dict(orient='records')
            if len(rows)>json.get('limit',100):raise DPError('JDBC_RESULT: too many rows')
            clean=[]
            for row in rows:
                new={}
                for key,value in row.items():
                    if hasattr(value,'item'):value=value.item()
                    if isinstance(value,float):
                        if not math.isfinite(value):raise DPError('JDBC_RESULT: nonfinite numeric')
                        if value.is_integer():value=int(value)
                    new[str(key).upper()]=value
                clean.append(new)
            return {'items':[{'resultSet':{'items':clean,'offset':0,'hasMore':False}}]}
        except DPError:raise
        except Exception as exc:
            # JDBC exceptions may repeat CLOB bodies or connection details.
            code=re.search(r'ORA-\d{5}|PLS-\d{5}',str(exc))
            raise DPError('JDBC_FAILURE: '+(code.group() if code else type(exc).__name__)) from None
    def identity(self):
        from semantic_runtime.oracle_dp_io import SQL
        # This single read establishes target identity; subsequent operations are journaled.
        payload={'statementText':"SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL",'limit':1}
        rows=self.request('POST',self.SQL_PATH,payload)['items'][0]['resultSet']['items']
        if len(rows)!=1 or not all(rows[0].values()):raise DPError('JDBC_IDENTITY: missing target identity')
        return digest({'connection':self.connection,'project':self.project,'database':rows[0]}),rows[0]
