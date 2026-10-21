"""HTML review -> the same shared SQLite authority, without export archives.

Existing fixed staging, source validation, review, SQL application and rollback
remain their respective owners. This module only freezes the local review input.
"""
import fcntl
import getpass
import os
from pathlib import Path

from lawrag.pipeline import basis_batch_artifacts as art
from semantic_runtime.basis_links.contracts import digest, require


def prepare(root, job, generation, runtime, config):
    from lawrag.pipeline import basis_batch as batch, basis_batch_candidates as candidates
    from lawrag.pipeline import risk_basis_seed as fixed, risk_basis_staging as staging
    job = art.plain(job)
    # The existing batch planner owns source/structure/identity checks. This is
    # a fixed-document JSON plan only; no stage-run or model call is made.
    os.environ['GENOS_RAG_IMPLEMENTATION'] = config[1]['implementation']
    with batch.lock(job):
        if not (job/'PLAN.json').exists():
            batch.resources(job)
            with batch.heartbeat({'phase':'fixed-plan'}):
                app = batch.boot(root)
                try:
                    selected = fixed.resolve(app.state.pipeline.store, {
                        'user_id':getpass.getuser(),'team_id':'risk_team','document_ids':[],'basis_review':True})
                    value, _ = batch.plan(app,'risk_team',ids=[selected['internal_document_id']])
                    value['candidate_storage'] = {'kind':'json-candidates-v1','path':str(job/'CANDIDATES.json'),
                        'tool':candidates.tool_binding(),'publication':'manual-review-only'}
                    value['plan_sha256'] = digest({k:v for k,v in value.items() if k!='plan_sha256'})
                    art.atomic(job/'PLAN.json',value)
                finally:
                    app.state.pipeline.store.close()
        return staging.stage(job,generation,runtime,getpass.getuser(),config=config)


def fixed_snapshot(job, generation, runtime, config):
    from lawrag.pipeline.basis_batch_candidates import JsonRepository
    value = art.capture(job, generation, runtime, config)
    repo = JsonRepository(job/'CANDIDATES.json')
    selected = {}
    for path in sorted(job.glob('RISK_FIXED_*.json')):
        receipt = art.read_json(path)
        if receipt.get('plan_sha256') != value['plan_sha256']:
            continue
        saved = repo.receipt('risk-fixed:'+receipt['operation_id'],receipt['operation_id'])
        require(saved and {**receipt,'status':'STAGED'} == saved, 'LOCAL_FIXED_RECEIPT',
                '확정 연결 기록이 후보 원장과 다릅니다.', 409)
        for row in receipt['actions']:
            previous = selected.get(row['link_id'])
            require(previous is None or previous == row['head_hash'], 'LOCAL_FIXED_CONFLICT',
                    '확정 연결의 저장 기록이 서로 다릅니다.', 409)
            selected[row['link_id']] = row['head_hash']
    require(len(selected) == 4, 'LOCAL_FIXED_MISSING', '먼저 같은 작업에 fixed-stage로 지정 4건을 추가하세요.')
    value['items'] = [i for i in value['items'] if i['link']['link_id'] in selected]
    require(len(value['items']) == 4 and all(i['link']['status'] == 'APPROVED' and
            digest(i['link']) == selected[i['link']['link_id']] for i in value['items']),
            'LOCAL_FIXED_CHANGED', '확정 연결이 변경되었거나 4건 모두 확인되지 않았습니다.', 409)
    dids = {e['document_id'] for i in value['items'] for group in ('revisions','bindings')
            for row in i['history'][group] for side in ('internal','external') for e in row[side]}
    value['lineage'] = [v for v in value['lineage'] if v['version_id'] in dids]
    value['document_hashes'] = {k:v for k,v in value['document_hashes'].items() if k in dids}
    value['documents'] = [d for d in value['documents'] if d['document_id'] in dids]
    value['snapshot_sha256'] = digest({k:v for k,v in value.items() if k!='snapshot_sha256'})
    return value


def binding(value):
    # Unrelated model progress may continue; selected heads/history/source may not change.
    return {k:value[k] for k in ('plan_sha256','source','principal','items','lineage','document_hashes')}


