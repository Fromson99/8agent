"""Build a data-free, credential-free Dataiku handoff and schema workbook."""
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'02_BACKEND'),str(HERE)]
from vector_silver.schema import COLUMNS,TABLE_META,description,statements
from semantic_runtime.initial_vector import table
import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment,Font,PatternFill

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(name,text):
    p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')

create=['-- 개발 SIDDS: 신규 벡터 3테이블 / 18컬럼. 기존 원문 테이블 변경·삭제 없음.',
        '-- Oracle native VECTOR 필요. SQL Developer/SQLcl 스크립트 실행(F5). ORDS는 / 구분 없이 블록별 실행.',
        '-- CREATE 권한이 없으면 이 파일로 DBA에게 생성 요청. 운영 Gold 승인 DDL이 아님.']
for s in statements():
    if s.startswith('CREATE '):
        create.append("BEGIN\n  EXECUTE IMMEDIATE '"+s.replace("'","''")+"';\nEXCEPTION WHEN OTHERS THEN\n  IF SQLCODE <> -955 THEN RAISE; END IF;\nEND;\n/")
    else:create.append(s+';')
put('01_CREATE_VECTOR_SILVER.sql','\n\n'.join(create)+'\n')
put('00_CHECK_TARGET.sql',"""-- 읽기 전용. 연결 이름 AIDP와 DB owner SIDDS는 다른 값입니다.
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER,
       SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL;
SELECT VECTOR_DIMENSION_COUNT(TO_VECTOR('[1,0]',2,FLOAT32)) AS DIMENSIONS,
       VECTOR_DISTANCE(TO_VECTOR('[1,0]',2,FLOAT32),TO_VECTOR('[1,0]',2,FLOAT32),COSINE) AS DISTANCE FROM DUAL;
-- 정상 기대값 2 / 0. VECTOR 미지원이면 생성·적재 중단.
SELECT OWNER,TABLE_NAME,COUNT(*) AS COLUMN_COUNT FROM ALL_TAB_COLUMNS
 WHERE OWNER IN ('SIDDS','SIDDA') AND TABLE_NAME IN
 ('LGL_DOC_VER_S','LGL_DOC_UNIT_S','LGL_DOC_BLK_S','LGL_FILE_PART_S','LGL_SRC_PBLS_S',
  'LGL_SRCH_ROW_S','LGL_SRCH_PBLS_S','LGL_SRCH_CHNL_S','LGL_EXEC_ST_A',
  'LGL_VCTR_PBLS_S','LGL_VCTR_SEG_S','LGL_VCTR_ACT_S')
 GROUP BY OWNER,TABLE_NAME ORDER BY OWNER,TABLE_NAME;
""")
put('02_CHECK_VECTOR.sql',"""-- 생성 후/적재 후 조회. 테이블이 없으면 오류를 성공으로 처리하지 않습니다.
SELECT TABLE_NAME,COLUMN_ID,COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,NULLABLE
FROM ALL_TAB_COLUMNS WHERE OWNER='SIDDS'
AND TABLE_NAME IN ('LGL_VCTR_PBLS_S','LGL_VCTR_SEG_S','LGL_VCTR_ACT_S') ORDER BY TABLE_NAME,COLUMN_ID;
-- 예상 컬럼수 PBLS=8 / SEG=7 / ACT=3. 18개.
SELECT TABLE_NAME,CONSTRAINT_NAME,CONSTRAINT_TYPE,STATUS,VALIDATED FROM ALL_CONSTRAINTS
WHERE OWNER='SIDDS' AND TABLE_NAME IN ('LGL_VCTR_PBLS_S','LGL_VCTR_SEG_S','LGL_VCTR_ACT_S');
SELECT INDEX_NAME,COLUMN_NAME,COLUMN_POSITION FROM ALL_IND_COLUMNS
WHERE INDEX_OWNER='SIDDS' AND TABLE_NAME='LGL_VCTR_SEG_S' ORDER BY INDEX_NAME,COLUMN_POSITION;
SELECT r.PUB_ID,r.QUERY_ID,r.STATUS,r.EXPECTED_COUNT,r.ACTUAL_COUNT,
 (SELECT COUNT(*) FROM SIDDS.LGL_VCTR_SEG_S s WHERE s.PUB_ID=r.PUB_ID) AS STORED_ROWS
FROM SIDDS.LGL_VCTR_PBLS_S r;
SELECT PUB_ID,VECTOR_DIMENSION_COUNT(EMBEDDING) AS DIMENSIONS,
 VECTOR_DIMENSION_FORMAT(EMBEDDING) AS FORMAT,COUNT(*) AS ROWS_N
FROM SIDDS.LGL_VCTR_SEG_S
GROUP BY PUB_ID,VECTOR_DIMENSION_COUNT(EMBEDDING),VECTOR_DIMENSION_FORMAT(EMBEDDING);
SELECT a.QUERY_ID,a.PUB_ID,a.REVISION,r.STATUS FROM SIDDS.LGL_VCTR_ACT_S a
JOIN SIDDS.LGL_VCTR_PBLS_S r ON a.PUB_ID=r.PUB_ID;
-- READY / 예상=실제=저장건수 / PROFILE_JSON 차원 일치 / FLOAT32 확인.
""")
mapping=yaml.safe_load((ROOT/'00_SYSTEM/ORACLE/physical_mapping.yaml').read_text())
owners=mapping['profiles']['dev_silver']['owner_by_role']
tables=[];columns=[]
for key,t in mapping['tables'].items():
    owner=owners[t['role']]
    tables.append([owner,t['name'],len(t['columns']),'기존 이관 대상' if owner=='SIDDS' else '별도 Agent',
                   t['role'],'현장 생성 미확인','운영명·표준 매핑·승인 미확인',t['description']])
    for i,(alias,c) in enumerate(t['columns'].items(),1):
        logical=re.search(r'논리명[^:]*:\s*([^\n]+)',c['description'])
        columns.append([owner,t['name'],i,c['name'],logical.group(1) if logical else '',c['type'],
                        'Y' if c['nullable'] else 'N',str(c.get('default') or ''),
                        'Y' if alias in t.get('pk',[]) else 'N','표준조회 필요','표준조회 필요','표준조회 필요',c['description']])
