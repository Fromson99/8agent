from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parent.parent
out=root/'gold_restart_20261102_r8'
base=(root/'gold_shape_silver_20261102_r1/DATAIKU_GOLD_SHAPE_RUN_R1.txt').read_text()
helper=(out/'progress_display.py').read_text()
base=base.replace('def _run_gold_shape():', helper+'\n\ndef _run_gold_shape():')
base=base.replace("    lines=collections.OrderedDict()",'''    old_job = Path(OLD_JOB_DIR) if OLD_JOB_DIR else Path(tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'
    contract_sha = digest(json.loads((root/'contract.json').read_text()))
    display = Display(old_job, contract_sha, ACTION)
    display.render()  # Baseline before the child starts; resumed rows are not new throughput.
    log_dir = Path.cwd()/'gold-progress-logs'
    log_dir.mkdir(exist_ok=True)
    import uuid
    log_path = log_dir/(time.strftime('%Y%m%d-%H%M%S')+'-'+ACTION+'-'+uuid.uuid4().hex[:8]+'.log')
    log = log_path.open('x', encoding='utf-8')
    print('전체 진행 로그:', log_path, flush=True)
    lines=collections.OrderedDict()''')
base=base.replace("            line=line.strip()", "            log.write(line); log.flush()\n            line=line.strip()")
base=base.replace("            print('[Gold 형태 R1] 실행 단계:',ACTION,'/ 최근 상태 최대18줄')", "            summary = display.render()\n            log.write(summary+'\\n'); log.flush()\n            print('[Gold 진행 표시 R8] 실행 단계:', ACTION)\n            print(summary)\n            print('전체 진행 로그:', log_path)")
base=base.replace("        code=process.wait()", "        code=process.wait()\n        print(display.render())\n        log.write('PROCESS_EXIT='+str(code)+'\\n'+display.render()+'\\n'); log.flush()")
base=base.replace("        print('중단 요청을 전달했습니다. 진행 영수증을 보존했습니다. 마지막 DB 요청의 반영 여부는 재확인이 필요합니다.')", "        print('중단 요청을 전달했습니다. 진행 영수증을 보존했습니다. 마지막 DB 요청의 반영 여부는 재확인이 필요합니다.')")
# Close the display log whether the child exits or the user interrupts.
marker='\ntry:\n    _run_gold_shape()'
assert marker in base
base=base.replace(marker,"\n    finally:\n        log.close()\n"+marker)
base=base.replace("    lines=collections.OrderedDict()", "    diagnostic_errors = []\n    env['G19_DIAGNOSTIC_FILE'] = str(log_path.with_suffix('.errors.jsonl'))\n    lines=collections.OrderedDict()")
base=base.replace("[sys.executable,'-u',str(root/'run.py'),ACTION]", "[sys.executable,'-u',str(helper_root/'diagnostic_runner.py'),str(root),ACTION]")
base=base.replace("                value=json.loads(line)", "                value=json.loads(line)\n                display.observe(value)\n                if value.get('phase') == 'DIAGNOSTIC_ERROR':\n                    diagnostic_errors.append(value)\n                    print(error_banner(value), flush=True)")
base=base.replace("            clear_output(wait=True)", "            if not diagnostic_errors:\n                clear_output(wait=True)")
base=base.replace("        if code:", "        if code:\n            for failure in diagnostic_errors:\n                print(error_banner(failure), flush=True)")
for action,name in [('load','DATAIKU_GOLD_LOAD_PROGRESS_R8.txt'),('verify_publish','DATAIKU_GOLD_VERIFY_PROGRESS_R8.txt')]:
    content=base.replace("ACTION = 'start'", f"ACTION = '{action}'",1)
    compile(content,name,'exec')
    # Full R8 launcher below includes checked diagnostic helper loading.
print('generated two notebook cells; unchanged R1 ZIP')

