import ast
import hashlib
import json
from pathlib import Path
import zipfile
import oracle_queries

HERE=Path(__file__).parent
ZIP='DATAIKU_NFS_TABLE_CAPACITY_20261103_R1.zip'
sql='-- Dataiku AIDP SQL 노트북. 번호별 SELECT를 한 셀씩 실행하세요. 읽기 전용입니다.\n-- DBA 권한 오류/0행은 용량0을 뜻하지 않습니다. 자세한 범위는 GUIDE.txt.\n\n'
for name,value in oracle_queries.SQL.items():
    sql+='-- '+name+'\n'+value+';\n\n'
(HERE/'ORACLE_TABLE_CAPACITY_R1.sql').write_text(sql,encoding='utf-8')
(HERE/'ORACLE_TABLE_CAPACITY_R1.txt').write_text(sql,encoding='utf-8')
names=['capacity.py','oracle_queries.py','target_contract.json','ORACLE_TABLE_CAPACITY_R1.sql','GUIDE.txt']
manifest={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in names}
(HERE/'CODE_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
with zipfile.ZipFile(HERE/ZIP,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in names+['CODE_MANIFEST.json']:archive.write(HERE/name,name)
with zipfile.ZipFile(HERE/ZIP) as archive:
    assert all(Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs','.zip') for n in archive.namelist())
sha=hashlib.sha256((HERE/ZIP).read_bytes()).hexdigest()
launch=(HERE/'launch_template.py').read_text().replace('__ZIP_NAME__',ZIP).replace('__ZIP_SHA256__',sha)
ast.parse(launch,feature_version=(3,9))
(HERE/'DATAIKU_NFS_TABLE_CAPACITY_RUN_R1.txt').write_text(launch,encoding='utf-8')
attachments=[ZIP,'DATAIKU_NFS_TABLE_CAPACITY_RUN_R1.txt','ORACLE_TABLE_CAPACITY_R1.sql','ORACLE_TABLE_CAPACITY_R1.txt','GUIDE.txt']
metadata={n:dict(bytes=(HERE/n).stat().st_size,sha256=hashlib.sha256((HERE/n).read_bytes()).hexdigest()) for n in attachments}
(HERE/'ATTACHMENTS.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(metadata,ensure_ascii=False,indent=2))
