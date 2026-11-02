from common import *
import sqlite3
b=read(DES/'baseline.json');data=ROOT/b['manifest']['data_path'];did='7bbe815ff43b6635';nav=read(data/'navigation/manifest.json');full=data/read(data/'manifest.json')['fulltext']['path']
with sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True) as db:
 units={str(x[0]) for x in db.execute('select unit_id from source_block where document_id=? and block_id in (?,?,?,?)',(did,'1420','1421','1422','1423'))}
with sqlite3.connect((full/'units.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True) as db:
 rows=[dict(key=k,source_id=sid,unit_id=json.loads(raw)['unit_id']) for k,sid,raw in db.execute("select key,source_id,json from unit where document_id=? and json_extract(json,'$.unit_id') in (select value from json_each(?))",(did,json.dumps(sorted(units))))]
assert len(rows)==4
put(DES/'scope-fixture.json',{'document_id':did,'units':sorted(units),'expected_rows':rows,'data_manifest':bind(data/'manifest.json'),'fulltext_manifest':bind(full/'manifest.json'),'method':'Read-only immutable source mirror used only to freeze expected technical key/ID parity; no model or answer input'})
print('Scope fixture',len(units),'units',len(rows),'keys')
