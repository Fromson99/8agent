"""Bind the tested action contract to a fresh nine-cell run before any call."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited'
ART = ADR/'artifacts'
PRIOR = ROOT/'04_EXPERIMENTS/ADR/ADR-1065-ontology-task-local-navigation'
SOURCE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1066/input-unlimited-r1'
CODE = SOURCE/'revisions/rev-002/snapshot'
HERE = Path(__file__).parent

def read(p): return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
def rel(p): return str(p.relative_to(ROOT))
def save(p, value): p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def exact(p, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    if p.exists(): assert p.read_text()==raw, 'immutable input changed: '+str(p)
    else: p.write_text(raw)

def prepare():
    assert not (ART/'design-freeze.json').exists() and not (ART/'matrix').exists()
    m = read(ADR/'실험/manifest.json')
    assert m['reservation']['status']=='in_progress' and m['results']['status']=='not_run'
    prior = read(PRIOR/'실험/manifest.json')
    assert prior['results']['status']=='complete'
    tested = read(ART/'action-frozen-final-summary.json')
    files = {relpath:sha(CODE/relpath) for relpath in tested['files']}
    assert files==tested['files'] and len(files)==743
    assert tested['passed']==80 and tested['validation_status']==0
    assert not tested['production_import_leaks'] and not tested['candidate_changed_during_tests']
    plan = deepcopy(read(PRIOR/'artifacts/implementation-plan.json'))
    plan.update(schema_version='action-choice-live-plan-v1', parent='ADR-1065-experiment-v1/A2',
        source_candidate=rel(CODE), candidate_id='action-choice-a2-r1',
        hypothesis='입력 문자 차단 해제와 행동별 최소 응답·확정값 서버 조립을 결합하면 필수 필드 누락으로 조사를 막던 문제가 줄고, 실제 원문 읽기·승인 묶음 전달·판단 후 행동·답변 발행까지 이어진다.',
        success_criteria='9셀 모두 애플리케이션 입력 문자 차단·필수 행동 필드 누락에 의한 종료·코드/권한/해시/상태 오류 없이 원문 실제 전달과 최종 답변 소비를 확인. 운영 완료 수/9가 일차 지표이며 정확도·원문 도달률·온톨로지 도착/취득/전달은 별도 집계한다.',
        failure_criteria='원문 미확보·필수 필드 누락 종료·유효 판단 이후 실행 차단·발행 실패는 운영 실패. 의미 오답만으로 신규 셀을 중단하지 않는다. 전송 수락 불명·자원·권한/해시/상태·예상하지 못한 예외는 즉시 신규 호출 중단. 결과 후 수정/재실행 금지.',
        scope='Exactly the same known three questions and nine cells as completed ADR1065; no additional questions or repetitions. Historical1065 is descriptive, not a concurrent control.',
        user_authorization='실험해봐',
        primary_metric='Published native service answers / 9; original delivery and action-contract failures reported independently',
        interpretation='Combined repair probe: character-cap removal, action contract and confirmed-document binding are not separately ablated. A1/A2 effects only assessable after actual bundle delivery.',
        regression_floor={'focused_contract_passes':80,'new_failures':0,'evidence':rel(ART/'action-frozen-final-summary.json'),
            'rule':'Exact tested743-file map reused; no repeated broad test suite or production runtime edits.'})
    plan['budgets']['input_chars']={key:None for key in plan['budgets']['input_chars']}
    plan['budgets']['enforce_input_character_limits']=False
    plan['model']['provider_exception']['scope']='Isolated ADR1066 nine-cell product and offline judge; previously user-approved same-model FP8 provider advances only after known rejected429.'
    plan['success_dimensions'][0]='Uncapped measured input and required action-field completeness'
    plan['freeze_order']=['criteria','identical tested code registered per arm','freeze all hashes','single sequential live matrix','offline evaluation and immutable report']
    plan['transport_accounting']=plan['transport_accounting'].replace('and its mode budget','and the original wall deadline')
    exact(ART/'live-implementation-plan.json',plan)
    for name in ('cases-product.json','cases-evaluator.json'):
        exact(ART/name,read(PRIOR/'artifacts'/name))
    auth = read(PRIOR/'artifacts/authorization.json')
    auth.update(schema_version='action-choice-live-authorization-v1',experiment_id=m['experiment_id'],
        authorization_record='Current user explicitly requested 실험해봐 after implementation. Existing source/export/provider approvals persist.',
        scope=plan['scope'])
    exact(ART/'live-authorization.json',auth)
    corpus=read(PRIOR/'artifacts/corpus.json')
    corpus['authorization_receipt']={'path':rel(ART/'live-authorization.json'),'sha256':sha(ART/'live-authorization.json')}
    exact(ART/'corpus.json',corpus)
    preserve=[PRIOR/'실험/manifest.json',PRIOR/'artifacts/design-freeze.json',
        SOURCE/'candidate.json',ART/'action-frozen-final-summary.json',ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']
    exact(ART/'live-preservation.json',{'files':{rel(p):sha(p) for p in preserve},'tested_code_files':files})
    if not any(e['action']=='live_scope_authorized' for e in m['reservation']['events']):
        now=datetime.now(timezone.utc).isoformat()
        m['reservation']['events'].append({'action':'live_scope_authorized','at':now,'owner':'codex',
            'session_id':m['reservation']['session_id'],'note':'사용자 실험해봐 요청으로 기존 미실행1066의 3질문×A0/A1/A2 9셀 live 범위를 사전 동결. 구현 기록과 rev001/002 보존.'})
        m['reservation']['updated_at']=now
        text=(ADR/'README.md').read_text()
        import re
        text=re.sub(r'(?m)^updated_at:.*$', 'updated_at: '+now,text)
        (ADR/'README.md').write_text(text)
    m['design']=deepcopy(prior['design'])
    m['design'].update(hypothesis=plan['hypothesis'],primary_metric=plan['primary_metric'],
        success_criteria=plan['success_criteria'],failure_criteria=plan['failure_criteria'],
        budgets=plan['budgets'],criteria_frozen_before_run=True,
        criteria_record={'path':rel(ART/'live-implementation-plan.json'),'sha256':sha(ART/'live-implementation-plan.json'),'frozen_before_model':True})
    m['design']['sampling']['selection']='Known3 exact matched questions from completed1065; no continuation; combined repair probe.'
    for arm in m['design']['arms']:
        arm['derived_from']=['ADR-1065-experiment-v1/A2']
        arm['controls']='동일80검사743파일·3질문·데이터·모델·제공자·40호출/1024도구/1800초. 입력/출력 문자·토큰 상한 없음. 온톨로지 모드만 다름.'
    m['design']['code_isolation']['candidates']=[]
    m['dataset']=deepcopy(prior['dataset'])
    m['dataset'].update(name='Known3 action-choice combined repair probe',version='20261026-action-choice-r1',
        frozen_source=rel(ART/'cases-product.json'),sha256=sha(ART/'cases-product.json'))
    m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['A0','A1','A2'],
        'selection_rule':plan['scope'],'status':'planned','artifact_path':rel(ART/'matrix-summary.json'),'sha256':None}]
    m['llm_policy']=plan['model']
    m['retrieval_accounting']=deepcopy(prior['retrieval_accounting'])
    for key in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):
        m['retrieval_accounting'][key]=None
    m['retrieval_accounting']['stage_ledger'].update(artifact_path=rel(ART/'retrieval-ledger.json'),sha256=None)
    save(ADR/'실험/manifest.json',m)
    sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
    source_manifest=read(SOURCE/'candidate.json')
    for arm in ('A0','A1','A2'):
        name='action-choice-'+arm.lower()+'-r1';directory=SOURCE.parent/name
        assert not directory.exists(), 'arm candidate already exists; inspect rather than overwrite'
        c.snapshot(ADR,name,[r['target_path'] for r in source_manifest['files'] if r['upstream_state']=='present'],
            experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
        for row in source_manifest['files']:
            target=directory/'snapshot'/row['target_path'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(CODE/row['target_path'],target)
            if row['upstream_state']=='absent': c.register_file(directory,row['target_path'],upstream_state='absent')
        c.refresh(directory);c.freeze(directory);assert not c.validate(directory)
        cm=read(directory/'candidate.json');revision=cm['revisions'][-1]
        assert {r['target_path']:r['snapshot_sha256'] for r in cm['files']}==files
        m['design']['code_isolation']['candidates'].append({'candidate_id':name,'arm_id':arm,
            'experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':rel(directory/'candidate.json'),
            'manifest_sha256':sha(directory/'candidate.json'),'revision_id':revision['revision_id'],
            'revision_sha256':revision['revision_sha256'],'runner_path':rel(HERE/'run_matrix.py'),'runner_sha256':None})
    save(ADR/'실험/manifest.json',m)
    exact(ART/'live-tested-binding.json',{'test_summary':rel(ART/'action-frozen-final-summary.json'),
        'sha256':sha(ART/'action-frozen-final-summary.json'),'passed':80,'files':files,'exact_tested_files':True,
        'runtime_changes':0,'external_model_calls':0})
    print('Prepared3×3; 743 identical tested files per arm; no model calls')

def freeze():
    assert not (ART/'design-freeze.json').exists() and not (ART/'matrix').exists()
    old=read(PRIOR/'artifacts/design-freeze.json');f=deepcopy(old)
    m=read(ADR/'실험/manifest.json');plan=read(ART/'live-implementation-plan.json')
    for binding in m['design']['code_isolation']['candidates']:
        binding['runner_sha256']=sha(ROOT/binding['runner_path'])
    save(ADR/'실험/manifest.json',m)
    binding=next(b for b in m['design']['code_isolation']['candidates'] if b['arm_id']=='A2')
    code=(ROOT/binding['manifest_path']).parent/'revisions'/binding['revision_id']/'snapshot'
    files=read(ART/'live-tested-binding.json')['files']
    for arm_binding in m['design']['code_isolation']['candidates']:
        manifest_path=ROOT/arm_binding['manifest_path']
        assert sha(manifest_path)==arm_binding['manifest_sha256']
        candidate=read(manifest_path)
        revision=next(r for r in candidate['revisions'] if r['revision_id']==arm_binding['revision_id'])
        assert revision['revision_sha256']==arm_binding['revision_sha256']
        arm_code=manifest_path.parent/'revisions'/arm_binding['revision_id']/'snapshot'
        assert {str(p.relative_to(arm_code)):sha(p) for p in arm_code.rglob('*') if p.is_file()}==files
    assert files=={str(p.relative_to(code)):sha(p) for p in code.rglob('*') if p.is_file()}
    policy=read(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    assert policy['provider_failover']['scope']==m['experiment_id'] and policy['max_output_tokens'] is None
    source=ROOT/old['data_path']/'store.sqlite';s=source.stat();receipt=read(ROOT/old['source_integrity_path'])
    assert all(getattr(s,'st_'+key)==receipt[key] for key in ('size','mtime_ns','ctime_ns'))
    assert sha(source)==old['store_sha256']
    after=source.stat()
    assert all(getattr(after,'st_'+key)==getattr(s,'st_'+key) for key in ('size','mtime_ns','ctime_ns'))
    for path,h in read(ART/'live-preservation.json')['files'].items():assert sha(ROOT/path)==h
    f.update(frozen_at=datetime.now(timezone.utc).isoformat(),experiment_id=m['experiment_id'],
        manifest_sha256_at_freeze=sha(ADR/'실험/manifest.json'),code_root=rel(code),files=files,
        design=m['design'],execution_order=plan['execution_order'],arm_code_bindings=m['design']['code_isolation']['candidates'],
        policy_sha256=sha(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),provider_failover=policy['provider_failover'],
        mode_limits=plan['budgets']['input_chars'],enforce_input_character_limits=False,minimal_action_choices=True,
        validation_inheritance=True,validation_note='Exact743-file map from80 focused contract/API tests; no runtime change for live arm binding.',
        shared_execution_code='Three identical tested file maps; A2 explicitly imported and only ontology mode varied per cell.',
        prior_design_freeze_path=rel(PRIOR/'artifacts/design-freeze.json'),prior_design_freeze_sha256=sha(PRIOR/'artifacts/design-freeze.json'))
    for key,path in [('product_cases',ART/'cases-product.json'),('evaluator_cases',ART/'cases-evaluator.json'),
        ('corpus',ART/'corpus.json'),('authorization',ART/'live-authorization.json'),
        ('optimization_authorization',ART/'live-implementation-plan.json'),
        ('validation',ART/'action-frozen-final-summary.json'),('validation_receipt',ART/'live-tested-binding.json'),
        ('client',code/'02_BACKEND/lawrag/research/experiment_client.py'),('judge_client',code/'02_BACKEND/lawrag/research/experiment_client.py')]:
        f[key+'_path']=rel(path);f[key+'_sha256']=sha(path)
    for key in ('task_preflight','candidate_diff_path','candidate_diff_sha256','development_parent_candidate_path','development_parent_candidate_sha256'):
        f.pop(key,None)
    f['semantic_contract_files']={p:files[p] for p in old['semantic_contract_files']}
    assert all(files.get(p)==h for p,h in old['unchanged_core_semantic_definitions'].items())
    parent_binding=next(b for b in old['arm_code_bindings'] if b['arm_id']=='A2')
    parent_code=ROOT/old['code_root']
    parent_files=old['files']
    delta={'parent_experiment':'ADR-1065-experiment-v1/A2','parent_code_root':rel(parent_code),
        'parent_revision_sha256':parent_binding['revision_sha256'],'candidate_code_root':rel(code),
        'candidate_revision_sha256':binding['revision_sha256'],
        'files':[{'path':p,'parent_sha256':parent_files.get(p),'candidate_sha256':files.get(p)}
            for p in sorted(set(parent_files)|set(files)) if parent_files.get(p)!=files.get(p)]}
    exact(ART/'live-candidate-diff.json',delta)
    f.update(candidate_diff_path=rel(ART/'live-candidate-diff.json'),candidate_diff_sha256=sha(ART/'live-candidate-diff.json'),
        development_parent_candidate_path=parent_binding['manifest_path'],
        development_parent_candidate_sha256=parent_binding['manifest_sha256'])
    f['input_output_representation'].update(minimal_action_choices=True,enforce_input_character_limits=False,
        action_output_key_aliases=False,action_schema_sharing=False,action_request_local_value_tables=False,
        action_input_projection_v3=False,normal_and_whole_repair_same_contract=True,
        final_request_limit_chars=None,configured_historical_outer_limit_chars=100000,
        required_output_schema='Action-specific required choices; deterministic server assembly; same normal/whole-repair contract')
    f['first_nine_gate'].update(implementation=rel(HERE/'gate.py'),sha256=sha(HERE/'gate.py'))
    f['delivery_audit_contract'].update(code=rel(HERE/'delivery_spans.py'),sha256=sha(HERE/'delivery_spans.py'))
    f['runner_hashes']={rel(p):sha(p) for p in HERE.glob('*.py') if p.name!='finish_live.py'}
    trace=ROOT/'06_TOOLS/EXPERIMENTS/adr_1037/trace.py';f['runner_hashes'][rel(trace)]=sha(trace)
    for key in ('provider_authorization','optimization_authorization'):
        f['runner_hashes'][f[key+'_path']]=f[key+'_sha256']
    f['evaluation_scripts']={rel(HERE/n):sha(HERE/n) for n in ('collect_metrics.py','common.py','wire_audit.py',
        'delivery_spans.py','physical_transport.py','gate.py','judge.py','evaluate_matrix.py','report_results.py')}
    ledger=ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py';f['evaluation_scripts'][rel(ledger)]=sha(ledger)
    exact(ART/'design-freeze.json',f)
    print('Frozen9 cells before calls; exact input/output/runner/source/policy bindings')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','freeze']);args=parser.parse_args()
    (prepare if args.phase=='prepare' else freeze)()
