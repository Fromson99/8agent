"""Freeze a new nine-cell run after selected-code synthetic validation.

MAIN104 execution is independently gated by main-selection-binding.json.
No model, credentials, runtime/data loading, or old-result rewriting.
"""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import argparse
import hashlib
import json

from common import ROOT,ADR,ART,read,sha,exact_write
from run_case import bound_code,check_source_integrity,require,checked,rooted,TRACE

HERE=Path(__file__).parent
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1067-non-model-latency-profiling/artifacts/design-freeze.json'
FIELDS=('data_path','data_manifest_sha256','source_generation_id','store_sha256','source_store_sha256',
    'source_integrity_path','source_integrity_sha256','snapshot_path','snapshot_file_sha256','snapshot_digest',
    'corpus_total_article_roots','corpus_article_root_count_path','corpus_article_root_count_sha256',
    'dataset_preparation_path','dataset_preparation_sha256','product_cases_path','product_cases_sha256',
    'evaluator_cases_path','evaluator_cases_sha256','evaluation_contract_path','evaluation_contract_sha256',
    'execution_order','response_reception','input_output_representation','mode_limits')


def rel(path):return str(Path(path).resolve().relative_to(ROOT.resolve()))
def ref(path):return {'path':rel(path),'sha256':sha(path)}
def prospective(value):return hashlib.sha256((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()).hexdigest()


def prepare(validations):
    require(not (ART/'design-freeze.json').exists(),'existing freeze immutable')
    require(not (ART/'matrix').exists(),'execution already began')
    old=read(PRIOR);plan=read(ART/'implementation-plan.json');manifest=read(ADR/'실험/manifest.json')
    require(manifest['reservation']['status']=='in_progress' and manifest['results']['status']=='not_run','not fresh')
    require(manifest['design']['criteria_record']==ref(ART/'implementation-plan.json'),'criteria binding changed')
    parent=manifest['lineage']['parents'][0];checked(ROOT/parent['manifest_path'],parent['manifest_sha256'])
    require(read(ROOT/parent['manifest_path'])['results']['by_arm']['B2']['status']=='complete','parent not complete')
    prepared=read(ART/'candidate-bindings.json');bindings=prepared['arm_code_bindings'];maps={};codes={}
    for arm in ('A0','A1','A2'):
        code,files=bound_code({'experiment_id':manifest['experiment_id'],'arm_code_bindings':bindings},arm,'run-001')
        codes[arm]=code;maps[arm]=files
        for p,h in files.items():checked(code/p,h)
    require(maps['A0']==maps['A1']==maps['A2'],'live code mismatch')
    code,files=codes['A2'],maps['A2'];records=[]
    for name in validations:
        path=rooted(name);v=read(path)
        require(path.is_relative_to(ART) and v.get('status')==0 and v.get('failed')==0
            and v.get('passed',0)>0 and v.get('candidate_changed') is False and v.get('import_leaks')=={}
            and v.get('live_model_calls')==0 and v.get('real_corpus_loads')==0
            and v.get('files')==files and rooted(v['code_root']) in codes.values(),'failed/mismatched validation')
        records.append({**ref(path),'passed':v['passed'],'tested_code_root':v['code_root'],
            'same_file_map_arms':['A0','A1','A2'],'historical_pass_count_inherited':False})
    require(records,'current validation required')
    validation={'schema_version':'adr1074-current-validation-binding-v1','records':records,
        'all_file_maps_identical':True,'external_model_calls':0,'historical_pass_counts_inherited':False}
    policy=read(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    require(policy['model']=='qwen/qwen3.8-27b' and policy['allowed_upstream_providers']==['Parasail']
        and policy['reasoning']=={'effort':'none'} and policy.get('provider_failover') is None
        and policy['fallback_allowed'] is False and policy['http_retries']==0 and policy['max_output_tokens'] is None,
        'model policy changed')
    checked(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'))
    check_source_integrity(old)
    for k in FIELDS:
        if k.endswith('_path') and k[:-5]+'_sha256' in old:checked(rooted(old[k]),old[k[:-5]+'_sha256'])
    auth=deepcopy(read(ROOT/old['authorization_path']))
    auth.update(schema_version='adr1074-user-source-authorization-v1',experiment_id=manifest['experiment_id'],
        authorization_record=plan['user_authorization'],scope=plan['scope'],
        provider_policy='Single Parasail FP8; no historical failover exception.',source_authorization=ref(ROOT/old['authorization_path']))
    corpus=deepcopy(read(ROOT/old['corpus_path']))
    corpus['authorization_receipt']={'path':rel(ART/'authorization.json'),'sha256':prospective(auth)}
    outputs={ART/'authorization.json':auth,ART/'corpus.json':corpus,ART/'validation-binding.json':validation}
    frozen={k:deepcopy(old[k]) for k in FIELDS}
    frozen.update(schema_version='ontology-mvp-design-freeze-v1',status='FROZEN_AWAITING_MAIN104_SELECTION',
        approved_for_live_execution=True,main_selection_required=True,frozen_at=datetime.now(timezone.utc).isoformat(),
        experiment_id=manifest['experiment_id'],run_id='run-001',design=deepcopy(manifest['design']),
        manifest_path=rel(ADR/'실험/manifest.json'),manifest_sha256_at_freeze=sha(ADR/'실험/manifest.json'),
        code_root=rel(code),files=files,arm_code_bindings=bindings,
        baseline_policy_sha256=sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),policy_sha256=sha(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),
        provider_failover=None,enforce_input_character_limits=False,minimal_action_choices=True,
        resource_limits=plan['resource_limits'],equal_operational_overrides={
            'max_model_attempts':40,'max_tool_actions':1024,'wall_seconds':1800,'max_transport_retries':1,
            'http_retries':0,'max_output_tokens':None},
        semantic_contract_files={p:files[p] for p in old['semantic_contract_files']},
        source_design_freeze=ref(PRIOR),completed_parent_manifest=ref(ROOT/parent['manifest_path']),
        validation_records=records,live_model_calls_before_freeze=0,profiling=plan['profiling'],
        shared_execution_code='Three exact code maps; only supplied ontology mode differs.',
        reporting_rules={'environment':'Local WSL ontology candidate after MAIN104 SQL selection; ontology not active MAIN.',
            'performance':'Model-boundary and coarse view timing; no equal-decision performance claim against old live runs.',
            'history':'Old failed/live/SQL diagnostic results immutable and not counted.',
            'semantic':'Known-in-sample three-question probe; same-model judge is provisional.',
            'uncertainty':'Missing observations/usage remain unknown, not zeros.'},
        first_nine_gate={'implementation':rel(HERE/'gate.py'),'sha256':sha(HERE/'gate.py'),
            'first9':deepcopy(plan['execution_order']),'remaining':0,'continuation_allowed':False,
            'failure_stops_new_cells':True,'unknown_is_failure':True,'semantic_wrong_answer_alone_stops':False},
        delivery_audit_contract={'source':'ADR-1064-experiment-v1/delivery-audit',
            'mode':'exact-native-acquired-parent-ref-and-evidence-options','unknown_is_verified':False,
            'code':rel(HERE/'delivery_spans.py'),'sha256':sha(HERE/'delivery_spans.py')})
    for name,path in [('client',code/'02_BACKEND/lawrag/research/experiment_client.py'),
        ('judge_client',code/'02_BACKEND/lawrag/research/experiment_client.py'),('optimization_authorization',ART/'implementation-plan.json')]:
        frozen[name+'_path']=rel(path);frozen[name+'_sha256']=sha(path)
    for name,path in [('authorization',ART/'authorization.json'),('corpus',ART/'corpus.json'),('validation_receipt',ART/'validation-binding.json')]:
        frozen[name+'_path']=rel(path);frozen[name+'_sha256']=prospective(outputs[path])
    frozen['validation_path']=records[0]['path'];frozen['validation_sha256']=records[0]['sha256']
    frozen['runner_hashes']={rel(p):sha(p) for p in [*sorted(HERE.glob('*.py')),TRACE,ART/'implementation-plan.json']}
    evaluation=[HERE/n for n in ('common.py','judge.py','evaluate_matrix.py','collect_metrics.py','wire_audit.py','delivery_spans.py','physical_transport.py','gate.py','report_results.py')]
    evaluation.append(ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py')
    frozen['evaluation_scripts']={rel(p):sha(p) for p in evaluation}
    outputs[ART/'manifest-at-freeze.json']=manifest
    outputs[ART/'design-freeze.json']=frozen
    return outputs


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--validation',action='append',required=True);parser.add_argument('--write',action='store_true')
    a=parser.parse_args();outputs=prepare(a.validation)
    if a.write:
        for p,v in outputs.items():exact_write(p,v)
    print(json.dumps({'ready':True,'written':a.write,'outputs':[{'path':rel(p),'sha256':prospective(v)} for p,v in outputs.items()],
        'external_model_calls':0,'main_selection_required_before_execution':True},ensure_ascii=False))
