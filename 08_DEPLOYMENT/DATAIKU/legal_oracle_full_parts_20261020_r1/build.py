from pathlib import Path
import hashlib,importlib,json,shutil,sys,zipfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PACKAGE=HERE/'package';BACKEND=ROOT/'02_BACKEND'
sys.path.insert(0,str(BACKEND))
# Exact maintained dependencies, including lazy projection imports. No app startup.
for name in ['lawrag.pipeline.oracle_full_package','lawrag.pipeline.oracle_query_dataiku','lawrag.pipeline.oracle_query_navigation_publish',
             'semantic_runtime.filename_versions','semantic_runtime.legal_agent.errors','semantic_runtime.term_index','semantic_runtime.search_selection','semantic_runtime.multi_entry_navigation','semantic_runtime.folder_navigation']:
    importlib.import_module(name)
paths=sorted(set(Path(m.__file__).resolve().relative_to(BACKEND) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(BACKEND)))
for rel in paths:
    dest=PACKAGE/'runtime'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BACKEND/rel,dest)
pins={str(p.relative_to(PACKAGE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((PACKAGE/'runtime').rglob('*.py'))}
pins['entry.py']=hashlib.sha256((PACKAGE/'entry.py').read_bytes()).hexdigest()
(PACKAGE/'CODE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
if (HERE/'notebook_template.py').exists():
    text=(HERE/'notebook_template.py').read_text().replace('__PINS_HASH__',hashlib.sha256((PACKAGE/'CODE_PINS.json').read_bytes()).hexdigest())
    (PACKAGE/'DATAIKU_FULL_IMPORT_RUN.txt').write_text(text)
    cells=[{'cell_type':'markdown','metadata':{},'source':['# 전체 데이터 Oracle 적재\n','Managed Folder ID와 Oracle 연결 이름을 설정하고 restore → check → publish → status 순서로 실행합니다.\n','전체 원문·자산·조회 데이터를 적재하며 테이블 재생성과 활성 포인터 전환은 하지 않습니다.']},
           {'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':text.splitlines(keepends=True)}]
    (PACKAGE/'DATAIKU_FULL_IMPORT.ipynb').write_text(json.dumps({'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'nbformat':4,'nbformat_minor':4},ensure_ascii=False,indent=2)+'\n')
for path in PACKAGE.rglob('*.py'):compile(path.read_bytes(),str(path),'exec')
zipname='LEGAL_ORACLE_FULL_PARTS_20261020_R1.zip'
with zipfile.ZipFile(HERE/zipname,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(PACKAGE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
            assert path.suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.write(path,'LEGAL_ORACLE_FULL_PARTS_20261020_R1/'+str(path.relative_to(PACKAGE)))
print(json.dumps({'runtime_files':len(paths),'zip':str(HERE/zipname),'bytes':(HERE/zipname).stat().st_size}))
