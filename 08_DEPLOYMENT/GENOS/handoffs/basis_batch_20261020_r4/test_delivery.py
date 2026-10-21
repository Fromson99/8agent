"""Extracted ZIP/TXT -> actual service -> JSON plan/report; no model invocation."""
from pathlib import Path
import gzip
import hashlib
import json
import os
import subprocess
import zipfile

from test_risk_team_compare_workflow import generation

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
NAME='GENOS_BASIS_BATCH_20261020_R4'


def test_actual_r4_delivery_and_json_plan(tmp_path,generation):
    from lawrag.pipeline.fulltext_stage import derive
    from lawrag.pipeline.search_selection import plan,activate
    selected=tmp_path/'selected-generation'
    derive(generation,selected,workers=1)
    activate(plan(selected,latest=True))
    transfer=tmp_path/'actual-transfer';transfer.mkdir()
    checkout=tmp_path/'physical-checkout';checkout.mkdir()
    task_home=tmp_path/'test-home';task_home.mkdir()
    (task_home/'DEV').symlink_to(checkout,target_is_directory=True)
    with zipfile.ZipFile(ROOT/'08_DEPLOYMENT/GENOS/handoffs/main92_cumulative_20261020_r1/code.zip') as archive:
        archive.extractall(checkout)
    runtime=tmp_path/'runtime'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    config={'schema_version':'genos-serving-paths-v1','selection':'operator-fixed',
            'generation':str(selected),'runtime':str(runtime),
            'generation_manifest_sha256':sha(selected/'manifest.json')}
    config_path=checkout/'00_SYSTEM/GENOS_SERVING_PATHS.json'
    config_path.write_text(json.dumps(config))
    config_before=config_path.read_bytes()
    data_before={str(p.relative_to(selected)):sha(p) for p in selected.rglob('*') if p.is_file()}
    env={k:v for k,v in os.environ.items() if not k.startswith((
        'GENOS_','SEMANTIC_','LEGAL_AGENT_','PYTHON','LAWRAG_',
        'SOURCE_PROVIDER_','WORKFLOW_','TASK_TEST_'))}
    env.update(HOME=str(task_home),PATH=str(ROOT/'.venv/bin')+os.pathsep+os.environ['PATH'],
               PYTHONDONTWRITEBYTECODE='1',DP='oracle',
               GENOS_RAG_IMPLEMENTATION='"retired-implementation-v0"')
    trace=[]

    def command(args,expected=0):
        result=subprocess.run([str(a) for a in args],cwd=transfer,env=env,
                              capture_output=True,text=True,timeout=60)
        output=result.stdout+result.stderr
        trace.append({'args':[str(a) for a in args],'exit':result.returncode,
                      'expected':expected,'output':output})
        with gzip.open(HERE/'DELIVERY_TRACE.json.gz','wt') as stream:
            json.dump(trace,stream,ensure_ascii=False)
        assert (result.returncode==0)==(expected==0),output[-14000:]
        return output

    command(['git','init','-q',checkout])
    old_name='GENOS_BASIS_BATCH_20261020_R3'
    old=transfer/old_name
    command(['python3','-m','zipfile','-e',
             HERE.with_name('basis_batch_20261020_r3')/(old_name+'.zip'),old])
    command(['bash',old/(old_name+'_RUN.txt'),'apply'])
    old_spec=json.loads((old/'PACKAGE.json').read_text())
    old_code={n:sha(checkout/n) for n in old_spec['code']}
    assert old_code==old_spec['code']
    package=transfer/NAME
    command(['python3','-m','zipfile','-e',HERE/(NAME+'.zip'),package])
    script=package/(NAME+'_RUN.txt')
    for action in ('check','apply','gate','apply'):
        command(['bash',script,action])
    spec=json.loads((package/'PACKAGE.json').read_text())
    assert all(sha(checkout/n)==h for n,h in spec['code'].items())
    receipt=(package/'INSTALL_STATE.json').read_bytes()
    listing=command(['bash',script,'list'])
    assert '"implementation": "legal-agent-unified-v6"' in listing
    assert 'basis.batch.latest_internal' in listing
    command(['bash',script,'plan','--count','3'])
    job=runtime/'basis-batch/pilot-review-skip-20261020-r4'
    saved=(job/'PLAN.json').read_bytes();value=json.loads(saved)
    assert value['candidate_storage']['kind']=='json-candidates-v1'
    assert value['candidate_storage']['publication']=='manual-review-only'
    assert value['binding']['generation_path']==str(selected)
    assert [d['document_id'] for d in value['documents']]==['inside']
    assert value['batch_id'] in command(['bash',script,'status'])
    command(['bash',script,'plan'],expected=1)
    assert (job/'PLAN.json').read_bytes()==saved
    for action in ('run','resume'):
        failure=command(['bash',script,action],expected=1)
        assert '내부 모델' in failure
    assert not (job/'STATE.json').exists()
    assert not (job/'CANDIDATES.json').exists()
    command(['bash',script,'report','--output','./후보검토.html'])
    html=(transfer/'후보검토.html').read_text()
    assert '<html' in html and '별도 JSON 후보이며 관계 SQLite에는 아직 적용하지 않았습니다.' in html
    # No candidates may be packaged as an approved relationship transfer.
    command(['bash',script,'export','--output','./empty-export'],expected=1)
    original=(checkout/'02_BACKEND/lawrag/pipeline/basis_batch.py').read_bytes()
    (checkout/'02_BACKEND/lawrag/pipeline/basis_batch.py').write_bytes(original+b'\n# unexpected change\n')
    assert 'Unknown code' in command(['bash',script,'gate'],expected=1)
    (checkout/'02_BACKEND/lawrag/pipeline/basis_batch.py').write_bytes(original)
    tool=package/'tools/basis_batch_candidates.py';tool_original=tool.read_bytes()
    tool.write_bytes(tool_original+b'\n# unexpected change\n')
    assert 'Package file changed' in command(['bash',script,'report'],expected=1)
    tool.write_bytes(tool_original)
    command(['bash',script,'rollback'])
    assert {n:sha(checkout/n) for n in old_code}==old_code
    assert (job/'PLAN.json').read_bytes()==saved
    assert not (runtime/'basis-links/SQLITE_ENABLED.json').exists()
    assert not (runtime/'basis-links/authority.sqlite').exists()
    assert config_path.read_bytes()==config_before
    assert data_before=={str(p.relative_to(selected)):sha(p) for p in selected.rglob('*') if p.is_file()}
    assert receipt
    assert env['DP']=='oracle' and env['GENOS_RAG_IMPLEMENTATION']=='"retired-implementation-v0"'
    logs=list((transfer/'basis-batch-r4-logs').glob('*.log.exit'))
    shell_calls=sum(r['args'][:2]==['bash',str(script)] for r in trace)
    assert len(logs)==shell_calls and {'0','1'}<={p.read_text().strip() for p in logs}
    record={'status':'PASS','zip_sha256':sha(HERE/(NAME+'.zip')),'commands':len(trace),
            'intentional_failures':sum(r['expected']!=0 for r in trace),
            'app_injection':False,'synthetic_source_generation':True,
            'real_shell_and_service_boot':True,'json_candidate_plan':True,
            'html_report_from_json_plan':True,'source_and_sqlite_unchanged':True,
            'existing_plan_preserved':True,'idempotent_install_and_exact_R3_rollback':True,
            'package_and_code_tamper_rejected':True,'unconfigured_model_rejected':True,
            'external_model_calls':0,'GENOS_model_calls':0}
    (HERE/'FINAL_VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n')
