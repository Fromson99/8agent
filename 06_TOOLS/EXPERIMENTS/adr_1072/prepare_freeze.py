"""Prepare fresh ADR1072 execution bindings; only --write creates artifacts.

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
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1071-definition-reference-point-lookup/artifacts'
PARENT=ROOT/'04_EXPERIMENTS/ADR/ADR-1065-ontology-task-local-navigation/실험/manifest.json'
ARMS=('B2',)
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
    require(set(codes)==set(ARMS),'B0 explicit binding is required')
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
    require('B2' in covered,'successful validation of the selected diagnostic revision is required')
    return {'schema_version':'adr1072-current-validation-binding-v1','records':records,
        'directly_tested_arms':sorted(covered),'same_code_live_arms':[],
        'historical_validation_counts_imported':False,'external_model_calls':0,
        'baseline_validation_claimed':'B2' in covered}


def prepare(arguments,validations):
    require(not (ART/'design-freeze.json').exists(),'existing freeze is immutable')
    require(not (ART/'replay').exists() and not (ART/'matrix').exists(),
            'no freezing after an execution reservation')
    plan_path=ART/'implementation-plan.json';plan=read(plan_path)
    manifest_path=ADR/'실험/manifest.json';manifest=read(manifest_path)
    require(manifest['reservation']['status']=='in_progress' and manifest['results']['status']=='not_run',
            'experiment is not an unrun reservation')
    require(len(manifest['runs'])==1 and manifest['runs'][0]['id']=='run-001'
        and manifest['runs'][0]['status']=='planned' and set(manifest['runs'][0]['arm_ids'])==set(ARMS),
        'only the planned single-arm diagnostic is allowed')
    criteria=manifest['design']['criteria_record']
    require(criteria['path']==rel(plan_path) and criteria['sha256']==sha(plan_path),
            'implementation criteria binding changed')
    source=plan['frozen_source_design'];source_path=rooted(source['path'])
    require(source_path==PRIOR/'design-freeze.json','unexpected source experiment')
    checked(source_path,source['sha256']);old=read(source_path)
    parent=read(PARENT)
    require(parent['results']['status']=='complete' and any(p['experiment_id']==parent['experiment_id']
        and p['arm_id']=='A2' and p['manifest_sha256']==sha(PARENT) for p in manifest['lineage']['parents']),
        'completed ADR1065/A2 parent binding missing')
    require(all(p['experiment_id']!=old['experiment_id'] for p in manifest['lineage']['parents']),
            'prior optimization ADR1071 is not a completed parent')
    resources={'worker_rss_max_bytes':MEMORY_LIMIT,'available_memory_min_bytes':MIN_AVAILABLE,
        'disk_free_min_bytes':MIN_DISK_FREE,'swap_increase_max_bytes':MAX_SWAP_INCREASE,
        'address_space_backstop_bytes':ADDRESS_SPACE_LIMIT,'heavy_workers':1}
    require(plan['resource_limits']==resources,'resource contract changed')
    bindings,codes,maps=parse_bindings(arguments,manifest['experiment_id'])
    validation=validation_records(validations,codes,maps)
    code,files=codes['B2'],maps['B2']
    policy_path=ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json';policy=read(policy_path)
    require(policy.get('provider_failover') is None and policy['fallback_allowed'] is False
        and policy['max_output_tokens'] is None and policy['http_retries']==0
        and policy['model']=='qwen/qwen3.8-27b' and policy['reasoning']=={'effort':'none'}
        and policy['allowed_upstream_providers']==['Parasail']
        and policy['provider_routing']=={'only':['parasail/fp8'],'order':['parasail/fp8'],
            'quantizations':['fp8'],'allow_fallbacks':False,'require_parameters':True},'base policy changed')
    for arm,arm_code in codes.items():
        checked(arm_code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',sha(policy_path))
        profile=read(arm_code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
        require(profile['max_transport_retries']==1 and profile['max_model_attempts']==MAX_CALLS
            and profile['max_tool_actions']==MAX_TOOLS and profile['wall_seconds']==WALL_SECONDS
            and profile['max_output_tokens'] is None,'profile changed: '+arm)
    check_source_integrity(old)
    for key in INHERITED:
        if key.endswith('_path') and key[:-5]+'_sha256' in old:
            checked(rooted(old[key]),old[key[:-5]+'_sha256'])
    checked(rooted(old['data_path'])/'manifest.json',old['data_manifest_sha256'])
    checked(rooted(old['snapshot_path']),old['snapshot_file_sha256'])
    inventory_path=rooted(old['replay_contract']['inventory_path'])
    checked(inventory_path,old['replay_contract']['inventory_sha256'])
    inventory=read(inventory_path)
    cells=[r for r in inventory['cells'] if r['case_id']=='fsc-hard-005' and r['arm']=='A0']
    require(len(cells)==1,'original first-cell recording missing or duplicated')
    for row in [cells[0]['outer_request'],*[v for c in cells[0]['calls']
            for k,v in c.items() if k in ('request','response','response_receipt')]]:
        checked(rooted(row['path']),row['sha256'])
    auth=deepcopy(read(rooted(old['authorization_path'])))
    auth.update(schema_version='adr1072-offline-source-authorization-v1',experiment_id=manifest['experiment_id'],
        authorization_record=plan['user_authorization'],scope=plan['scope'],
        external_model_calls_allowed=0,source_authorization=reference(rooted(old['authorization_path'])))
    corpus=deepcopy(read(rooted(old['corpus_path'])))
    corpus['authorization_receipt']={'path':rel(ART/'authorization.json'),'sha256':prospective_sha(auth)}
    outputs={ART/'authorization.json':auth,ART/'corpus.json':corpus,ART/'validation-binding.json':validation}
    frozen={key:deepcopy(old[key]) for key in INHERITED}
    design=deepcopy(manifest['design']);design['code_isolation']['candidates']=deepcopy(bindings)
    frozen.update(schema_version='offline-navigation-reconstruction-freeze-v1',status='FROZEN_OFFLINE_ONLY',
        approved_for_live_execution=False,offline_only=True,prefix_only=False,scripted_reconstruction=True,external_model_calls_allowed=0,
        frozen_at=datetime.now(timezone.utc).isoformat(),experiment_id=manifest['experiment_id'],run_id='run-001',
        design=design,manifest_path=rel(manifest_path),manifest_sha256_at_freeze=sha(manifest_path),
        source_experiment_freeze=reference(source_path),completed_parent_manifest=reference(PARENT),
        code_root=rel(code),files=files,arm_code_bindings=bindings,baseline_policy_sha256=sha(policy_path),
        policy_sha256=sha(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),provider_failover=None,
        enforce_input_character_limits=False,minimal_action_choices=True,mode_limits=deepcopy(old['mode_limits']),
        response_reception=deepcopy(old['response_reception']),resource_limits=resources,
        execution_order=[{'ordinal':1,'case_id':'fsc-hard-005','arm':'A0'}],
        semantic_contract_files={p:files[p] for p in old['semantic_contract_files']},
        replay_contract={'inventory_path':rel(inventory_path),'inventory_sha256':sha(inventory_path),
            'native_journal':deepcopy(plan['original_journal']),
            'native_journal_path':plan['original_journal']['path'],
            'native_journal_sha256':plan['original_journal']['sha256'],
            'expected_response_count':11,'expected_navigation_views':8,
            'schema_match':'exact','response_rewrite':False,
            'allow_prefix_diagnostic':False,'stop_at_first_request':False,
            'recorded_response_consumption':True,'exact_request_comparison':False,
            'identity_normalization':False,'rules':deepcopy(plan['reconstruction_rules'])},
        validation_inheritance=False,validation_records=validation['records'],
        live_model_calls_before_freeze=0,profiling={'mode':'coarse','raw_network_latency':'NOT_MEASURED',
            'pure_inference_latency':'NOT_MEASURED','finalizer_wait_added':False},
        reporting_rules={'full_service_replay_verified':False,'recorded_responses_used':0,
            'scope':'Eight native post-action-to-next-menu windows, literal recorded decisions, no inference or semantic quality claim.',
            'equivalence':'Per-frame hashes and full wire diffs recorded independently; valid scripted responses continue despite input drift but unmatched frames are not exact replay.',
            'history':'All1066/1067/1068 results and interrupted records remain unchanged.'})
    checked(rooted(plan['original_journal']['path']),plan['original_journal']['sha256'])
    frozen['original_event_gaps']=deepcopy(plan['original_event_gaps'])
    for name,path in [('client',code/'02_BACKEND/lawrag/research/experiment_client.py'),
                      ('judge_client',code/'02_BACKEND/lawrag/research/experiment_client.py'),
                      ('optimization_authorization',plan_path)]:
        frozen[name+'_path']=rel(path);frozen[name+'_sha256']=sha(path)
    for name,path in [('authorization',ART/'authorization.json'),('corpus',ART/'corpus.json'),
                      ('validation_receipt',ART/'validation-binding.json')]:
        frozen[name+'_path']=rel(path);frozen[name+'_sha256']=prospective_sha(outputs[path])
    primary=next(r for r in validation['records'] if 'B2' in r['tested_arm_ids'])
    frozen['validation_path']=primary['path'];frozen['validation_sha256']=primary['sha256']
    scripts=sorted(HERE.glob('*.py'))
    frozen['runner_hashes']={rel(p):sha(p) for p in [*scripts,TRACE,plan_path]}
    reader=ROOT/'08_DEPLOYMENT/GENOS/handoffs/function_timing_20261024_r2/extract.py'
    frozen['runner_hashes'][rel(reader)]=sha(reader)
    outputs[ART/'design-freeze.json']=frozen
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',action='append',required=True,help='B0/B1=candidate directory@exact-revision')
    parser.add_argument('--validation',action='append',required=True,help='Current successful frozen validation JSON')
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args();outputs=prepare(args.binding,args.validation)
    if args.write:
        for path,value in outputs.items():exact_write(path,value)
    print(json.dumps({'ready':True,'written':args.write,'artifacts':[
        {'path':rel(p),'sha256':prospective_sha(v)} for p,v in outputs.items()],
        'model_calls':0,'source_database_reads':0,'performance_runs':0},ensure_ascii=False))


if __name__=='__main__':main()


