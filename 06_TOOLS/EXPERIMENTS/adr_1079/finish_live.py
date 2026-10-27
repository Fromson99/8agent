"""Report the one immutable observation; never rerun, judge or promote."""
import importlib.util
import json
from pathlib import Path
from common import ROOT, ADR, ART, read, save, sha
from run_case import load_frozen, require, checked, cell_directory, digest
from extract_timing import analyze


def disposition(completed, gate_passed, transition_observed):
    if not completed or not gate_passed:return 'FAILED'
    return 'TRANSITION_VERIFIED' if transition_observed else 'NOT_OBSERVED'


def ref(path):return {'path':str(path.relative_to(ROOT)),'sha256':sha(path)}


def main():
    frozen,code,*_=load_frozen();cell=frozen['execution_order'][0];directory=cell_directory(cell)
    require((directory/'result.json').is_file(),'no observed result; no empty success report')
    result=read(directory/'result.json');metrics=read(directory/'metrics.json');gate=read(ART/'gate.json')
    require(gate['report_sha256']==digest({k:v for k,v in gate.items() if k!='report_sha256'}),'gate changed')
    require(gate['design_freeze_sha256']==sha(ART/'design-freeze.json'),'gate freeze changed')
    resources=read(ART/'matrix/001-cm-023-A2.resources.json')
    require(resources['process_reaped'] is True,'worker still active')
    transition=next((row.get('transition',{}) for row in gate.get('cells',[]) if row.get('cell')==cell),{})
    complete=result.get('completed') is True;passed=gate.get('passed') is True
    status=disposition(complete,passed,transition.get('status')=='OBSERVED')
    timing=analyze(read(directory/'profile.json'));save(ART/'observed-timing.json',timing)
    ledger_path=ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py'
    checked(ledger_path,frozen['evaluation_scripts'][str(ledger_path.relative_to(ROOT))])
    spec=importlib.util.spec_from_file_location('adr1079_ledger_report',ledger_path)
    ledger_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(ledger_module)
    case_ledger=read(directory/'retrieval-ledger-case.json')
    ledger=ledger_module.build_experiment_artifact('ADR-1079',frozen['experiment_id'],[
        ledger_module.build_run_artifact('run-001',[case_ledger],{'A2':[s['stage_id'] for s in case_ledger['stages']]})])
    save(ART/'retrieval-ledger.json',ledger)
    summary={'schema_version':'adr1079-single-cell-result-v1','status':status,'cell':cell,
        'completed_observations':int(complete),'planned_cells':1,'observed_result_files':1,
        'operational_gate_passed':passed,'transition':transition,'success_criteria_met':status=='TRANSITION_VERIFIED',
        'model_calls':result.get('physical_model_calls',metrics.get('usage',{}).get('physical_calls')),
        'offline_evaluator_calls':0,'whole_cell_retries':0,'quality_certified':False,
        'ontology_effect_certified':False,'main_promotable':False,'environment':'local isolated candidate after MAIN105',
        'service_status':metrics.get('service_status'),'service_outcome':result.get('outcome'),
        'usage':metrics.get('usage'),'latency_seconds':metrics.get('latency_seconds'),
        'source_integrity':metrics.get('source_integrity'),'request_acl_check':metrics.get('request_acl_check'),
        'required_targets':metrics.get('required_targets'),'gate_reasons':gate.get('reasons'),
        'native_failures':result.get('native_failures'),
        'limitations':['One known in-sample case; no A0/A1 comparison or legal-quality judge.',
            'No causal timing comparison against MAIN104/105 or earlier1074.',
            'If the relevant transition is not naturally selected, no repeat or forced choice.'],
        'input_artifacts':[ref(directory/n) for n in ('result.json','metrics.json','execution-audit.json','profile.json')]
            +[ref(ART/n) for n in ('gate.json','design-freeze.json','main-selection-binding.json','retrieval-ledger.json','observed-timing.json')]}
    save(ART/'matrix-summary.json',summary)
    manifest=read(ADR/'실험/manifest.json');run=manifest['runs'][0]
    # Execution completion is distinct from success. A native bounded result
    # is complete even when the desired transition was not observed.
    run_status='complete' if complete else 'failed'
    run.update(status=run_status,artifact_path=str((ART/'matrix-summary.json').relative_to(ROOT)),
        sha256=sha(ART/'matrix-summary.json'),success_criteria_met=summary['success_criteria_met'])
    manifest['results']={'status':run_status,'by_arm':{'A2':{'status':run_status,
        'observations':int(complete),'success_criteria_met':summary['success_criteria_met'],
        'transition_status':transition.get('status','NOT_OBSERVED')}},'comparisons':[],
        'judge_disagreements':None,'usage':summary['usage'],'latency':{'seconds':summary['latency_seconds']},
        'error_taxonomy':result.get('native_failures',[]),'quality_certified':False,'main_promotable':False,
        'operational_gate_passed':passed,'terminal_status':status}
    final=case_ledger['stages'][-1];count=final['after_count'];total=metrics['corpus_total_article_roots']
    manifest['retrieval_accounting'].update(changed=True,corpus_total=total,
        before_filter={'status':'unavailable','reason':'No complete prefilter snapshot inferred'},
        after_filter={'status':'unavailable','reason':'Exact acquisition/delivery/citation ledger retained'},
        presented_total={'A2':count},presented_mean={'A2':count},presented_p50={'A2':count},presented_p95={'A2':count},
        golden_recall={'A2':final['golden_recall']},selectivity={'A2':count/total},not_applicable_reason=None)
    manifest['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',
        artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256=sha(ART/'retrieval-ledger.json'),
        not_applicable_reason=None)
    question=read(ROOT/frozen['product_cases_path'])['cases'][0]['question']
    qpath=ADR/'실험/질문-001-cm-023.md'
    qpath.write_text(f'''# 질문 001 — CM023 A2 단일 셀

## 1. 실행 메타

ADR1079/run-001/A2. 결과 {status}, 실행 관찰 완료 {complete}, 운영 gate {passed}. 1077/B1 위에1081 성능3파일 hunk와pin31개를 합친749파일.

## 2. 사용자 질문 원문

{question}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

법률 기준답변으로 채점하지 않았다. 읽은 원문과 판단 참조를 다음 선택 계약까지 보존하는 것이 기준이다. 평가용 근거 좌표는 실행 후 원장 결속에만 썼다.

## 4. 제품 입력을 구성한 원값

[단일 질문](../artifacts/product-cases.json), [승인](../artifacts/authorization.json), [동결](../artifacts/design-freeze.json), [실제 요청](../artifacts/matrix/001-cm-023-A2/request.json).

### 회수·탈락 단계 원장 — run·arm별

[실제 원문 원장](../artifacts/retrieval-ledger.json). 원문 확보·전달·인용을 구분한다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

물리 호출 {summary['model_calls']}회. [원시 호출 디렉터리](../artifacts/matrix/001-cm-023-A2/model), [usage](../artifacts/matrix/001-cm-023-A2/metrics.json). 누락 usage는 unknown으로 보존한다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

같은 제품40물리호출 예산 안의 native gateway 경로다. 별도 수동 repair나 전체 셀 재실행은0회다. [행동·전송 감사](../artifacts/matrix/001-cm-023-A2/execution-audit.json).

## 7. 채점 호출과 반복 판정

평가 모델0회, 반복 채점0회. [운영 gate](../artifacts/gate.json)와 고정 전환 관찰기를 사용했다. 법률 정답을 인증하지 않는다.

## 8. 사례 최종 판정

{status}. [집계](../artifacts/matrix-summary.json), [원문](../artifacts/matrix/001-cm-023-A2/evidence-audit.json), [시간](../artifacts/observed-timing.json). 전체 온톨로지 효과·9셀 완주·MAIN 기능 반영으로 확대하지 않는다.
''')
    manifest['questions'][0]['sha256']=sha(qpath);save(ADR/'실험/manifest.json',manifest)
    with (ADR/'README.md').open('a') as stream:
        stream.write(f'\n## 실행 결과 기록\n\n단일 셀 **{status}**. [결과](artifacts/matrix-summary.json) · [질문 기록](실험/질문-001-cm-023.md). 운영 gate={passed}, 관찰 완료={complete}; 법률 품질·온톨로지 효과는 인증하지 않는다.\n')
    save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1079',
        'created_at':manifest['reservation']['created_at'],'files':[
            {**ref(p),'bytes':p.stat().st_size,'description':'Frozen one-cell evidence; no repetition or semantic judge',
             'contains_raw_prompts_and_outputs':'model' in p.parts or p.name=='journal.sqlite'}
            for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and p.suffix!='.lock']})
    print(json.dumps({'status':status,'model_calls':summary['model_calls'],'operational_gate':passed,'completed':complete}))


if __name__=='__main__':main()