def run(action, job, output, generation, runtime, config, *, local_validation=False, hook=None):
    job, output = art.plain(job), art.plain(output)
    generation, runtime = art.plain(generation), art.plain(runtime)
    require(action in ('report','check','apply','status','rollback'), 'LOCAL_ACTION', '알 수 없는 명령입니다.')
    require(job.is_dir(), 'LOCAL_JOB', '먼저 같은 작업에 plan과 fixed-stage를 실행하세요.')
    require(not any(output.is_relative_to(p) for p in (job,generation,runtime)),
            'LOCAL_OUTPUT', 'HTML 폴더는 원문·runtime 밖의 TRANSFER에 두세요.')
    context = {'schema_version':'basis-local-fixed-v1', 'job':str(job),
               'generation':str(generation), 'runtime':str(runtime)}
    if action in ('apply','rollback'):
        require(local_validation or art.network_storage(runtime), 'TRANSFER_RUNTIME',
                '기존 GENOS 외부 공유 runtime이 필요합니다.')
    # Same lock as the JSON candidate writer; no model/research runs inside this lock.
    with art.plain(job/'CANDIDATES.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data = output/'RELATIONS.json'
        if action == 'report':
            current = fixed_snapshot(job,generation,runtime,config)
            if data.exists():
                require(art.read_json(output/'LOCAL_CONTEXT.json') == context,
                        'LOCAL_CONTEXT', '다른 작업의 HTML 폴더입니다.', 409)
                value = art.signed(art.read_json(data),'snapshot_sha256')
                require(binding(value) == binding(current), 'LOCAL_REVIEW_STALE',
                        '기존 HTML과 확정 연결이 다릅니다. 새 --output 폴더를 사용하세요.', 409)
            else:
                output.mkdir(parents=True,exist_ok=True)
                leftovers = {p.name for p in output.iterdir()}
                require(not leftovers or (leftovers == {'LOCAL_CONTEXT.json'} and
                        art.read_json(output/'LOCAL_CONTEXT.json') == context),
                        'LOCAL_OUTPUT_EXISTS', '빈 HTML 폴더를 지정하세요.')
                art.atomic(output/'LOCAL_CONTEXT.json',context)
                art.atomic(data,current)
                value=current
            art.report(value,output/'LINKS.html')
            art.atomic(output/'HTML.json', {'snapshot_sha256':value['snapshot_sha256'],
                       'html_sha256':art.hashlib.sha256((output/'LINKS.html').read_bytes()).hexdigest()})
            return {'status':'HTML_READY','html':str(output/'LINKS.html'),'links':4,'published_to_sqlite':False}
        require(data.is_file() and art.read_json(output/'LOCAL_CONTEXT.json') == context,
                'LOCAL_REVIEW_REQUIRED', '먼저 local-report로 HTML을 생성하고 확인하세요.')
        value = art.signed(art.read_json(data),'snapshot_sha256')
        if action in ('check','apply'):
            html = art.read_json(output/'HTML.json')
            require(html == {'snapshot_sha256':value['snapshot_sha256'],
                    'html_sha256':art.hashlib.sha256((output/'LINKS.html').read_bytes()).hexdigest()},
                    'LOCAL_HTML_CHANGED', '확인할 HTML이 변경되었습니다.', 409)
            require(binding(value) == binding(fixed_snapshot(job,generation,runtime,config)),
                    'LOCAL_REVIEW_STALE', 'HTML 생성 후 확정 연결이 변경되었습니다.', 409)
            if action=='check':
                # A check does not record the operator's import decision.
                with art.source(generation,value['source'],value['principal'],config) as (sources,who):
                    art.validate(value,sources,who)
                return {'status':'SOURCE_READY','links':len(value['items']),'published_to_sqlite':False}
            decision = art.review(value,output/'REVIEW.json',accept_all=True)
            reviewed = art.reviewed(value,decision)
            art.atomic(output/'REVIEWED.sql',art.sql(reviewed))
            result = art.apply(reviewed,art.sql(reviewed),generation,runtime,config=config,hook=hook)
        else:
            if action=='status' and not (output/'REVIEW.json').exists():
                return {'status':'not_applied','html':str(output/'LINKS.html')}
            reviewed = art.load_reviewed(data,value)
            result = (art.status(reviewed,runtime) if action=='status' else art.rollback(reviewed,runtime,hook=hook))
        art.atomic(output/('LOCAL_'+action.upper()+'.json'),result)
        return result