for key,cols in COLUMNS.items():
    name=table(key).split('.')[1]
    tables.append(['SIDDS',name,len(cols),'이번 신규 생성','gold_knowledge' if key=='segment' else 'gold_support',
                   '코드 작성; 현장 생성 미확인','운영 Gold 후보; 승인 미완료',description(key)])
    pk={'release':['PUB_ID'],'segment':['PUB_ID','SEG_ID'],'active':['QUERY_ID']}[key]
    for i,(namecol,typ,nullable,logical,desc) in enumerate(cols,1):
        columns.append(['SIDDS',name,i,namecol,logical,typ,'Y' if nullable else 'N','0' if namecol=='ACTUAL_COUNT' else '',
                        'Y' if namecol in pk else 'N','표준조회 필요','표준조회 필요','표준조회 필요',desc])
headers1=['개발스키마','물리테이블명','컬럼수','범위','운영분류후보','현장상태','승인상태','테이블Description']
headers2=['개발스키마','테이블명','순번','물리컬럼명','논리명후보','타입','NULL허용','기본값','PK','표준용어','표준도메인','인포타입','컬럼Description']
book=Workbook();book.remove(book.active)
def sheet(title,headers,rows):
    ws=book.create_sheet(title);ws.append(headers)
    for row in rows:ws.append(row)
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    for c in ws[1]:c.font=Font(color='FFFFFF',bold=True);c.fill=PatternFill('solid',fgColor='224D63')
    for row in ws.iter_rows(min_row=2):
        for c in row:c.alignment=Alignment(vertical='top',wrap_text=True)
    for col in ws.columns:
        letter=col[0].column_letter;ws.column_dimensions[letter].width=65 if 'Description' in str(col[0].value) else 24
    for idx in range(2,ws.max_row+1):ws.row_dimensions[idx].height=72
    return ws
