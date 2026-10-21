from pathlib import Path
import hashlib,importlib,json,shutil,sys,zipfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PACKAGE=HERE/'package';BACKEND=ROOT/'02_BACKEND'
sys.path.insert(0,str(BACKEND))
# Exact maintained dependencies, including lazy projection imports. No app startup.
for name in ['lawrag.pipeline.oracle_clean_import','lawrag.pipeline.oracle_import_stop','lawrag.pipeline.oracle_legacy_parts','lawrag.pipeline.oracle_existing_zip','lawrag.pipeline.oracle_query_dataiku','lawrag.pipeline.oracle_query_navigation_publish',
             'semantic_runtime.filename_versions','semantic_runtime.legal_agent.errors','semantic_runtime.term_index','semantic_runtime.search_selection','semantic_runtime.multi_entry_navigation','semantic_runtime.folder_navigation']:
    importlib.import_module(name)
paths=sorted(set(Path(m.__file__).resolve().relative_to(BACKEND) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(BACKEND)))
for rel in paths:
    dest=PACKAGE/'runtime'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BACKEND/rel,dest)
pins={str(p.relative_to(PACKAGE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((PACKAGE/'runtime').rglob('*.py'))}
pins['entry.py']=hashlib.sha256((PACKAGE/'entry.py').read_bytes()).hexdigest()
(PACKAGE/'CODE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
stop_path=PACKAGE/'STOP_OLD_IMPORT_RUN.txt'
previous=stop_path.read_text()
header=previous[:previous.index('"""Inspect/stop')]
footer=previous[previous.index('\nif WORK_DIR:'):]
stop_source=(BACKEND/'lawrag/pipeline/oracle_import_stop.py').read_text().replace(
    'from semantic_runtime.oracle_dp_io import DPError','class DPError(RuntimeError):\n    pass')
stop_path.write_text(header+stop_source+footer)
if (HERE/'notebook_template.py').exists():
    text=(HERE/'notebook_template.py').read_text().replace('__PINS_HASH__',hashlib.sha256((PACKAGE/'CODE_PINS.json').read_bytes()).hexdigest())
    (PACKAGE/'DATAIKU_CLEAN_IMPORT_RUN.txt').write_text(text)
    cells=[{'cell_type':'markdown','metadata':{},'source':['# 전체 데이터 Oracle 적재\n','별도 새 노트북에서 inspect_processes → stop → plan → replace. 기존 WORK_DIR를 유지하세요.\n','데이터 7테이블만 삭제 후 재적재합니다. ACTIVE/STATE는 보존하며 활성 포인터가 있으면 삭제를 차단합니다.']},
           {'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':text.splitlines(keepends=True)}]
    (PACKAGE/'DATAIKU_CLEAN_IMPORT.ipynb').write_text(json.dumps({'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'nbformat':4,'nbformat_minor':4},ensure_ascii=False,indent=2)+'\n')
for path in PACKAGE.rglob('*.py'):compile(path.read_bytes(),str(path),'exec')
for path in PACKAGE.glob('*_RUN.txt'):compile(path.read_bytes(),str(path),'exec')
zipname='LEGAL_ORACLE_CLEAN_IMPORT_20261020_R1.zip'
with zipfile.ZipFile(HERE/zipname,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(PACKAGE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
            assert path.suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.write(path,'LEGAL_ORACLE_CLEAN_IMPORT_20261020_R1/'+str(path.relative_to(PACKAGE)))
print(json.dumps({'runtime_files':len(paths),'zip':str(HERE/zipname),'bytes':(HERE/zipname).stat().st_size}))
