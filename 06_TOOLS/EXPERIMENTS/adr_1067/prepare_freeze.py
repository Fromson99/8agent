"""Prepare fresh ADR1067 execution bindings; only --write creates artifacts.

No candidate mutation, source DB read, API invocation or performance run.
Historical results are immutable replay inputs, never new validation results.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from common import ROOT, ADR, ART, read, sha, canonical_digest, exact_write
from run_case import (bound_code, checked, check_source_integrity, require, rooted,
    MAX_CALLS, MAX_TOOLS, WALL_SECONDS, MEMORY_LIMIT, MIN_AVAILABLE,
    MIN_DISK_FREE, MAX_SWAP_INCREASE, ADDRESS_SPACE_LIMIT, TRACE)

HERE=Path(__file__).parent
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts'
PARENT=ROOT/'04_EXPERIMENTS/ADR/ADR-1065-ontology-task-local-navigation/실험/manifest.json'
ARMS=('B0','B1','A0','A1','A2')
INHERITED=('data_path','data_manifest_sha256','source_generation_id','store_sha256',
    'source_store_sha256','source_integrity_path','source_integrity_sha256',
    'snapshot_path','snapshot_file_sha256','snapshot_digest','corpus_total_article_roots',
    'corpus_article_root_count_path','corpus_article_root_count_sha256',
    'dataset_preparation_path','dataset_preparation_sha256',
    'product_cases_path','product_cases_sha256','evaluator_cases_path','evaluator_cases_sha256',
    'evaluation_contract_path','evaluation_contract_sha256','execution_order')


def rel(path):return str(Path(path).resolve().relative_to(ROOT.resolve()))


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()


def prospective_sha(value):
    import hashlib
    return hashlib.sha256(encoded(value)).hexdigest()


def reference(path):
    path=Path(path).resolve()
    require(path.is_relative_to(ROOT),'source outside workspace')
    return {'path':rel(path),'sha256':sha(path)}


def parse_bindings(arguments,experiment):
    bindings=[];codes={};maps={}
    for value in arguments:
        arm,target=value.split('=',1);path,revision_id=target.rsplit('@',1)
        require(arm in ARMS and arm not in codes,'duplicate/unknown arm binding')
        manifest_path=rooted(path)
        if manifest_path.is_dir():manifest_path=manifest_path/'candidate.json'
        candidate=read(manifest_path)
        revisions=[r for r in candidate['revisions'] if r['revision_id']==revision_id]
        require(len(revisions)==1,'explicit candidate revision missing')
        binding={'candidate_id':candidate['candidate_id'],'experiment_id':experiment,'arm_id':arm,
            'run_ids':['run-001' if arm.startswith('B') else 'run-002'],
            'manifest_path':rel(manifest_path),'manifest_sha256':sha(manifest_path),
            'revision_id':revision_id,'revision_sha256':revisions[0]['revision_sha256'],
            'runner_path':rel(HERE/'run_matrix.py'),'runner_sha256':sha(HERE/'run_matrix.py')}
        code,files=bound_code({'experiment_id':experiment,'arm_code_bindings':[binding]},arm,binding['run_ids'][0])
        for path,digest in files.items():checked(code/path,digest)
        require({relpath for relpath in files}=={str(p.relative_to(code)) for p in code.rglob('*') if p.is_file()},
                'unregistered file in frozen candidate')
        bindings.append(binding);codes[arm]=code;maps[arm]=files
    require(set(codes)==set(ARMS),'all B0/B1/A0/A1/A2 explicit bindings are required')
    require(all(maps[a]==maps['B1'] for a in ('A0','A1','A2')),'live code differs from optimized code')
    return sorted(bindings,key=lambda b:ARMS.index(b['arm_id'])),codes,maps


def validation_records(paths,codes,maps):
    records=[];covered=set()
    for path in paths:
        path=rooted(path);value=read(path)
        require(path.is_relative_to(ART) and value.get('status')==0
            and value.get('failed')==0 and type(value.get('passed')) is int and value['passed']>0
            and value.get('candidate_changed') is False and value.get('import_leaks')=={}
            and value.get('live_model_calls')==0 and value.get('real_corpus_loads')==0,
            'current validation is not a successful frozen-code synthetic check')
        code=rooted(value['code_root'])
        matched=[arm for arm in ARMS if codes[arm]==code and maps[arm]==value['files']]
        require(bool(matched),'validation does not match an exact selected revision')
        covered.update(matched)
        records.append({**reference(path),'tested_arm_ids':matched,'passed':value['passed'],
            'scope':'Only the tests named in this current artifact; no historical pass counts inherited.'})
    require('B1' in covered,'successful validation of the selected optimized revision is required')
    return {'schema_version':'adr1067-current-validation-binding-v1','records':records,
        'directly_tested_arms':sorted(covered),'same_code_live_arms':['A0','A1','A2'],
        'historical_validation_counts_imported':False,'external_model_calls':0,
        'baseline_validation_claimed':'B0' in covered}


def replay_inventory(old):
    """Freeze exact historical small request/response files, not old scores."""
    rows=[]
    for cell in old['execution_order']:
        directory=PRIOR/'matrix'/f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"
        if not directory.is_dir():continue
        result=read(directory/'result.json');reservation=read(directory/'reservation.json')
        require(result.get('cell')==cell and reservation.get('cell')==cell
            and reservation.get('design_freeze_sha256')==sha(PRIOR/'design-freeze.json'),
            'historical replay cell freeze changed')
        count=result.get('model_calls')
        require(type(count) is int and 0<count<=MAX_CALLS,'historical physical count unknown')
        events=[json.loads(line) for line in (directory/'physical-calls.jsonl').open()]
        require([e['call'] for e in events if e.get('event')=='START']==list(range(1,count+1)),
                'historical physical request inventory changed')
        require([e['call'] for e in events if e.get('event')=='END']==list(range(1,count+1)),
                'historical physical response inventory changed')
        paths=sorted((directory/'model').glob('call-*/request.json'))
        require(paths==[directory/'model'/f'call-{i:03d}-service/request.json' for i in range(1,count+1)],
                'historical request file inventory changed')
        calls=[]
        for number,path in enumerate(paths,1):
            response_path=path.with_name('response.json');receipt_path=path.with_name('response-receipt.json')
            body,envelope=read(response_path),read(receipt_path)
            require(envelope.get('body_json')==body and envelope.get('status_code')==200
                and envelope.get('stream_complete') is True
                and envelope.get('stream_receipt',{}).get('complete') is True,
                'offline replay requires a completed saved response, not a rejection/unknown acceptance')
            calls.append({'call':number,'request':reference(path),'response':reference(response_path),
                          'response_receipt':reference(receipt_path)})
        rows.append({'case_id':cell['case_id'],'arm':cell['arm'],'outer_request':reference(directory/'request.json'),
            'source_result':reference(directory/'result.json'),'source_reservation':reference(directory/'reservation.json'),
            'source_physical_events':reference(directory/'physical-calls.jsonl'),
            'source_completed':result.get('completed'),'source_outcome':result.get('outcome'),'calls':calls})
    require(bool(rows),'no historical replay inputs')
    return {'schema_version':'exact-service-replay-inputs-v1','source_design_freeze':reference(PRIOR/'design-freeze.json'),
            'historical_results_are_new_results':False,'cells':rows}


def prepare(arguments,validations,*,live_bindings=None,histories=()):
    require(not (ART/'design-freeze.json').exists(),'design freeze already exists; never overwrite')
    require(not (ART/'matrix').exists() and not (ART/'replay').exists(),
            'execution artifacts already exist; no post-result freeze')
    plan_path=ART/'implementation-plan.json';plan=read(plan_path)
    manifest_path=ADR/'실험/manifest.json';manifest=read(manifest_path)
    require(manifest['reservation']['status']=='in_progress' and manifest['results']['status']=='not_run',
            'experiment is no longer an unrun reservation')
    require({r['id']:r['status'] for r in manifest['runs']}=={'run-001':'planned','run-002':'planned'},
            'run status is not planned')
    require(manifest['design']['criteria_record']=={'path':rel(plan_path),'sha256':sha(plan_path)},
            'implementation criteria binding changed')
    for path,digest in plan['preservation'].items():checked(rooted(path),digest)
    old=read(PRIOR/'design-freeze.json');parent=read(PARENT)
    require(parent['results']['status']=='complete' and any(p['experiment_id']==parent['experiment_id']
        and p['arm_id']=='A2' and p['manifest_sha256']==sha(PARENT) for p in manifest['lineage']['parents']),
        'completed ADR1065/A2 parent binding missing')
    require(all(p['experiment_id']!=old['experiment_id'] for p in manifest['lineage']['parents']),
            'failed ADR1066 is not a completed parent')
    budgets=plan['budgets']
    require(budgets=={'model_calls_per_cell':MAX_CALLS,'tools_per_cell':MAX_TOOLS,
        'wall_seconds_per_cell':WALL_SECONDS,'worker_rss_bytes':MEMORY_LIMIT,
        'minimum_available_memory_bytes':MIN_AVAILABLE,'max_swap_increase_bytes':MAX_SWAP_INCREASE,
        'minimum_disk_free_bytes':MIN_DISK_FREE,'heavy_workers':1},'planned resource budget changed')
    arguments=list(arguments)
    if live_bindings:
        receipt_path=rooted(live_bindings);receipt=read(receipt_path)
        require(receipt.get('schema_version')=='adr1067-live-candidate-bindings-v1'
            and receipt.get('status')=='COMPLETE' and receipt.get('all_file_maps_identical') is True,
            'live candidate preparation receipt is incomplete')
        require({r['arm_id'] for r in receipt['arm_code_bindings']}=={'A0','A1','A2'},
                'live receipt arm inventory differs')
        for row in [receipt['source'],*receipt['arm_code_bindings']]:
            checked(rooted(row['manifest_path']),row['manifest_sha256'])
        arguments.extend(row['arm_id']+'='+row['manifest_path']+'@'+row['revision_id']
                         for row in receipt['arm_code_bindings'])
    bindings,codes,maps=parse_bindings(arguments,manifest['experiment_id'])
    validation=validation_records(validations,codes,maps)
    code,files=codes['A2'],maps['A2']
    policy_path=ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json';policy=read(policy_path)
    require(policy.get('provider_failover') is None and policy['fallback_allowed'] is False
        and policy['max_output_tokens'] is None and policy['http_retries']==0
        and policy['model']=='qwen/qwen3.8-27b' and policy['reasoning']=={'effort':'none'}
        and policy['allowed_upstream_providers']==['Parasail']
        and policy['provider_routing']=={'only':['parasail/fp8'],'order':['parasail/fp8'],
            'quantizations':['fp8'],'allow_fallbacks':False,'require_parameters':True},'current provider policy changed')
    for arm,arm_code in codes.items():
        checked(arm_code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',sha(policy_path))
        profile=read(arm_code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
        require(profile['max_transport_retries']==1 and profile['max_model_attempts']==MAX_CALLS
            and profile['max_tool_actions']==MAX_TOOLS and profile['wall_seconds']==WALL_SECONDS
            and profile['max_output_tokens'] is None,'profile budget changed: '+arm)
    check_source_integrity(old)  # stat plus existing streamed receipt; never opens source DB
    for key in INHERITED:
        if key.endswith('_path') and key[:-5]+'_sha256' in old:
            checked(rooted(old[key]),old[key[:-5]+'_sha256'])
    checked(rooted(old['data_path'])/'manifest.json',old['data_manifest_sha256'])
    checked(rooted(old['snapshot_path']),old['snapshot_file_sha256'])
    auth=deepcopy(read(rooted(old['authorization_path'])))
    auth.update(schema_version='adr1067-source-question-authorization-v1',experiment_id=manifest['experiment_id'],
        authorization_record=plan['user_authorization'],scope=plan['runs']['run-002'],
        provider_policy='Current Parasail FP8 only; historical provider exception is not reused.',
        source_authorization=reference(rooted(old['authorization_path'])))
    corpus=deepcopy(read(rooted(old['corpus_path'])))
    corpus['authorization_receipt']={'path':rel(ART/'authorization.json'),'sha256':prospective_sha(auth)}
    inventory=replay_inventory(old)
    outputs={ART/'authorization.json':auth,ART/'corpus.json':corpus,
             ART/'replay-inputs.json':inventory,ART/'validation-binding.json':validation}
    frozen={key:deepcopy(old[key]) for key in INHERITED}
    design=deepcopy(manifest['design']);design['budgets']=deepcopy(budgets)
    design['code_isolation']['candidates']=deepcopy(bindings)
    frozen.update(schema_version='ontology-mvp-design-freeze-v1',status='FROZEN_USER_AUTHORIZED_READY_FOR_EXECUTION',
        approved_for_live_execution=True,frozen_at=datetime.now(timezone.utc).isoformat(),
        experiment_id=manifest['experiment_id'],run_id='run-002',replay_run_id='run-001',design=design,
        manifest_path=rel(manifest_path),manifest_sha256_at_freeze=sha(manifest_path),
        code_root=rel(code),files=files,arm_code_bindings=bindings,baseline_policy_sha256=sha(policy_path),
        policy_sha256=sha(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),provider_failover=None,
        enforce_input_character_limits=False,minimal_action_choices=True,
        mode_limits={key:None for key in ('entry','catalogue','review','repair','assess','compose','outer')},
        response_reception=deepcopy(old['response_reception']),input_output_representation=deepcopy(old['input_output_representation']),
        semantic_contract_files={p:files[p] for p in old['semantic_contract_files']},
        resource_limits={'worker_rss_max_bytes':MEMORY_LIMIT,'available_memory_min_bytes':MIN_AVAILABLE,
            'disk_free_min_bytes':MIN_DISK_FREE,'swap_increase_max_bytes':MAX_SWAP_INCREASE,
            'address_space_backstop_bytes':ADDRESS_SPACE_LIMIT,'heavy_workers':1},
        equal_operational_overrides={'max_model_attempts':MAX_CALLS,'max_tool_actions':MAX_TOOLS,
            'wall_seconds':WALL_SECONDS,'max_transport_retries':1,'http_retries':0,'max_output_tokens':None},
        source_design_freeze=reference(PRIOR/'design-freeze.json'),completed_parent_manifest=reference(PARENT),
        live_model_calls_before_freeze=0,validation_inheritance=False,
        validation_scope='Only current selected-code test artifacts; historical regression history is separate.',
        profiling={'enabled':True,'mode':'coarse','raw_network_latency':'NOT_MEASURED',
            'pure_inference_latency':'NOT_MEASURED','finalizer_wait_added':False},
        replay_contract={'inventory_path':rel(ART/'replay-inputs.json'),'inventory_sha256':prospective_sha(inventory),
            'allow_prefix_diagnostic':True,'exact_request_required':True,'identity_normalization':False},
        shared_execution_code='A0/A1/A2 exactly equal selected B1 code; only ontology mode differs.',
        reporting_rules={'performance':'Exact paired service replay only; prefix and saved-schema timings remain diagnostics.',
            'historical':'ADR1066 is informed_by and replay input; no old result becomes an ADR1067 observation.',
            'semantic':'Known three-case live integration; semantic errors are separate from operational integrity.',
            'environment':'Local WSL experiment only; no GENOS or MAIN validation claim.'},
        first_nine_gate={'implementation':rel(HERE/'gate.py'),'sha256':sha(HERE/'gate.py'),
            'first9':deepcopy(old['execution_order']),'remaining':0,'continuation_allowed':False,
            'failure_stops_new_cells':True,'unknown_is_failure':True,'semantic_wrong_answer_alone_stops':False},
        delivery_audit_contract={'source':'ADR-1064-experiment-v1/delivery-audit',
            'mode':'exact-native-acquired-parent-ref-and-evidence-options','unknown_is_verified':False,
            'code':rel(HERE/'delivery_spans.py'),'sha256':sha(HERE/'delivery_spans.py')})
    for name,path in [('client',code/'02_BACKEND/lawrag/research/experiment_client.py'),
                      ('judge_client',code/'02_BACKEND/lawrag/research/experiment_client.py'),
                      ('optimization_authorization',plan_path)]:
        frozen[name+'_path']=rel(path);frozen[name+'_sha256']=sha(path)
    for name,path in [('authorization',ART/'authorization.json'),('corpus',ART/'corpus.json'),
                      ('validation_receipt',ART/'validation-binding.json')]:
        frozen[name+'_path']=rel(path);frozen[name+'_sha256']=prospective_sha(outputs[path])
    frozen['validation_records']=validation['records']
    primary=next(r for r in validation['records'] if 'B1' in r['tested_arm_ids'])
    frozen['validation_path']=primary['path'];frozen['validation_sha256']=primary['sha256']
    history_paths=[rooted(p) for p in histories]
    default_history=ART/'development-test-history.json'
    if default_history.exists() and default_history not in history_paths:history_paths.append(default_history)
    frozen['development_validation_history']=[{**reference(p),
        'role':'Historical preparation failures/observations; not passing validation.'} for p in history_paths]
    if live_bindings:frozen['live_candidate_preparation']=reference(rooted(live_bindings))
    scripts=sorted(HERE.glob('*.py'))
    frozen['runner_hashes']={rel(p):sha(p) for p in [*scripts,TRACE,plan_path]}
    legacy_reader=ROOT/'08_DEPLOYMENT/GENOS/handoffs/function_timing_20261024_r2/extract.py'
    frozen['runner_hashes'][rel(legacy_reader)]=sha(legacy_reader)
    evaluation=[HERE/n for n in ('common.py','collect_metrics.py','wire_audit.py','delivery_spans.py','physical_transport.py','gate.py')]
    evaluation.append(ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py')
    frozen['evaluation_scripts']={rel(p):sha(p) for p in evaluation}
    outputs[ART/'design-freeze.json']=frozen
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',action='append',required=True,help='ARM=repository-relative candidate directory@exact-revision')
    parser.add_argument('--validation',action='append',required=True,help='Current successful frozen validation JSON')
    parser.add_argument('--live-bindings',help='Exact prepared A0/A1/A2 receipt; replaces their --binding arguments')
    parser.add_argument('--history',action='append',default=[],help='Preserved failed/partial validation artifact, never a pass')
    parser.add_argument('--write',action='store_true',help='Create new input artifacts and design freeze; never overwrite')
    args=parser.parse_args();outputs=prepare(args.binding,args.validation,
        live_bindings=args.live_bindings,histories=args.history)
    if args.write:
        for path,value in outputs.items():exact_write(path,value)
    print(json.dumps({'ready':True,'written':args.write,'artifacts':[
        {'path':rel(p),'sha256':prospective_sha(v)} for p,v in outputs.items()],
        'model_calls':0,'source_database_reads':0,'performance_runs':0},ensure_ascii=False))


if __name__=='__main__':main()
