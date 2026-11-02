# Dataiku LEGAL_RAG Python/Jupyter: _1 새 표 전체 적재 + 검증 + 벡터
# 관리 폴더 ehA8dpVm에 이번 ZIP을 이름 그대로 업로드한 뒤 전체 코드를 실행합니다.
OLD_JOB_DIR = ''  # 기존 원본 준비 폴더. 이전에 직접 지정했으면 같은 값을 사용.
ZIP_NAME = '__ZIP_NAME__'
ZIP_SHA256 = '__ZIP_SHA256__'

import codecs
import collections
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import selectors
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
import dataiku

folder=dataiku.Folder('ehA8dpVm')
matches=[p for p in folder.list_paths_in_partition() if PurePosixPath(p).name==ZIP_NAME]
if len(matches)!=1:raise ValueError('관리 폴더 ehA8dpVm에 이번 _1 ZIP을 정확히 한 개 올리세요.')
with folder.get_download_stream(matches[0]) as stream:raw=stream.read(16*1024**2+1)
if len(raw)>16*1024**2 or hashlib.sha256(raw).hexdigest()!=ZIP_SHA256:raise ValueError('ZIP_HASH_MISMATCH')
package=Path(tempfile.gettempdir())/('legal-gold-fresh-1-'+ZIP_SHA256[:16])
package.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    names=archive.namelist()
    if len(names)!=len(set(names)) or sum(i.file_size for i in archive.infolist())>32*1024**2:raise ValueError('ZIP_CONTENTS')
    manifest=json.loads(archive.read('CODE_MANIFEST.json'))
    if set(names)!=set(manifest['files'])|{'CODE_MANIFEST.json'}:raise ValueError('ZIP_MANIFEST')
    for item in archive.infolist():
        name=PurePosixPath(item.filename)
        if name.is_absolute() or '..' in name.parts or item.is_dir() or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('ZIP_PATH')
        path=package.joinpath(*name.parts)
        if package.resolve() not in path.resolve().parents:raise ValueError('ZIP_ESCAPE')
        content=archive.read(item)
        if item.filename!='CODE_MANIFEST.json' and hashlib.sha256(content).hexdigest()!=manifest['files'][item.filename]:raise ValueError('FILE_HASH')
        if path.exists():
            if path.read_bytes()!=content:raise ValueError('EXTRACTED_CODE_CHANGED')
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(content)

def module(name):
    spec=importlib.util.spec_from_file_location('_fresh_1_'+name+'_'+ZIP_SHA256[:12],package/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value

display_module=module('progress_display')
diagnostics=module('error_diagnostics')
config=module('mesh_embedding').resolve_settings(os.environ,dataiku.get_custom_variables())
old_job=Path(OLD_JOB_DIR) if OLD_JOB_DIR else Path(tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'
contract=json.loads((package/'contract.json').read_text())
contract_sha=display_module.digest(contract)
print('새 대상:',', '.join(t['owner']+'.'+t['name'] for t in contract['tables'].values()),flush=True)
print('새 진행 기록:',old_job.parent/('gold-shape-'+contract_sha[:12]),flush=True)
print('임베딩:',config['model'],config['dimensions'],'차원',flush=True)
log_dir=Path.cwd()/'gold-progress-logs';log_dir.mkdir(exist_ok=True)

def run_stage(action):
    env=os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE']='1'
    env['PYTHONPATH']=os.pathsep.join(p for p in sys.path if isinstance(p,str) and p)
    env['LEGAL_EMBED_LLM_ID']=config['model'];env['LEGAL_EMBED_DIMENSIONS']=str(config['dimensions'])
    env['G19_OLD_JOB_DIR']=str(old_job)
    env.pop('G19_RETRY_MISSING',None)
    log_path=log_dir/(time.strftime('%Y%m%d-%H%M%S')+'-fresh1-'+action+'-'+uuid.uuid4().hex[:8]+'.log')
    env['G19_DIAGNOSTIC_FILE']=str(log_path.with_suffix('.errors.jsonl'))
    view=display_module.Display(old_job,contract_sha,action)
    recent=collections.OrderedDict();errors=[];started=time.monotonic();last_shown=0
    from IPython.display import clear_output
    def redraw(force=False):
        nonlocal last_shown
        now=time.monotonic()
        if not force and now-last_shown<1:return
        last_shown=now
        if not errors:clear_output(wait=True)
        print('[새 _1 표] 단계:',action,'| 이번 단계 경과:',display_module.duration(now-started))
        if action!='vector':print(view.render())
        print('전체 로그:',log_path)
        print('\n'.join(recent.values()),flush=True)
    def consume(line,log):
        log.write(line+'\n');log.flush()
        if not line.strip():return
        try:value=json.loads(line)
        except ValueError:
            key=('text',line);text=line
        else:
            view.observe(value)
            if value.get('phase')=='DIAGNOSTIC_ERROR':
                errors.append(value);print(diagnostics.banner(value),flush=True)
            key=(value.get('phase'),value.get('table'),value.get('asset'))
            text=' | '.join(str(v) if k=='phase' else k+'='+str(v) for k,v in value.items())
        recent[key]=text;recent.move_to_end(key)
        while len(recent)>18:recent.popitem(last=False)
        redraw(bool(errors))
    process=subprocess.Popen([sys.executable,'-u',str(package/'pipeline_entry.py'),action],
                             cwd=str(package),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    decoder=codecs.getincrementaldecoder('utf-8')();pending=''
    try:
        with log_path.open('x',encoding='utf-8') as log:
            while True:
                events=selector.select(timeout=15)
                if not events:redraw(True);continue
                chunk=os.read(process.stdout.fileno(),65536)
                if not chunk:
                    pending+=decoder.decode(b'',final=True)
                    if pending:consume(pending,log)
                    break
                pending+=decoder.decode(chunk)
                while '\n' in pending:
                    line,pending=pending.split('\n',1);consume(line,log)
            code=process.wait();log.write('PROCESS_EXIT='+str(code)+'\n');log.flush()
        redraw(True)
        if code:
            raise RuntimeError(('\n'.join(diagnostics.banner(e) for e in errors) or '실행 중단: 위 오류를 확인하세요.')+'\n로그: '+str(log_path))
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
        process.stdout.close()

for action in ('load','verify_publish','vector'):
    run_stage(action)
print('_1 새 표 원문·검색 적재와 검증, 개발계 벡터 저장 완료. 서비스 조회 전환은 별도입니다.',flush=True)