# Keep the old R1 package byte-for-byte; all added code is outside its bound directory.
base=base.replace("            print('중단되었습니다. 이 화면을 캡처하고 후속 셀은 실행하지 마세요.')", "            raise RuntimeError(('\\n'.join(error_banner(failure) for failure in diagnostic_errors) or '적재/검증 중단: 자식 프로세스 출력을 확인하세요.')+'\\n로그: '+str(log_path))")
base=base.replace("        print('중단 요청을 전달했습니다. 진행 영수증을 보존했습니다. 마지막 DB 요청의 반영 여부는 재확인이 필요합니다.')", "        print('중단 요청을 전달했습니다. 진행 영수증을 보존했습니다. 마지막 DB 요청의 반영 여부는 재확인이 필요합니다.')\n        raise")
base=base[:base.index('\ntry:\n    _run_gold_shape()')]
helpers={n:(out/n).read_text() for n in ('progress_display.py','mesh_embedding.py','vector_stage.py','error_diagnostics.py','diagnostic_runner.py','reset_source.py','jdbc_transport.py')}
helper_zip_name = 'DATAIKU_GOLD_RESTART_20261102_R8.zip'
helper_manifest = {name:hashlib.sha256(content.encode()).hexdigest() for name,content in helpers.items()}
with zipfile.ZipFile(out/helper_zip_name,'w',zipfile.ZIP_DEFLATED) as z:
    for name,content in helpers.items(): z.writestr(name,content)
    z.writestr('MANIFEST.json',json.dumps(helper_manifest,sort_keys=True))