sheet('테이블목록',headers1,tables)
sheet('전체컬럼정의',headers2,columns)
sheet('벡터컬럼18',headers2,[r for r in columns if r[1].startswith('LGL_VCTR_')])
sheet('골드신청확인',['항목','내용'],[
 ['범위','기존 실버 8개 41컬럼 + 신규 벡터 3개 18컬럼 = 실버 11개 59컬럼. Agent 1개 5컬럼 별도. 현장 실측 아님.'],
 ['사용자 요청','개발계는 SIDDS.*_S, 운영에는 벡터 지식의 Gold 등록 준비.'],
 ['표준','현재 물리명은 기존 소비자 계약 유지용. 표준단어·용어·도메인·인포타입은 메타마이너 조회·승인 필요.'],
 ['운영 대상','SEG는 검색 지식, PBLS/ACT는 게시 지원 후보. 상세 실행 로그는 Dataiku/Agent. LEASE_ID의 운영 레이어 분리 검토.'],
 ['VECTOR','VECTOR(*,FLOAT32) 메타 도메인 등록·지원 여부 확인. 1024 숫자는 1024 컬럼이 아니라 VECTOR 한 컬럼의 차원.'],
 ['JSON','PROFILE_JSON/MANIFEST_JSON/META_JSON 내부 속성은 물리 컬럼 수에 추가하지 않음. 운영 등록 시 JSON 도메인/분리 필요 검토.'],
 ['운영명','Gold owner·물리명은 미확정. 승인 후 적재기와 GENOS 소비자 매핑을 함께 변경·검증.'],
 ['신청상태','전부 작성 후보. 표준신청·메타 등록·DBA 생성·현장 적재 완료를 뜻하지 않음.'],
 ['기타필수','관리부서·담당자·보유기간·개인정보 여부·업무표준사전·에이전트 3/5 귀속을 최종 신청자가 확인.']])
sheet('벡터Bizmeta',['테이블','논리명후보','유형후보','행단위','데이터출처','가공과정','생성시각','예시SQL'],[
 [table(k),TABLE_META[k][0],TABLE_META[k][1],TABLE_META[k][2],'완료 원문/조회 릴리스 → GENOS 임베딩',
  '원문·권한 결속 → 800자 분할 → 동일 모델 임베딩 → 검증 → READY → 활성 선택',
  'Dataiku 작업 완료 시점; 현행 테이블에는 전용 생성시각 컬럼 없음. Dataiku 이력 참조.',
  'SELECT * FROM '+table(k)+' FETCH FIRST 10 ROWS ONLY;'] for k in COLUMNS])
book.save(HERE/'TABLE_COLUMNS_GOLD_DRAFT.xlsx')
for name,head,rows in [('TABLES.csv',headers1,tables),('COLUMNS.csv',headers2,columns)]:
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(head);w.writerows(rows)

binding=HERE/'BASE_BINDING.json'
if not binding.exists():
    # Subsequent packaging must not silently move when another task promotes MAIN.
    current=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    binding.write_text(json.dumps(current,ensure_ascii=False,indent=2))
active=json.loads(binding.read_text())
release=json.loads((ROOT/active['manifest_path']).read_text())
base=ROOT/release['code_root']
payload=HERE/'payload';payload.mkdir(exist_ok=True)
sources={}
for name,h in release['files'].items():
    if name.startswith('02_BACKEND/') and name.endswith('.py') or name=='00_SYSTEM/ORACLE/physical_mapping.yaml':
        assert sha(base/name)==h
        sources[name]=base/name
for name in ['02_BACKEND/lawrag/pipeline/__init__.py','02_BACKEND/lawrag/pipeline/oracle_query_dataiku.py']:
    sources[name]=ROOT/name
for path in (HERE/'vector_silver').glob('*.py'):sources['vector_silver/'+path.name]=path
for name in ['00_CHECK_TARGET.sql','01_CREATE_VECTOR_SILVER.sql','02_CHECK_VECTOR.sql','GUIDE.txt','requirements.txt']:
    if (HERE/name).exists():sources[name]=HERE/name
for old in list(payload.rglob('*')):
    if old.is_file() and str(old.relative_to(payload)) not in sources and old.name!='CODE_MANIFEST.json':old.unlink()
for name,path in sources.items():
    dest=payload/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
manifest={'format':'vector-silver-dataiku-v1','base_release':active['release_id'],'base_generation':active['generation'],
          'scope':'Dataiku only; no MAIN/GENOS deployment','files':{name:sha(path) for name,path in sorted(sources.items())}}
