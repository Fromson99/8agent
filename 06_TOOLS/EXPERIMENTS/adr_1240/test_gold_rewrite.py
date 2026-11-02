import ast,importlib.util
from types import SimpleNamespace as S
from common import ROOT,DES,GOLD,read
import pytest
from semantic_runtime.oracle_query_catalog import ROW

def fixture():
 pf=read(DES/'port-freeze.json');p=ROOT/pf['code_root']/GOLD.relative_to(ROOT)/'connect.py'
 spec=importlib.util.spec_from_file_location('scope_port_connect',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 binding=read(DES/'baseline.json')['gold_binding'];legacy=ROOT/binding['adapter_root']/'gold_connection.py'
 fn=next(n for n in ast.parse(legacy.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='rewrite_reads');ns={'GoldError':RuntimeError};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(legacy),'exec'),ns)
 class Config:
  manifest={'tables':{'nav.test':{}}}
  def names(self,key,only_kind=None):return S(table='ALL_ROWS' if only_kind is None else 'NARROW_ROWS')
 runtime=S(rewrite_reads=ns['rewrite_reads'],GoldError=RuntimeError);config=Config()
 prefix=('SELECT ROW_ID,ROW_SHA256,DOCUMENT_ID,LOOKUP_ID,OWNER_ID,TARGET_ID,TO_CLOB(VALUE_JSON) AS VALUE,DBMS_LOB.GETLENGTH(VALUE_JSON) AS N FROM '+ROW+' WHERE RELEASE_ID=:release AND KIND=:kind')
 return module,runtime,config,prefix

@pytest.mark.parametrize('suffix',[
 ' ORDER BY ROW_ID FETCH FIRST 100 ROWS ONLY',
 ' AND DOCUMENT_ID=:document_id ORDER BY ROW_ID FETCH FIRST 100 ROWS ONLY',
 " AND (DOCUMENT_ID IS NULL OR DOCUMENT_ID IN (SELECT did FROM JSON_TABLE(:docs,'$[*]' COLUMNS(did VARCHAR2(512) PATH '$')))) ORDER BY ROW_ID FETCH FIRST 100 ROWS ONLY",
 " AND OWNER_ID=:owner_id AND NLSSORT(ROW_ID,'NLS_SORT=BINARY')>NLSSORT(:after,'NLS_SORT=BINARY') ORDER BY ROW_ID FETCH FIRST 100 ROWS ONLY"])
def test_narrow_records_only_preserves_every_other_byte(suffix):
 m,rt,c,prefix=fixture();sql=prefix+suffix;binds=[('kind','nav.test','VARCHAR2')]
 old=rt.rewrite_reads(sql,c);new=m.mapped_reads(rt,c,sql,binds)
 assert new==old.replace('ALL_ROWS','NARROW_ROWS')

@pytest.mark.parametrize('change',['or','union','other_select','missing_bind','duplicate_bind','wrong_type','no_extension','joined'])
def test_noncanonical_query_preserves_full_legacy_view(change):
 m,rt,c,prefix=fixture();sql=prefix+' ORDER BY ROW_ID';binds=[('kind','nav.test','VARCHAR2')]
 if change=='or':sql=prefix+' OR DOCUMENT_ID=:extra ORDER BY ROW_ID'
 if change=='union':sql=prefix+' UNION SELECT * FROM '+ROW
 if change=='other_select':sql='SELECT COUNT(*) FROM '+ROW+' WHERE KIND=:kind'
 if change=='missing_bind':binds=[]
 if change=='duplicate_bind':binds*=2
 if change=='wrong_type':binds=[('kind','nav.test','CLOB')]
 if change=='no_extension':c.manifest=None
 if change=='joined':sql=sql.replace(' WHERE',' JOIN '+ROW+' other ON 1=1 WHERE')
 assert m.mapped_reads(rt,c,sql,binds)==rt.rewrite_reads(sql,c)

def test_undeclared_kind_rejected_before_sql():
 m,rt,c,prefix=fixture()
 with pytest.raises(RuntimeError,match='EXTENSION_KIND'):m.mapped_reads(rt,c,prefix+' ORDER BY ROW_ID',[('kind','not.published','VARCHAR2')])