helper_zip_hash = hashlib.sha256((out/helper_zip_name).read_bytes()).hexdigest()
combined=base+'\nHELPER_ZIP_NAME = '+repr(helper_zip_name)+'\nHELPER_ZIP_SHA256 = '+repr(helper_zip_hash)+'\n'
combined+='''
# Load the separately attached code ZIP from the same managed folder.
import dataiku
folder = dataiku.Folder('ehA8dpVm')
matches = [p for p in folder.list_paths_in_partition() if PurePosixPath(p).name == HELPER_ZIP_NAME]
if len(matches) != 1:
    raise ValueError('관리 폴더에 R8 코드 ZIP을 정확히 한 개 업로드하세요.')
with folder.get_download_stream(matches[0]) as stream:
    helper_raw = stream.read(1024*1024+1)
if len(helper_raw)>1024*1024 or hashlib.sha256(helper_raw).hexdigest()!=HELPER_ZIP_SHA256:
    raise ValueError('R8_HELPER_ZIP_HASH')
helper_root = Path(tempfile.gettempdir())/('gold-vector-mesh-'+HELPER_ZIP_SHA256[:16])
helper_root.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(helper_raw)) as archive:
    expected_names = {'progress_display.py','mesh_embedding.py','vector_stage.py','error_diagnostics.py','diagnostic_runner.py','reset_source.py','jdbc_transport.py','MANIFEST.json'}
    if set(archive.namelist())!=expected_names or len(archive.namelist())!=len(expected_names):
        raise ValueError('R8_HELPER_ARCHIVE_NAMES')
    manifest = json.loads(archive.read('MANIFEST.json'))
    if set(manifest)!=expected_names-{'MANIFEST.json'}:
        raise ValueError('R8_HELPER_MANIFEST_NAMES')
    for name, expected in manifest.items():
        content = archive.read(name)
        if hashlib.sha256(content).hexdigest()!=expected:
            raise ValueError('R8_HELPER_FILE_HASH')
        path = helper_root/name
        if path.exists() and path.read_bytes()!=content:
            raise ValueError('VECTOR_HELPER_CHANGED')
        if not path.exists():
            with path.open('xb') as stream: stream.write(content)

# Real process environment has priority; Dataiku project variables are also supported.
import importlib.util
spec = importlib.util.spec_from_file_location('gold_mesh_settings_'+HELPER_ZIP_SHA256[:12], helper_root/'mesh_embedding.py')
mesh_settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mesh_settings)
project_values = dataiku.get_custom_variables()
config = mesh_settings.resolve_settings(os.environ, project_values)
embed_environment = {'LEGAL_EMBED_LLM_ID':config['model'], 'LEGAL_EMBED_DIMENSIONS':str(config['dimensions'])}
print('임베딩 설정 확인:', config['model'], '/', config['dimensions'], '차원', flush=True)
sys.path.insert(0, str(helper_root))
from error_diagnostics import banner as error_banner
for ACTION in ('load', 'verify_publish'):
    _run_gold_shape()

package_root = Path(tempfile.gettempdir())/('legal-gold-shape-'+ZIP_SHA256[:16])
old_job = Path(OLD_JOB_DIR) if OLD_JOB_DIR else Path(tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'
contract_sha = digest(json.loads((package_root/'contract.json').read_text()))
state_path = old_job.parent/('gold-shape-'+contract_sha[:12])/'state.json'
state = read_json(state_path)
if state['status'] != 'SOURCE_QUERY_VERIFIED':
    raise ValueError('SOURCE_QUERY_VERIFIED_REQUIRED')
import selectors
import uuid
log_path = Path.cwd()/'gold-progress-logs'/('vector-'+uuid.uuid4().hex+'.log')
child_env = os.environ.copy()
child_env.update(embed_environment)
child_env['G19_DIAGNOSTIC_FILE'] = str(log_path.with_suffix('.errors.jsonl'))
child_env['PYTHONPATH'] = os.pathsep.join(p for p in sys.path if isinstance(p,str) and p)
child_env['PYTHONDONTWRITEBYTECODE'] = '1'
process = subprocess.Popen([sys.executable, '-u', str(helper_root/'vector_stage.py'), str(package_root), str(old_job)],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=child_env)
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ)
started = time.monotonic()
buffer = b''
try:
    with log_path.open('xb') as log:
        print('벡터 전체 로그:', log_path, flush=True)
        while True:
            if time.time() >= state['deadline']:
                raise TimeoutError('원래 작업 기한 종료; 모델 결과 불명은 자동 재전송하지 않습니다.')
            events = selector.select(timeout=min(15, max(0.1, state['deadline']-time.time())))
            if not events:
                print('벡터 작업 진행 중 | 경과 '+duration(time.monotonic()-started)+' | 현재 요청 응답 대기', flush=True)
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            log.write(chunk); log.flush()
            buffer += chunk
            while b'\\n' in buffer:
                line, buffer = buffer.split(b'\\n', 1)
                print(line.decode('utf-8', errors='replace'), flush=True)
        if buffer:
            print(buffer.decode('utf-8', errors='replace'), flush=True)
        result = process.wait()
        if result:
            raise RuntimeError('벡터 단계 중단. 원문·검색 적재는 보존됩니다. 로그: '+str(log_path))
finally:
    selector.close()
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=10)
print('원문·검색 검증 및 개발계 벡터 저장 완료. 서비스 검색 전환은 별도입니다.')
'''
compile(combined,'DATAIKU_GOLD_RESTART_R8.txt','exec')
(out/'DATAIKU_GOLD_RESTART_R8.txt').write_text(combined)
(out/'00_SET_EMBED_ENV.txt').write_text('''# 선택 사항: Dataiku 환경변수/프로젝트변수로 이미 넣었다면 이 셀은 실행하지 않습니다.
import os
os.environ['LEGAL_EMBED_LLM_ID'] = 'openai:genos-embedding:embedding-kure-v1'
os.environ['LEGAL_EMBED_DIMENSIONS'] = '1024'
# Dataiku에 등록된 인증을 사용합니다. URL/API 키는 이 셀에 넣지 않습니다.
# 모델 ID는 등록 모델 별칭입니다. 같은 별칭의 실제 모델을 교체한 경우 기존 벡터 작업을 이어 쓰지 마세요.
''')
print('generated combined load -> verify -> Mesh vector cell and environment setup')