(payload/'CODE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
archive=HERE/'VECTOR_SILVER_CODE_20261029_R1.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name in sorted(manifest['files']):z.write(payload/name,name)
    z.write(payload/'CODE_MANIFEST.json','CODE_MANIFEST.json')
bootstrap='''import dataiku,hashlib,io,json,pathlib,sys,tempfile,zipfile,atexit,shutil
_folder=dataiku.Folder("ehA8dpVm")
with _folder.get_download_stream("VECTOR_SILVER_CODE_20261029_R1.zip") as _stream:_raw=_stream.read(32*1024*1024+1)
if len(_raw)>32*1024*1024 or hashlib.sha256(_raw).hexdigest()!="ARCHIVE_HASH":raise ValueError("VECTOR_CODE_HASH")
_root=pathlib.Path(tempfile.mkdtemp(prefix="legal-vector-code-"));atexit.register(shutil.rmtree,_root,ignore_errors=True)
with zipfile.ZipFile(io.BytesIO(_raw)) as _z:
 _names=_z.namelist()
 if len(_names)!=len(set(_names)) or sum(i.file_size for i in _z.infolist())>64*1024*1024:raise ValueError("VECTOR_ARCHIVE_SIZE_OR_DUPLICATE")
 _manifest=json.loads(_z.read("CODE_MANIFEST.json"))
 if set(_names)!=set(_manifest["files"])|{"CODE_MANIFEST.json"}:raise ValueError("VECTOR_ARCHIVE_NAMES")
 for _entry in _z.infolist():
  _p=pathlib.PurePosixPath(_entry.filename)
  if _p.is_absolute() or ".." in _p.parts or (_entry.external_attr>>16)&0o170000==0o120000:raise ValueError("VECTOR_ARCHIVE_PATH")
  if _entry.filename=="CODE_MANIFEST.json":continue
  _body=_z.read(_entry.filename)
  if hashlib.sha256(_body).hexdigest()!=_manifest["files"][_entry.filename]:raise ValueError("VECTOR_FILE_HASH")
  _dest=_root/_entry.filename;_dest.parent.mkdir(parents=True,exist_ok=True);_dest.write_bytes(_body)
# Refuse an already imported different package instead of mixing revisions in a notebook.
for _name in ("semantic_runtime","lawrag","vector_silver"):
 if _name in sys.modules:
  _loaded=pathlib.Path(sys.modules[_name].__file__).resolve()
  _relative=("02_BACKEND/" if _name!="vector_silver" else "")+_name+"/__init__.py"
  if not _loaded.is_relative_to(_root):raise ValueError("RESTART_NOTEBOOK_KERNEL_BEFORE_INSTALL: "+_name)
sys.path[:0]=[str(_root/"02_BACKEND"),str(_root)]
'''.replace('ARCHIVE_HASH',sha(archive))
put('BOOTSTRAP.py',bootstrap)
settings='''# LEGAL_RAG Python 노트북. 코드 ZIP을 ehA8dpVm 루트에 업로드한 후 실행.
# 첫 설치는 모델 정보 공란으로 가능. 임베딩 실행 전 실제 배포값을 채워 재설치(커널 재시작).
EMBED_MODEL = ""
EMBED_REVISION = ""
EMBED_DIMENSIONS = 0
LOAD_RESULT_FOLDER_ID = ""  # 공란: 기존 LEGAL_LGL_LOAD_RESULT_R1 자동 확인
LOAD_RECEIPT_PATH = ""  # 완료 기록이 여러 개면 jobs/<job>/complete.json 지정
'''
install=settings+bootstrap+'''\nfrom vector_silver.install import install
VECTOR_CFG=install(dataiku.api_client().get_default_project(), BOOTSTRAP,
 load_id=LOAD_RESULT_FOLDER_ID, model=EMBED_MODEL, revision=EMBED_REVISION,
 dimensions=EMBED_DIMENSIONS, receipt_path=LOAD_RECEIPT_PATH)
print("설치만 완료. 아래 별도 실행 셀에서 schema/check를 먼저 실행하세요.")
'''.replace('BOOTSTRAP,',repr(bootstrap)+',')
put('DATAIKU_INSTALL.txt',install)
put('DATAIKU_RUN.txt','''# DATAIKU_INSTALL.txt를 실행한 동일 노트북의 새 셀에서 실행합니다.
# SQL 파일로 이미 생성했으면 check부터. schema는 같은 3테이블 생성·검사이며 기존 데이터 삭제 없음.
ACTION = "check"  # "schema" / "check" / "build"
from vector_silver.runtime import run
VECTOR_RESULT = run(VECTOR_CFG, action=ACTION)
print(VECTOR_RESULT)
# build는 Flow LEGAL_04_VECTOR_SILVER_R2의 Run으로 실행해도 같습니다.
''')
put('BUILD_RECEIPT.json',json.dumps({'base_release':active['release_id'],'files':len(sources),
    'code_zip_sha256':sha(archive),'vector_tables':3,'vector_columns':18,'silver_tables':11,'silver_columns':59,
    'agent_tables':1,'agent_columns':5,'field_deployment':False,'external_model_calls':0},ensure_ascii=False,indent=2))
print(json.dumps({'files':len(sources),'zip_bytes':archive.stat().st_size,'vector_columns':18,'silver_columns':59}))
