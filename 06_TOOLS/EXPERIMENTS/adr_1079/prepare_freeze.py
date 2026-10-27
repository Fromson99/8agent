"""Seal the one-cell run only after MAIN105 actual consumer evidence exists."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
from common import ROOT, ADR, ART, read, sha, exact_write
from run_case import require, checked, rooted, bound_code, check_source_integrity, TRACE

HERE=Path(__file__).parent
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1074-ontology-after-sql-main/artifacts/design-freeze.json'


def ref(path):return {'path':str(path.relative_to(ROOT)),'sha256':sha(path)}


def prepare(consumer_path, validations):
    require(not (ART/'matrix').exists() and not (ART/'design-freeze.json').exists(), 'already sealed or run')
    selected_path=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    selected=read(selected_path); consumer=read(consumer_path)
    require(selected['generation']==105 and consumer.get('passed') is True,
        'verified MAIN105 required before final freeze')
    require(consumer.get('pointer')==selected and consumer.get('binding',{}).get('generation')==105
        and consumer['binding']['release_id']==selected['release_id']
        and consumer['binding']['release_manifest_sha256']==selected['release_manifest_sha256'],
        'actual consumer and active MAIN105 differ')
    checked(ROOT/selected['manifest_path'], selected['release_manifest_sha256'])
    old=read(PRIOR); plan=read(ART/'implementation-plan.json'); manifest=read(ADR/'실험/manifest.json')
    require(manifest['design']['criteria_record']==ref(ART/'implementation-plan.json'),'criteria changed')
    parents=manifest['lineage']['parents']
    require([(p['experiment_id'],p['arm_id'],p['relation']) for p in parents]==[
        ('ADR-1077-experiment-v1','B1','merged_from'),
        ('ADR-1081-experiment-v1','optimized','merged_from')], 'final completion parents differ')
    for parent in parents:
        checked(ROOT/parent['manifest_path'],parent['manifest_sha256'])
        record=read(ROOT/parent['manifest_path'])
        require(record['results']['status']=='complete'
            and record['results']['by_arm'][parent['arm_id']]['status']=='complete','parent incomplete')
    prepared=read(ART/'candidate-bindings.json'); bindings=prepared['arm_code_bindings']
    code,files=bound_code({'experiment_id':manifest['experiment_id'],'arm_code_bindings':bindings},'A2','run-001')
    composition=read(ART/'main105-alignment-rev2.json')
    require(files==composition['files'] and prepared['parent_code_files']==composition['old_files'],
        'product differs from declared composition')
    checked(ART/'main-performance-equivalence.json',prepared['main_performance_equivalence']['sha256'])
    for p,h in files.items():checked(code/p,h)
    records=[]
    for name in validations:
        path=rooted(name); value=read(path)
        require(path.is_relative_to(ART) and value.get('status')==0 and value.get('failed')==0
            and value.get('passed',0)>0 and value.get('candidate_changed') is False
            and value.get('import_leaks')=={} and value.get('files')==files
            and value.get('live_model_calls')==0 and value.get('real_corpus_loads')==0,
            'current runner/contract validation missing or invalid')
        records.append({**ref(path),'passed':value['passed']})
    require(records,'validation required')
    check_source_integrity(old)
    checked(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'))
    auth=deepcopy(read(ROOT/old['authorization_path']))
    cases=read(ART/'product-cases.json')['cases']
    auth.update(schema_version='adr1079-user-source-authorization-v1',experiment_id=manifest['experiment_id'],
        authorization_record=plan['user_authorization'],scope=plan['scope'],
        source_authorization=ref(ROOT/old['authorization_path']))
    auth['case_question_sha256']={c['case_id']:auth['case_question_sha256'][c['case_id']] for c in cases}
    exact_write(ART/'authorization.json',auth)
    corpus=deepcopy(read(ROOT/old['corpus_path'])); corpus['authorization_receipt']=ref(ART/'authorization.json')
    exact_write(ART/'corpus.json',corpus)
    exact_write(ART/'validation-binding.json',{'records':records,'parent_exact':False,
        'composition_exact':True,'live_model_calls':0})
    frozen=deepcopy(old)
    frozen.update(status='FROZEN_MAIN105_VERIFIED',frozen_at=datetime.now(timezone.utc).isoformat(),
        experiment_id=manifest['experiment_id'],design=manifest['design'],run_id='run-001',
        manifest_path=str((ADR/'실험/manifest.json').relative_to(ROOT)),
        manifest_sha256_at_freeze=sha(ADR/'실험/manifest.json'),code_root=str(code.relative_to(ROOT)),
        files=files,parent_code_files=prepared['parent_code_files'],arm_code_bindings=bindings,
        execution_order=plan['execution_order'],
        completed_parent_manifests=[{**ref(ROOT/p['manifest_path']),'arm_id':p['arm_id']} for p in parents],
        composition_receipt=ref(ART/'main105-alignment-rev2.json'),
        main_performance_equivalence=ref(ART/'main-performance-equivalence.json'),
        validation_records=records,source_design_freeze=ref(PRIOR),
        semantic_contract_files={p:files[p] for p in old['semantic_contract_files']},
        policy_sha256=files['00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'],
        baseline_policy_sha256=sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),
        shared_execution_code='1077 B1 plus 1081 performance hunks with selected-directory forwarding; one A2 cell.',
        reporting_rules={'environment':'Local isolated ontology candidate after MAIN105 actual selection',
            'performance':'Coarse model/non-model timing only; no causal A/B versus MAIN or 1074',
            'semantic':'No semantic judge or ontology quality certification',
            'transition':'Natural multi-original departure must reach a transmitted next contract; otherwise NOT_OBSERVED',
            'history':'Previous failure retained; no whole-cell repetition'})
    frozen.pop('first_nine_gate',None)
    frozen.pop('completed_parent_manifest',None)
    frozen['single_cell_gate']={'code':str((HERE/'gate.py').relative_to(ROOT)),
        'sha256':sha(HERE/'gate.py'),'continuation_allowed':False,'whole_cell_retries':0,
        'transition_observation':ref(HERE/'transition_audit.py')}
    for name,path in [('client',code/'02_BACKEND/lawrag/research/experiment_client.py'),
            ('judge_client',code/'02_BACKEND/lawrag/research/experiment_client.py'),
            ('product_cases',ART/'product-cases.json'),('authorization',ART/'authorization.json'),
            ('corpus',ART/'corpus.json'),('optimization_authorization',ART/'implementation-plan.json'),
            ('validation_receipt',ART/'validation-binding.json')]:
        frozen[name+'_path']=str(path.relative_to(ROOT)); frozen[name+'_sha256']=sha(path)
    frozen['validation_path']=records[0]['path']; frozen['validation_sha256']=records[0]['sha256']
    frozen['runner_hashes']={str(p.relative_to(ROOT)):sha(p) for p in [*sorted(HERE.glob('*.py')),TRACE,ART/'implementation-plan.json']}
    frozen['evaluation_scripts']={str(p.relative_to(ROOT)):sha(p) for p in
        [*[HERE/n for n in ('common.py','collect_metrics.py','wire_audit.py','delivery_spans.py',
            'physical_transport.py','gate.py','transition_audit.py')],
         ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py']}
    frozen['delivery_audit_contract']['code']=str((HERE/'delivery_spans.py').relative_to(ROOT))
    frozen['delivery_audit_contract']['sha256']=sha(HERE/'delivery_spans.py')
    exact_write(ART/'manifest-at-freeze.json',manifest)
    exact_write(ART/'design-freeze.json',frozen)
    exact_write(ART/'main-selection-binding.json',{'schema_version':'adr1079-main-selection-binding-v1',
        'verified':True,'actual_service_verified':True,'main_generation':105,'release_id':selected['release_id'],
        'design_freeze_sha256':sha(ART/'design-freeze.json'),'active_release_sha256':sha(selected_path),
        'evidence':[ref(consumer_path)],'checked_at':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'frozen':True,'main_generation':105,'product_files':len(files),'cells':1,'model_calls':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--consumer',required=True);p.add_argument('--validation',action='append',required=True)
    a=p.parse_args();prepare(rooted(a.consumer),a.validation)
