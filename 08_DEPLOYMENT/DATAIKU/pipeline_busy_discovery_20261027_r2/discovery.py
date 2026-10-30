"""Find prior batch capabilities in this project's checkpoints; never release work."""
import hashlib
import json
import math
from pathlib import Path
import re
import time

MAX_FOLDERS = 50
MAX_JOBS = 100
MAX_STATUSES = 40


def discover(d, dataiku, local_roots=()):
    if dataiku.default_project_key() != d.PROJECT:
        raise d.InspectionError('LEGAL_RAG_PROJECT_REQUIRED')
    remote = d.StatusClient(dataiku.get_custom_variables())
    health = remote.call('HEALTH')
    if health.get('code_sha256') != d.SERVICE_SHA:
        raise d.InspectionError('DEPLOYED_CODE_MISMATCH')
    if not re.fullmatch('[0-9a-f]{32}',str(health.get('instance',''))):
        raise d.InspectionError('HEALTH_CONTRACT')
    project = dataiku.api_client().get_project(d.PROJECT)
    known = project.list_managed_folders()
    if len(known) > MAX_FOLDERS:
        raise d.InspectionError('FOLDER_LIMIT')
    ids = [v['id'] for v in known]
    if len(ids) != len(set(ids)) or any(not isinstance(i,str) or not i for i in ids):
        raise d.InspectionError('FOLDER_IDS')
    rows, cache, contracts, counters = [], {}, {}, {'checkpoints':0,'folders':0,'local_clients':0}
    scan_deadline = time.monotonic()+120

    def emit(row):
        rows.append(row)
        print('DISCOVER_JOB',json.dumps(row,ensure_ascii=False,sort_keys=True),flush=True)

    def status(row, state, deadline=None):
        if (not re.fullmatch('[0-9a-f]{32}',str(state.get('job_id','')))
                or not re.fullmatch('[0-9a-f]{64}',str(state.get('job_token','')))
                or state.get('code_sha256') != d.SERVICE_SHA):
            raise d.InspectionError('CLIENT_AUTH_BINDING')
        row['job_id'] = state['job_id']
        row['saved_status'] = state.get('status') if state.get('status') in d.STATUSES else 'UNKNOWN'
        if deadline is not None and (type(deadline) not in (int,float) or not math.isfinite(deadline)
                                     or state.get('deadline') != deadline):
            raise d.InspectionError('CLIENT_DEADLINE_BINDING')
        if state.get('instance') != health['instance']:
            row['status'] = 'INSTANCE_CHANGED_NO_CALL'
            return row
        auth = {k:state[k] for k in ('job_id','job_token','instance','code_sha256')}
        key = hashlib.sha256(json.dumps(auth,sort_keys=True).encode()).hexdigest()
        contract = (state.get('archives'),state.get('deadline'))
        if key in contracts and contracts[key] != contract:
            raise d.InspectionError('DUPLICATE_CLIENT_BINDING')
        contracts[key] = contract
        if key not in cache:
            if len(cache) >= MAX_STATUSES:
                raise d.InspectionError('STATUS_LIMIT')
            try:
                reply = remote.call('STATUS',**auth)
                if any(reply.get(k) != auth[k] for k in ('job_id','instance','code_sha256')):
                    raise d.InspectionError('STATUS_BINDING')
                if reply.get('status') not in {'UPLOADING','RUNNING','COMPLETE','FAILED','CANCELLED','INTERRUPTED','RELEASED'}:
                    raise d.InspectionError('STATUS_CONTRACT')
                # A known client also binds the server's exact input declarations.
                if state.get('archives') and reply.get('archives') != state['archives']:
                    raise d.InspectionError('STATUS_ARCHIVES_BINDING')
                if state.get('deadline') is not None and reply.get('deadline') != state['deadline']:
                    raise d.InspectionError('STATUS_DEADLINE_BINDING')
                phase = reply.get('phase')
                cache[key] = {'status':reply['status'], 'blocks_new_start':reply['status']!='RELEASED',
                    'phase':phase if phase in {'VERIFY_INPUTS','STRUCTURE','PREPARE','INDEX','QUERY','PACKAGE','RETURN','RETURN_READY'} else 'UNSPECIFIED'}
                if reply.get('error'):
                    cache[key]['error_code'] = d.error_code(reply['error'])
            except d.InspectionError as exc:
                cache[key] = {'status':'STATUS_UNCONFIRMED','error_code':str(exc)}
        row.update(cache[key])
        return row

    for item in known:
        if counters['checkpoints'] >= MAX_JOBS:
            emit({'source':'managed','status':'TOTAL_CHECKPOINT_LIMIT_REACHED'});break
        if time.monotonic() >= scan_deadline:
            emit({'source':'managed','status':'SCAN_BUDGET_REACHED'})
            break
        fid = item['id']; counters['folders'] += 1
        found = 0
        try:
            folder = dataiku.Folder(fid,project_key=d.PROJECT)
            # Existing hash-verified, bounded latest-checkpoint reader. Only
            # _pipeline/jobs/*/checkpoint-...json contents are opened.
            for name, checkpoint in d.latest_checkpoints(folder):
                found += 1; counters['checkpoints'] += 1
                if counters['checkpoints'] > MAX_JOBS:
                    raise d.InspectionError('TOTAL_CHECKPOINT_LIMIT')
                row={'source':'managed','folder_id':fid,'job_name':name,
                     'local_phase':checkpoint.get('phase') if checkpoint.get('phase') in d.STATUSES else 'UNKNOWN'}
                binding=checkpoint.get('binding',{});inputs=binding.get('input',{})
                legacy=(inputs.get('project')==d.PROJECT and inputs.get('folder_id')==fid
                        and inputs.get('client_sha256') in d.CLIENT_SHAS)
                recipe=(binding.get('version')=='recipes-20261027-r1'
                        and inputs.get('landing') in ids and inputs.get('raw') in ids)
                if (not (legacy or recipe) or binding.get('service_code')!=d.SERVICE_SHA
                        or binding.get('service_url_sha256')!=remote.endpoint_sha):
                    row['status']='SKIPPED_BINDING'
                elif not checkpoint.get('client'):
                    row['status']='NO_CLIENT_STATE'
                else:
                    row=status(row,checkpoint['client'],checkpoint.get('deadline'))
                emit(row)
            print('DISCOVER_FOLDER',fid,'checkpoints=',found,flush=True)
        except d.InspectionError as exc:
            emit({'source':'managed','folder_id':fid,'status':'CHECKPOINT_UNCONFIRMED','error_code':str(exc)})
        except Exception as exc:
            emit({'source':'managed','folder_id':fid,'status':'FOLDER_UNCONFIRMED','error_type':type(exc).__name__})

    # Only the earlier runner's explicitly known work directories, not a home or
    # filesystem search. These local files lack checkpoint filename signatures;
    # project/input support binding + current server instance/auth are required.
    checked_roots=set()
    for candidate in local_roots:
        root=Path(candidate).expanduser().absolute()
        if str(root) in checked_roots:
            continue
        checked_roots.add(str(root))
        if len(checked_roots)>2:
            raise d.InspectionError('LOCAL_ROOT_LIMIT')
        if time.monotonic()>=scan_deadline:
            emit({'source':'local','status':'SCAN_BUDGET_REACHED'});break
        row={'source':'local','work_dir':str(root)}
        try:
            if any(p.is_symlink() for p in (root,*root.parents)):
                raise d.InspectionError('LOCAL_SYMLINK')
            if not root.exists():
                emit({**row,'status':'LOCAL_WORK_DIR_NOT_FOUND'});continue
            marker=root/'input-binding.json'
            if marker.is_symlink() or not marker.is_file():
                raise d.InspectionError('LOCAL_INPUT_BINDING_REQUIRED')
            with marker.open('rb') as stream:inputs=json.loads(d.read_small(stream))
            if (inputs.get('project')!=d.PROJECT or inputs.get('client_sha256') not in d.CLIENT_SHAS
                    or not isinstance(inputs.get('folder_id'),str) or not inputs['folder_id']):
                raise d.InspectionError('LOCAL_PROJECT_BINDING')
            jobs=root/'jobs'
            if jobs.is_symlink() or not jobs.is_dir():
                raise d.InspectionError('LOCAL_JOBS_DIRECTORY')
            count=0
            for index,job in enumerate(jobs.iterdir()):
                if index>=100 or count>=20:
                    raise d.InspectionError('LOCAL_JOB_LIMIT')
                if not job.is_dir() or not re.fullmatch('[A-Za-z0-9_-]{1,80}',job.name):
                    continue
                if job.is_symlink():raise d.InspectionError('LOCAL_SYMLINK')
                path=job/'client.json'
                if not path.exists():continue
                if path.is_symlink():raise d.InspectionError('LOCAL_SYMLINK')
                with path.open('rb') as stream:raw=d.read_small(stream)
                state=json.loads(raw);count+=1;counters['local_clients']+=1
                if (state.get('archives',{}).get('support') != inputs.get('archives',{}).get('PIPELINE_SUPPORT.zip')
                        or not state.get('archives',{}).get('support')):
                    raise d.InspectionError('LOCAL_SUPPORT_BINDING')
                emit(status({**row,'job_name':job.name,'local_client_sha256':hashlib.sha256(raw).hexdigest(),
                             'local_binding':'project/support/code/current-instance; no signed checkpoint'},state))
            print('DISCOVER_LOCAL',str(root),'clients=',count,flush=True)
        except d.InspectionError as exc:
            emit({**row,'status':'LOCAL_UNCONFIRMED','error_code':str(exc)})
        except Exception as exc:
            emit({**row,'status':'LOCAL_UNCONFIRMED','error_type':type(exc).__name__})
    blockers=sorted({row['job_id'] for row in rows if row.get('blocks_new_start')})
    summary={'inspection':'FINISHED','blocking_job_ids':blockers,'counts':counters,
             'http_calls':remote.calls,'scope':'this project managed folders and explicitly known old notebook work dirs',
             'note':'빈 목록/조회 실패는 서버에 다른 작업이 없다는 증명이 아닙니다.'}
    print('DISCOVER_SUMMARY',json.dumps(summary,ensure_ascii=False,sort_keys=True),flush=True)
    print('원문/ZIP 다운로드·START·UPLOAD·EXECUTE·CANCEL·ACK·SQL·S3 쓰기 없음. STATUS는 유실 실행 상태를 갱신할 수 있습니다.',flush=True)
    return rows,summary
