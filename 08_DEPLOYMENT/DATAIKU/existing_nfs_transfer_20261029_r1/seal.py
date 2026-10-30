"""Seal validated handoff and prepare the explicitly requested Samsung email."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name, value): (HERE/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

assert not (HERE/'SEALED.json').exists(), 'Do not replace sealed delivery'
assert '48 passed' in (HERE/'test-qualified.log').read_text()
build=json.loads((HERE/'BUILD.json').read_text())
for name, expected in build['files'].items():
    assert sha(HERE/name)==expected['sha256'] and (HERE/name).stat().st_size==expected['bytes']
for name in ('GENOS_EXISTING_NFS_INSTALL.txt','ROLLBACK_GENOS.txt'):
    subprocess.run(['bash','-n',str(HERE/name)],check=True)
ast.parse((HERE/'DATAIKU_EXISTING_NFS_RUN.txt').read_text(),feature_version=(3,9))
for archive in ('GENOS_EXISTING_NFS_20261029_R1.zip','DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip'):
    with zipfile.ZipFile(HERE/archive) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        for name in z.namelist():
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            if name.endswith('.py'): ast.parse(z.read(name),feature_version=(3,9))
save('VALIDATION.json',{
    'status':'LOCAL_CONTRACTS_PASSED','unique_tests':48,'test_log_sha256':sha(HERE/'test-qualified.log'),
    'python':sys.version,'server_code_sha256':build['server_code_sha256'],
    'checks':['whole delivered Dataiku notebook check/transfer/load/status with SDK+Oracle boundary fixtures',
              '503 read retry and capped exhaustion; original deadline and reserved budget retained',
              'whole local scratch loss restores from managed-folder chunks and Oracle receipts without duplicate writes',
              'source byte/mtime unchanged, changed source/metadata/WAL/selection and undeclared file rejected',
              '3.3MB fulltext manifest accepted with metadata16MiB',
              'native delivered async service INFO/READ and no compute handles',
              'actual synthetic Git checkout apply/reapply/stage/commit/code verification/generation E2E/verify_assets/rollback',
              'existing full importer regressions and silver/agent mapping contracts',
              'bash syntax; Python3.9 parse for packaged Python; no JavaScript recursively'],
    'mock_boundaries':['Dataiku SDK/Oracle execution ports','fixed NFS root replaced with synthetic fixture in native tests'],
    'earlier_build_error':'INITIAL_FAILURES.json','earlier_test_failures':0,
    'review_correction':'NFS_VERIFY runs in check and before push, not in pre-commit stage; environment/commit/entry hashes reported',
    'field_nfs_bytes_verified':False,'field_revision_verified':False,'field_oracle_loaded':False,
    'new_model_calls':0,'main_changed':False,'active_release_changed':False,
    'performance_or_legal_quality_certification':False})
save('FIELD_OBSERVATION.json',{
    'source':'2026-10-29 user notebook photos after MAX_METADATA=16*1024*1024',
    'generation':build['generation'],'metadata_errors':[],
    'files_present':['store.sqlite','manifest.json','navigation/manifest.json','navigation/navigation.sqlite',
                     'fulltext/manifest.json','fulltext/units.sqlite','glossary/bundle/manifest.json',
                     'glossary/dictionary.sqlite','glossary/cache receipt and sqlite'],
    'source_sqlite_absent_is_normal':True,'source_bytes_verified':False,
    'same_document_scope_as_new_raw_input':None,'exact_manifest_hash_from_photo':None,
    'previous_fulltext_ValueError':'R1 inspector metadata cap1MiB; preserved; current photo has errors=[]'})
names=['GENOS_EXISTING_NFS_20261029_R1.zip','DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip',
       'GENOS_EXISTING_NFS_INSTALL.txt','DATAIKU_EXISTING_NFS_RUN.txt','ROLLBACK_GENOS.txt','GUIDE.txt',
       'VALIDATION.json','BUILD.json','CODE_MANIFEST.json','FIELD_OBSERVATION.json','INITIAL_FAILURES.json','test-qualified.log']
archive=HERE/'DATAIKU_EXISTING_NFS_20261029_R1.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name in names:
        item=zipfile.ZipInfo(name,(2026,10,29,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
        item.external_attr=0o100644<<16;z.writestr(item,(HERE/name).read_bytes())
def inspect(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            if name.lower().endswith('.zip'):inspect(z.read(name))
inspect(archive.read_bytes())
attachments=[archive.name,'GENOS_EXISTING_NFS_INSTALL.txt','DATAIKU_EXISTING_NFS_RUN.txt','GUIDE.txt']
receipt={'files':{n:{'sha256':sha(HERE/n),'bytes':(HERE/n).stat().st_size} for n in [*names,archive.name]},
         'attachments':attachments,'server_code_sha256':build['server_code_sha256'],
         'field_revision':None,'actual_field_commit':None,'generation':build['generation']}
save('SEALED.json',receipt)
html='''<p>사진의 새 출력에서 errors=[]와 기존 원문·탐색·검색·용어집 SQLite 파일 존재가 확인되어, 기존 데이터를 재사용하는 이관 R1을 보냅니다.</p>
<p><b>구조화와 재색인을 다시 하지 않습니다.</b> 고정된 NFS generation을 작은 조각으로 읽어 Dataiku에 보관하고 기존 Oracle 적재기로 연결합니다. 수신 중단 시 저장된 조각을 재사용합니다.</p>
<ol><li>첨부 ZIP을 실제 TRANSFER 폴더에서 풀고, 그 안에서 <b>bash GENOS_EXISTING_NFS_INSTALL.txt</b>를 실행합니다. 기존 계산용 ~/DEV를 백업·반영·검증·commit·push한 뒤 GENOS 화면에서 새 리비전을 배포합니다.</li>
<li>내부 <b>DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip</b>을 LEGAL_RAG/ehA8dpVm에 업로드합니다.</li>
<li>Dataiku 새 Python 노트북에 <b>DATAIKU_EXISTING_NFS_RUN.txt</b> 전체를 붙여넣고 ACTION을 <b>check → transfer → load</b> 순서로 바꿔 실행합니다. 기존 00/01/02/03을 이 이관에 다시 실행하지 않습니다.</li></ol>
<p>이 메일은 이전 EXISTING_SQLITE_CHECK 진단용 메일의 다음 이관 단계입니다. 이전 진단 TXT를 설치 명령으로 사용하지 마세요. 현재 실행 중인 계산이 있다면 Dataiku에서 취소하고 GENOS 종료를 확인한 다음 리비전을 변경합니다.</p>
<p>로컬 48검사 통과: 전체 전달 노트북, 수신/이어받기, 모의 Oracle 적재·행 대조, 실제 service 진입점, 설치·원복 및 합성 generation 검증. 실제 NFS 내용 검증·현장 리비전·Dataiku 수신·Oracle 적재는 아직 완료되지 않았습니다. check/설치에서 실제 내용과 코드가 대조됩니다. load 완료 후에도 RAG 조회 release를 자동 전환하지 않습니다.</p>
<p>단계별 실행과 복원은 GUIDE.txt에 있습니다. 코드 ZIP 안에도 실행 TXT와 안내를 넣었고 JavaScript 파일은 제외했습니다.</p>'''
parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':html}}]
for name in attachments:
    parts.append({'mime_type':'application/zip' if name.endswith('.zip') else 'text/plain',
                  'filename':name,'content_disposition':'attachment',
                  'body':{'base64_url_content':base64.urlsafe_b64encode((HERE/name).read_bytes()).decode()}})
save('EMAIL_REQUEST.json',{'to':'hyungjininfocz.son@partner.samsung.com',
    'subject':'[기존 SQLite 재사용 R1] 구조화·재색인 없이 NFS → Dataiku → Oracle 이관',
    'payload':{'mime_type':'multipart/mixed','parts':parts},'response_fields':['id','thread_id','label_ids']})
print(json.dumps({'sealed':True,'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),
                  'attachment_count':len(attachments)},ensure_ascii=False))
