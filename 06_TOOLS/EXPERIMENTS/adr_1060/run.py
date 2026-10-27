from pathlib import Path
import hashlib,json,sys,copy,sqlite3,statistics
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1060-exact-wire-reference-audit';ART=ADR/'artifacts'
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1059-compact-input-guidance-binding';P=PRIOR/'artifacts'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(ROOT))


def prepare():
    plan={'adr_id':'ADR-1060','product_model_calls':0,'phase':'read-only post-run source-delivery audit',
        'hypothesis':'Stored request-local numbering is not reproducible numbering. Decode the transmitted dictionary and compare exact expanded values with the independently rebuilt saved view.',
        'success':'All21saved requests reconstruct; every decoded span matches original source/ACL; modified wire, recomputed wire hash and stale source views reject.',
        'preserve':'All1059code/data/prompts/requests/responses/usage/decisions and original metrics stay byte-exact. No correctness regrade, retrieval or new model execution.',
        'consumer':'Existing frozen1059collector plus isolated exact_wire_audit.restore; only read-only presentation-codec allowlist.',
        'failure_owner':'Audit rejects on hash, version, original value, permission or state mismatch; no retries or repair by a model.'}
    save(ART/'implementation-plan.json',plan)
    m=read(ADR/'실험/manifest.json');old=read(PRIOR/'실험/manifest.json')
    m['design'].update(hypothesis=plan['hypothesis'],primary_metric='Exact transmitted values and validated source spans',success_criteria=plan['success'],failure_criteria=plan['failure_owner'],criteria_frozen_before_run=True,operational_audit=True)
    m['design']['code_isolation'].update(mode='not_applicable',reason='Read-only audit adapter only; frozen1059product codecs are imported by hash. No product/runtime changes.',candidates=[])
    m['design']['criteria_record']={'path':rel(ART/'implementation-plan.json'),'sha256':sha(ART/'implementation-plan.json')}
    m['design']['arms'][0].update(changes='Immutable1059 metrics and raw21requests',controls='No new baseline execution')
    m['design']['arms'][1].update(changes='Decode actual dictionary instead of assigning IDs again',controls='Same exact saved requests, sources, outputs, state and schema')
    m['design']['retrieval_stage_plan']=copy.deepcopy(old['design']['retrieval_stage_plan'])
    m['design']['retrieval_stage_plan']['stages_by_arm']['wire-audit']=m['design']['retrieval_stage_plan']['stages_by_arm'].pop('compact-input')
    m['runs'][0].update(purpose='regrade',arm_ids=['wire-audit'],selection_rule='All3completed1059cells,21actual requests; no sampling',artifact_path=rel(ART/'result.json'))
    m['llm_policy']['llm_calls']=[];m['lineage']['hypothesis_delta']=plan['hypothesis']
    m['dataset']=copy.deepcopy(old['dataset']);m['dataset']['note']='Exact saved1059requests and sources. No product rerun and no semantic grade change.'
    m['retrieval_accounting']=copy.deepcopy(old['retrieval_accounting']);m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-001',artifact_path=rel(ART/'retrieval-ledger.json'),sha256='PENDING')
    save(ADR/'실험/manifest.json',m)
    frozen={'parent_manifest_sha256':sha(PRIOR/'실험/manifest.json'),'source_artifact_manifest_sha256':sha(P/'manifest.json'),
        'product_freeze_sha256':sha(P/'design-freeze.json'),'files':{rel(p):sha(p) for p in Path(__file__).parent.glob('*.py')},'model_calls':0}
    save(ART/'design-freeze.json',frozen)


def run():
    fixed=read(ART/'design-freeze.json');f=read(P/'design-freeze.json')
    assert sha(PRIOR/'실험/manifest.json')==fixed['parent_manifest_sha256'] and sha(P/'manifest.json')==fixed['source_artifact_manifest_sha256']
    assert sha(P/'design-freeze.json')==fixed['product_freeze_sha256']
    assert all(sha(ROOT/p)==h for p,h in fixed['files'].items())
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in read(P/'manifest.json')['files'])
    sys.path.insert(0,str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1059'))
    import wire_audit,collect_metrics
    cs=wire_audit.load_frozen_codecs(f)
    from exact_wire_audit import restore,test_rejection
    cs['restore']=restore
    from semantic_runtime.contracts import digest
    tests=0;attempts=0;cells=[];ledgers=[]
    for cell in f['execution_order']:
        name=f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}";src=P/'matrix'/name;out=ART/'matrix'/name
        out.mkdir(parents=True,exist_ok=False)
        for n in ('runtime','model','request.json','response.json','result.json','reservation.json','physical-calls.jsonl','call-state.json','authorization-trace.jsonl','service-entry-receipt.json','trace.jsonl'):
            if (src/n).exists():(out/n).symlink_to(src/n,target_is_directory=(src/n).is_dir())
        for p in src.glob('runtime/legal-agent/runs/*/*/journal.sqlite'):
            with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
                db.row_factory=sqlite3.Row
                records,failures=wire_audit.journal_records(db,cs,str(p.relative_to(src)))
                assert not failures,failures
                attempts+=db.execute('SELECT count(*) FROM model_attempt').fetchone()[0]
                receipt_rows={json.loads(r[0]).get('attempt_id'):json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='MODEL_INPUT_PROJECTION'")}
                for row in db.execute('SELECT a.attempt_id,a.request_json,v.body_json FROM model_attempt a JOIN model_view v USING(view_id)'):
                    receipt=receipt_rows.get(row['attempt_id'],{})
                    if 'navigation_values' not in receipt:continue
                    stored=json.loads(row['body_json']);expected=cs['compact'](cs['navigation'](stored).view(stored),stored['phase'])
                    test_rejection(expected,wire_audit.request_view(json.loads(row['request_json'])),receipt);tests+=3
        case=next(c for c in read(ROOT/f['evaluator_cases_path'])['cases'] if c['case_id']==cell['case_id'])
        metrics=collect_metrics.collect(case,cell['arm'],out,ROOT/f['data_path'],corpus_total=f['corpus_total_article_roots'],wire_codecs=cs)
        assert metrics['source_integrity']['mismatch_count']==0 and not metrics['source_integrity']['failures']
        assert metrics['request_acl_check']=='CHECKED'
        ledger=read(out/'retrieval-ledger-case.json');ledger['arm_id']='wire-audit';save(out/'retrieval-ledger-case.json',ledger);ledgers.append(ledger)
        cells.append({'case_id':cell['case_id'],'answer_coverage':metrics['answer_coverage'],'source_integrity':metrics['source_integrity'],'request_acl_check':metrics['request_acl_check'],'metrics_path':rel(out/'metrics.json'),'metrics_sha256':sha(out/'metrics.json')})
        print(cell['case_id'],'wire/source audit OK',flush=True)
    assert attempts==21
    from lawrag.runtime.retrieval_stage_ledger import build_run_artifact,build_experiment_artifact
    ledger=build_experiment_artifact('ADR-1060','ADR-1060-experiment-v1',[build_run_artifact('run-001',ledgers,{'wire-audit':['original_read','delivered','final_cited']})])
    save(ART/'retrieval-ledger.json',ledger)
    save(ART/'result.json',{'status':'complete','cells':cells,'actual_requests_verified':attempts,'corruption_rejection_checks':tests,'live_model_calls':0,'source_integrity_failures':0,'parent_preserved':True,'semantic_grade_changed':False})
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in read(P/'manifest.json')['files'])
    print('All21requests verified; additional model calls0')

if __name__=='__main__':
    if '--prepare' in sys.argv:prepare()
    else:run()
