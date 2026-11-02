"""Additional-load launchers for the already validated, unchanged R1 runtime."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'gold_shape_silver_20261102_r1'
ZIP='DATAIKU_GOLD_SHAPE_20261102_R1.zip'
EXPECTED='c1df3b82c7e589500cc81ffd8c7e2b3794eee9d7b39472beb589d3151f538a2e'
source=(BASE/'DATAIKU_GOLD_SHAPE_RUN_R1.txt').read_text()
assert hashlib.sha256(source.encode()).hexdigest()=='1b99475d4936eda014a84182097666d716619a93d0620e3ae1b7e05463996cae'
raw=(BASE/ZIP).read_bytes()
assert hashlib.sha256(raw).hexdigest()==EXPECTED
with zipfile.ZipFile(BASE/ZIP) as z:
    assert z.testzip() is None
    names=z.namelist()
    assert len(names)==len(set(names))
    assert not any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in names)
    manifest=json.loads(z.read('CODE_MANIFEST.json'))
    assert set(names)==set(manifest['files'])|{'CODE_MANIFEST.json'}
    assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in manifest['files'].items())
(HERE/ZIP).write_bytes(raw)
old_line="ACTION = 'start'  # 첫 실행 start / 전체 적재 load / 전수검증·시험게시 verify_publish"
assert source.count(old_line)==1
outputs=[]
for action,name,title in [
    ('load','DATAIKU_GOLD_ADDITIONAL_INSERT_R1.txt','추가 INSERT: 초기 적재 성공 뒤 실행'),
    ('verify_publish','DATAIKU_GOLD_VERIFY_AFTER_LOAD_R1.txt','전수검증: LOADED_UNVERIFIED 뒤 실행'),
]:
    text=source.replace(old_line,"ACTION = '"+action+"'  # "+title)
    compile(text,name,'exec')
    before=ast.parse(source);after=ast.parse(text)
    def normalize(tree):
        count=0
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ACTION' for t in node.targets):
                node.value=ast.Constant(value='NORMALIZED_ACTION');count+=1
        assert count==1
        return ast.dump(tree,include_attributes=False)
    assert normalize(before)==normalize(after),'Unexpected executable change'
    (HERE/name).write_text(text)
    outputs.append(name)
names=[ZIP,*outputs,'GUIDE_ADDITIONAL_INSERT_R1.txt']
files=[{'name':n,'bytes':(HERE/n).stat().st_size,'sha256':hashlib.sha256((HERE/n).read_bytes()).hexdigest()} for n in names]
result={'status':'VALIDATED_HANDOFF_ONLY','runtime_changed':False,'zip_matches_previous_delivery':True,
        'execution_txts_compile':True,'only_executable_change':'ACTION start -> load / verify_publish',
        'zip_files_verified':len(manifest['files'])+1,'nested_zip_or_javascript':False,
        'field_execution':False,'attachments':files}
(HERE/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
