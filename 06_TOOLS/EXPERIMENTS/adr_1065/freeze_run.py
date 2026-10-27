"""Freeze exactly three questions and nine cells before any model call."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json
from common import ROOT, ADR, ART, read, save, sha, exact_write, canonical_digest
CAND = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1065/task-local-r1'
PRIOR = ROOT/'04_EXPERIMENTS/ADR/ADR-1063-ontology-mvp-catalogue-projection/artifacts/design-freeze.json'
PREFLIGHT_STEM = 'task-preflight-final-03'
def rel(p): return str(p.relative_to(ROOT))


def verify_preflight(code, files, order):
    """Read only small proof files; no runtime/corpus/model imports or execution."""
    path=ART/(PREFLIGHT_STEM+'.json')
    before=sha(path); proof=read(path)
    def require(value, reason):
        if not value: raise ValueError('task preflight: '+reason)
    code=code.resolve()
    require(code.is_relative_to((CAND/'revisions').resolve()) and code.name=='snapshot',
            'current code is not a frozen candidate revision')
    require(proof.get('schema_version')=='task-local-saved-failure-preview-v1','unknown schema')
    require(proof.get('code_root')==rel(code),'preview did not use the current frozen root')
    runtime_files={name:h for name,h in files.items()
        if name.startswith(('02_BACKEND/','00_SYSTEM'))
        and Path(name).suffix in ('.py','.json') and '__pycache__' not in Path(name).parts}
    require(proof.get('files')==runtime_files,'runtime code/config file map differs')
    require(type(proof.get('calls')) is int and proof['calls']==0
            and type(proof.get('source_database_loads')) is int and proof['source_database_loads']==0,
            'preview used or did not prove zero model/source-database calls')
    require(proof.get('original_wire_reconstruction_claimed') is False
            and proof.get('all_within_mode_budget') is True,'preview is not a successful new candidate compilation')
    tools=[ROOT/'06_TOOLS/EXPERIMENTS/adr_1065/preflight_replay.py',
           ROOT/'06_TOOLS/EXPERIMENTS/adr_1065/common.py',
           ROOT/'06_TOOLS/EXPERIMENTS/adr_1063/replay_catalogue.py']
    expected_tools={rel(p):sha(p) for p in tools}
    require(proof.get('tool_files')==expected_tools,'preview tool map changed or is unknown')
    require(proof.get('helper_path')==rel(tools[-1])
            and proof.get('helper_sha256')==expected_tools[rel(tools[-1])],'historical helper binding differs')
    cells=proof.get('cells');names=[f"{r['ordinal']:03d}-{r['case_id']}-{r['arm']}" for r in order]
    require(len(order)==9 and len(set(names))==9 and isinstance(cells,list)
            and [r.get('cell') for r in cells]==names,'nine exact cells/order are not proven')
    limits={'ENTRY':24000,'CATALOGUE':24000,'REVIEW':48000,'REPAIR':16000,'ASSESS':64000,'COMPOSE':32000}
    dependencies={rel(path):before,**expected_tools}
    matrix=ROOT/'04_EXPERIMENTS/ADR/ADR-1063-ontology-mvp-catalogue-projection/artifacts/matrix'
    for row,name in zip(cells,names,strict=True):
        require(row.get('current_originals_exact') is True
                and row.get('original_request_reconstructed') is False,'current originals or new-preview identity unknown')
        require(type(row.get('calls')) is int and row['calls']==0
                and type(row.get('source_database_loads')) is int and row['source_database_loads']==0,
                'cell preview calls/source-database use is unknown')
        measured=row.get('candidate_prepared',{});mode=measured.get('input_mode');size=measured.get('measured_chars')
        require(measured.get('contract')=='execution-review-input-modes-v1'
                and mode in limits and measured.get('status')=='WITHIN_BUDGET'
                and type(size) is int and 0<size<=limits[mode]
                and measured.get('mode_limit_chars')==limits[mode]
                and measured.get('outer_limit_chars')==100000
                and measured.get('max_context_chars')==min(limits[mode],100000)
                and measured.get('physical_attempt_reserved') is False
                and measured.get('model_delivery_claimed') is False,'mode budget or non-delivery proof invalid')
        cell=matrix/name
        journals=list((cell/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'))
        require(len(journals)==1,'exact historical native journal unavailable')
        inputs=[journals[0],cell/'runtime/case-memory/cases-v4.sqlite',
                cell/'effective-profile.json',cell/'model/call-001-service/request.json']
        # A completed historical SQLite artifact may legitimately retain WAL.
        # Preserve it exactly; checkpointing would mutate the original evidence.
        # Include every existing sidecar (also an empty one) in the same before/
        # after hash proof produced by preflight. A missing or changed WAL fails.
        inputs += [wal for source in list(inputs) if (wal:=Path(str(source)+'-wal')).is_file()]
        for source in inputs:
            require(source.resolve().is_relative_to(cell.resolve()),'source input escapes its exact cell')
        expected_inputs={rel(source):sha(source) for source in inputs}
        require(row.get('source_inputs')==expected_inputs,'historical source inputs changed or are unknown')
        require(row.get('source_journal_sha256')==expected_inputs[rel(journals[0])],
                'native journal receipt differs')
        preview=ART/(PREFLIGHT_STEM+'-requests')/(name+'.json.gz')
        with gzip.open(preview,'rb') as stream: raw=stream.read(1024*1024+1)
        require(len(raw)<=1024*1024,'preview payload exceeds bounded proof size')
        require(hashlib.sha256(raw).hexdigest()==row.get('candidate_request_sha256'),
                'saved candidate request hash differs')
        request=json.loads(raw);encoded=json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        require(encoded.encode()==raw and len(encoded)==size
                and canonical_digest(request)==measured.get('request_sha256'),
                'measured candidate request differs from saved request bytes')
        dependencies.update(expected_inputs);dependencies[rel(preview)]=sha(preview)
    require(sha(path)==before,'preview receipt changed during verification')
    return {'path':rel(path),'sha256':before,'dependencies':dependencies,
            'cells':names,'current_frozen_code_root':rel(code),'all_within_mode_budget':True,
            'calls':0,'source_database_loads':0,'original_wire_reconstruction_claimed':False}

def main():
    assert not (ART/'design-freeze.json').exists() and not (ART/'matrix').exists()
    old=read(PRIOR); f=deepcopy(old)
    code=CAND/'revisions'/read(CAND/'candidate.json')['revisions'][-1]['revision_id']/'snapshot'
    manifest=read(ADR/'실험/manifest.json')
    policy=read(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    if policy.get('provider_failover',{}).get('scope')!=manifest['experiment_id']:
        raise ValueError('provider failover scope differs from current experiment before run freeze')
    files={str(p.relative_to(code)):sha(p) for p in code.rglob('*') if p.is_file()}
    for name in ('release-check','frozen-api'):
        t=read(ART/(name+'-summary.json'))
        assert t['validation_status']==0 and not t['new_failures'] and t['files']==files
        assert not t['production_import_leaks'] and not t['candidate_changed_during_tests']
        if name=='release-check':
            assert t['passed']>=982 and len(t['known_existing_failures'])<=8
            assert len(read(ART/'known-existing-failures.json')['failures'])==8
    source=ROOT/old['data_path']/'store.sqlite'; before=source.stat()
    assert sha(source)==old['store_sha256']; after=source.stat()
    fields=lambda s:(s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    assert fields(before)==fields(after)
    receipt=read(ROOT/old['source_integrity_path'])
    assert (receipt['size'],receipt['mtime_ns'],receipt['ctime_ns'])==fields(after)
    for path,h in read(ART/'preservation.json')['files'].items(): assert sha(ROOT/path)==h
    for key in ('product_cases','evaluator_cases','corpus','authorization','evaluation_contract'):
        assert sha(ROOT/old[key+'_path'])==old[key+'_sha256']
    m=read(ADR/'실험/manifest.json'); plan=read(ART/'implementation-plan.json')
    order=plan['execution_order']
    assert len(order)==9 and order==old['execution_order'][:9]
    assert m['design']['execution_order']==order and m['runs'][0]['arm_ids']==['A0','A1','A2']
    assert {a['id'] for a in m['design']['arms']}=={'A0','A1','A2'}
    preflight=verify_preflight(code,files,order)
    for key,name in [('product_cases','cases-product.json'),('evaluator_cases','cases-evaluator.json'),('corpus','corpus.json'),('authorization','authorization.json')]:
        f[key+'_path']=rel(ART/name);f[key+'_sha256']=sha(ART/name)
    product=read(ART/'cases-product.json')['cases']; evaluation=read(ART/'cases-evaluator.json')['cases']
    assert [c['case_id'] for c in product]==['fsc-hard-005','cm-023','fsc-hard-008']
    assert all(set(c)=={'case_id','question'} for c in product)
    assert [(c['case_id'],c['question']) for c in evaluation]==[(c['case_id'],c['question']) for c in product]
    for binding in m['design']['code_isolation']['candidates']:
        binding['runner_sha256']=sha(ROOT/binding['runner_path'])
    assert {b['arm_id'] for b in m['design']['code_isolation']['candidates']}=={'A0','A1','A2'}
    m['design']['criteria_record']['sha256']=sha(ART/'implementation-plan.json')
    save(ADR/'실험/manifest.json',m)
    f.update(frozen_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        experiment_id=m['experiment_id'],design=m['design'],manifest_sha256_at_freeze=sha(ADR/'실험/manifest.json'),
        code_root=rel(code),files=files,policy_sha256=sha(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),
        validation_inheritance=False,validation_note='Exact current task-local candidate and frozen API checked; regression floor982 and existing8 failures retained. Exactly9 cells only.',execution_order=order)
    for key in ('client','judge_client'):
        f[key+'_path']=rel(code/'02_BACKEND/lawrag/research/experiment_client.py');f[key+'_sha256']=sha(ROOT/f[key+'_path'])
    for key,name in [('optimization_authorization','implementation-plan.json'),('validation','release-check-summary.json'),('validation_receipt','tested-freeze.json')]:
        f[key+'_path']=rel(ART/name);f[key+'_sha256']=sha(ART/name)
    f['semantic_contract_files']={p:files[p] for p in old['semantic_contract_files']}
    f['provider_failover']=read(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['provider_failover']
    f['input_output_representation'].update(execution_review=True,task_local_navigation=True,pending_global=True)
    f['equal_operational_overrides'].update(minimum_available_memory_bytes=3*1024**3,memory_limit_bytes=5*1024**3,memory_limit_kind='worker_RSS',address_space_limit_bytes=6*1024**3,minimum_disk_free_bytes=20*1024**3,maximum_swap_increase_bytes=512*1024**2)
    f['mode_limits']=plan['budgets']['input_chars']
    f['first_nine_gate']={'implementation':rel(Path(__file__).with_name('gate.py')),'sha256':sha(Path(__file__).with_name('gate.py')),'first9':order,'remaining':0,'continuation_allowed':False,'failure_stops_new_cells':True,'unknown_is_failure':True,'semantic_wrong_answer_alone_stops':False}
    f['offline_evaluation_scope']='Exactly three completed integrity-valid triples from the frozen nine-cell experiment. A stopped partial matrix permits only completed triples. No repeat/regrade.'
    f['arm_code_bindings']=m['design']['code_isolation']['candidates']
    f['shared_execution_code']='Identical A0/A1/A2 file maps; A2 code selected with per-cell ontology mode; task_local_navigation and execution_review enabled identically.'
    f['prior_design_freeze_path']=rel(PRIOR);f['prior_design_freeze_sha256']=sha(PRIOR)
    for key in ('saved_input_replay_path','saved_input_replay_sha256'):f.pop(key,None)
    f['delivery_audit_contract']={'source':'ADR-1064-experiment-v1/delivery-audit','mode':'exact-native-acquired-parent-ref-and-evidence-options','unknown_is_verified':False,'code':rel(Path(__file__).with_name('delivery_spans.py')),'sha256':sha(Path(__file__).with_name('delivery_spans.py'))}
    f['runner_hashes']={rel(p):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    f['runner_hashes'].update(preflight['dependencies'])
    f['task_preflight']=preflight
    for name in ('known-existing-failures.json','validation-coverage-plan.json','implementation-plan.json'):
        f['runner_hashes'][rel(ART/name)]=sha(ART/name)
    trace=ROOT/'06_TOOLS/EXPERIMENTS/adr_1037/trace.py';f['runner_hashes'][rel(trace)]=sha(trace)
    for key in ('provider_authorization','optimization_authorization'):f['runner_hashes'][f[key+'_path']]=f[key+'_sha256']
    f['evaluation_scripts']={rel(Path(__file__).parent/n):sha(Path(__file__).parent/n) for n in ('collect_metrics.py','common.py','wire_audit.py','delivery_spans.py','physical_transport.py','gate.py','judge.py','evaluate_matrix.py','report_results.py')}
    p=ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py';f['evaluation_scripts'][rel(p)]=sha(p)
    f['reporting_rules']['semantic_accuracy']='Only frozen3 cases; use evaluation_class for reference/evidence-only denominators, pass/fail/unknown separate.'
    f['reporting_rules']['paired_required_extent']='Average exact BOUND extent coverage per case then paired arm differences; unavailable originals counted separately; primary required-article denominator retains unavailable roots.'
    f['reporting_rules']['scope']='Three fixed in-sample questions, nine cells; operational success and semantic quality separate; no continuation or generalization claim.'
    exact_write(ART/'design-freeze.json',f)
    print('FROZEN3x3=9; no continuation; exact tested code and audit rules; no live calls yet')
if __name__=='__main__':main()
