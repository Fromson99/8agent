from pathlib import Path
import hashlib,json,zipfile
p=Path(__file__).resolve().parent
for name in ('CATALOG.json','TABLE_LIST.txt'):
 q=p/name;q.write_text(q.read_text().replace('旧 벡터','구형 벡터'))
catalog=json.loads((p/'CATALOG.json').read_text())
code=(p/'inventory.py').read_text()+'\n\nCATALOG = '+repr(catalog)+'\nRESULTS, RESULT_CSV = run(CATALOG)\n'
compile(code,'DATAIKU_TABLE_INVENTORY_R4.txt','exec')
(p/'DATAIKU_TABLE_INVENTORY_R4.txt').write_text(code)
with zipfile.ZipFile(p/'DATAIKU_TABLE_INVENTORY_20261102_R4.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name in ('inventory.py','CATALOG.json','TABLE_LIST.txt'):
  z.writestr(name,(p/name).read_bytes())
with zipfile.ZipFile(p/'DATAIKU_TABLE_INVENTORY_20261102_R4.zip') as z:
 assert z.testzip() is None
 assert not any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in z.namelist())
files=['DATAIKU_TABLE_INVENTORY_20261102_R4.zip','DATAIKU_TABLE_INVENTORY_R4.txt','TABLE_LIST.txt','GUIDE.txt']
(p/'VALIDATION.json').write_text(json.dumps({'status':'LOCAL_MOCK_VALIDATED_FIELD_NOT_EXECUTED','known_names':len(catalog),'current_targets':sum(v['current_target'] for v in catalog),'tests_passed':8,'actual_field_counts':None,'db_mutations':0,'attachments':[{'name':n,'bytes':(p/n).stat().st_size,'sha256':hashlib.sha256((p/n).read_bytes()).hexdigest()} for n in files]},ensure_ascii=False,indent=2)+'\n')
print('Prepared 44-table catalog, read-only count cell, code ZIP, guide; no field SQL executed')
