"""Finalize the completed, provider-interrupted measurement without certifying behavior."""
from common import *
import sys, tarfile, shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS, QUESTION_HEADINGS_V4
f=read(ART/'design-freeze.json'); s=read(ART/'stage.json'); all_observations=read(ART/'observations.json')
assert (ART/'guard-result.json').exists()
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
for arm,files in f['files'].items():
    assert all(sha(ROOT/s['roots'][arm]/n)==h for n,h in files.items())
assert all(sha(ROOT/n)==h for n,h in s['working_before'].items())
assert all_observations['main_unchanged']
o=all_observations['by_arm']['candidate']; r=o['native_result']; P=ART/'known-query/candidate'
assert read(ART/'stop.json')['reason']=='PROVIDER_FAILURE'
assert r['model_calls']==2 and not (ART/'known-query/control').exists()
calls=read(P/'calls-audit.json'); view=calls[-1]
preselection={'phase':view['source_stage'],'scope_choice_count':len(view['scope_choices']),
    'no_selected_scope':view['references']['selected_scope_id'] is None,
    'no_connection_cards':not view['references']['dependency_cards'],
    'all_scopes_unselected':all(x['connection_preview']['status']=='NOT_SELECTED' and not x['selected'] for x in view['scope_choices']),
    'absence_not_claimed':view['references']['absence_proven'] is False,
    'catalog_queries':o['catalog_count'],
    'scopes92':[{'label':x['label'],'structural_selection':x['structural_selection']} for x in view['scope_choices'] if '제92조' in x['label']],
    'model_response_to_selection_received':False}
save(ART/'preselection-input-audit.json',preselection)
physical=[json.loads(line) for line in (P/'physical-calls.jsonl').read_text().splitlines()]
model_seconds=sum(x['seconds'] for x in physical)
summary={'status':'COMPLETE','execution_outcome':'PROVIDER_BLOCKED','criteria_met':None,
    'verdict':'BEHAVIOR_COMPARISON_UNAVAILABLE','physical_calls':2,'successful_calls':1,
    'failed_calls':1,'provider_error':429,'control_executed':False,
    'call_phases':[{k:x[k] for k in ('call','phase','status','seconds')} for x in physical],
    'service_seconds':r['seconds'],'model_attempt_seconds':model_seconds,
    'non_model_seconds':r['seconds']-model_seconds,
    'usage_reported_for_successful_calls':o['usage'],'failed_call_usage':'not reported',
    'source_checks':o['source_checks'],'preselection_contract':preselection,
    'selected_scope_behavior_verified':False,'reached97':False,'reached163':False,
    'final_answer_produced':False,'call_reduction_verified':False,
    'quality_certified':False,'decision_eligible':False,
    'main_changed':False,'genos_changed':False,
    'limitations':['Known exposed question; no approved answer gold or out-of-sample inference.',
        'Provider429 before explicit connection selection; no paired model behavior comparison.',
        'Input exclusion verified only before selection; selected-scope runtime and termination remain unmeasured by this model run.',
        'External Qwen observation does not certify GENOS internal model.']}
save(ART/'result.json',summary)
verification=ROOT/'09_ARTIFACTS/AUDITS/20261023-final-connection-selection/verification.json'
save(ART/'contracts-summary.json',{'path':str(verification.relative_to(ROOT)),'sha256':sha(verification),'result':read(verification)})
findings=[
    '判定: 실제 모델 실행은 제공자429로 중단되어 행동 비교 불가. 가설 통과·실패를 판정하지 않고 Proposed로 보존한다.',
    '질문: 양도차익을 산정할 때 양도가액에서 공제되는 경비는 무엇인가?',
    f'수정본 실제 호출2회: 요청 해석1회 성공, source-law-navigation-1-read-choice에서 Parasail shared pool429. 서비스 {r["seconds"]:.3f}초, 모델 시도 {model_seconds:.3f}초, 기타 {r["seconds"]-model_seconds:.3f}초. HTTP503으로 실패 응답; 법률 답변 없음. 제공자 실패 후 재시도0·비교군0·추가 감시 모델0.',
    f'원문 증거21건의 원문 slice·블록/본문/판본 hash·문서 권한 검사: {o["source_checks"]}. 조회 문서 범위65개, canonical article-root corpus{o["corpus_total"]}개. 통계는 실행된 부분에 한정한다.',
    '실제 두 번째 호출 입력에는 선택 후보26개와 확보 원문이 전달되었다. 제92조②1호가 개별 선택지로 존재한다. 모든 연결 범위 NOT_SELECTED, 연결 catalog조회0·연결 카드0·absence_proven=false를 확인했다. 모델이 최종 범위를 선택한 뒤의 흐름과97→163 도달·종료·호출 절감은 미검증이다.',
    '작업 코드 수정은 최종 명시적 선택 범위를 연결의 기준으로 사용한다. 조 전체 선택은 전체, 항·호 선택은 해당 확보 범위의 연결만 제시한다. 이미 확보한 하위 범위 선택에 재READ가 필요하지 않다. 법령·조문번호 예외나 별도 감시 LLM을 추가하지 않았다.',
    '동일 작업 코드의 앞선 계약/API 검사195통과·기존 bounded fixture schema실패1건. 해당 실패는 ADR1015 코드·pin에서도 재현했다. 신규 범위 검사8개·API8경로 통과. 검증 원본은 09_ARTIFACTS/AUDITS/20261023-final-connection-selection.',
    '수정 전/후 각443파일을 동결했고 모델 실행 뒤 hash 일치를 확인했다. 실험 중 작업 코드·선택 MAIN102·GENOS 변경 없음. 현재 작업 코드 수정과 선택 릴리스는 별도 상태다.',
    '재실행은 새 ADR에서 예산·제공자 가용성·동일 조건을 다시 사전 고정해야 한다. 이번 실패 기록과 동결 후보는 덮어쓰지 않는다.'
]
(ADR/'RESULT.txt').write_text('\n\n'.join(findings)+'\n')
runtime=P/'runtime';archive=P/'runtime.tar.gz'
assert runtime.exists() and not archive.exists()
hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
with tarfile.open(archive,'r:gz') as t:
    for name,digest in hashes.items():
        with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==digest
save(P/'runtime-archive.json',{'archive':'runtime.tar.gz','sha256':sha(archive),'verified_files':hashes,
    'restore':'Extract archive into an empty directory; relative paths preserved.','process_finished':True})
shutil.rmtree(runtime)
m=read(ADR/'실험/manifest.json');assert m['design']==f['design']
m['runs'][0].update(arm_ids=['candidate','control'],status='complete',sha256=sha(ART/'result.json'),
    execution_note='Measurement complete; product request failed with provider429. Control skipped by preregistered stop policy.')
m['results'].update(status='complete',by_arm={
    'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'accuracy_not_scored_reason':'Historical ADR1015 only; no new execution.','new_calls':0},
    'control':{'status':'complete','correct':None,'total':0,'accuracy':None,'accuracy_not_scored_reason':'Not executed: preregistered provider stop after candidate429.','new_calls':0,'execution_status':'skipped'},
    'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'Provider429 before selection, no final answer or approved gold.','new_calls':2,'execution_status':'provider_failed'}},
    comparisons=[],judge_disagreements=0,usage={'physical_calls':2,**o['usage'],'failed_call_usage_reported':False},
    latency={'service_seconds':r['seconds'],'model_seconds':model_seconds,'request_p50_seconds':r['seconds'],'request_p95_seconds':r['seconds'],'sample_size':1},
    error_taxonomy=['PROVIDER_RATE_LIMIT_429','PAIRED_COMPARISON_UNAVAILABLE'])
nr=len(o['read_coordinates']);nf=len(o['final_coordinates'])
m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter=nr,after_filter=nf,
    presented_total={'candidate':nf},presented_mean={'candidate':nf},presented_p50={'candidate':nf},presented_p95={'candidate':nf},
    golden_recall={'candidate':None},selectivity={'candidate':nf/o['corpus_total']})
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
for key in ('presented_total','presented_mean','presented_p50','presented_p95','selectivity'):
    m['retrieval_accounting'][key]['control']=0
m['retrieval_accounting']['golden_recall']['control']=None
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[findings[0],findings[5],m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
    m['design']['sampling']+'\n\n실행 순서는 candidate→control이며 sampling의 baseline은 실행 control을 의미한다. 역사 baseline은 호출하지 않는다. 두 비교 arm 모두14회·재시도0·벽시계1800초로 동결했다.',
    'Qwen3.8 / qwen/qwen3.8-27b, OpenRouter Parasail FP8, reasoning none, fallback 없음. 코드443파일/arm, 같은 요청·데이터·프로필. [동결](artifacts/design-freeze.json), [호출 전 메타 교정 이력](artifacts/preregistration-correction.json).',
    '\n\n'.join(findings[2:5]),findings[6]+'\n\n'+findings[0],
    json.dumps({'successful_call_usage':o['usage'],'failed_call_usage':'unavailable','physical_calls':2,'service_seconds':r['seconds'],'model_seconds':model_seconds,'source_evidence_count':21,'read_article_roots':nr,'final_cited_roots':nf,'corpus_total':o['corpus_total']},ensure_ascii=False,indent=2)+'\n\n[단계 원장](artifacts/retrieval-ledger.json): original_read→final_cited. 최종 제시 수0은 제공자 중단의 결과이며 원문 부재나 검색 적합도 판정이 아니다.',
    findings[4], '\n\n'.join(summary['limitations']), findings[7]+'\n\n'+findings[8],
    '실행 원본: `06_TOOLS/EXPERIMENTS/adr_1016/guard.py` → `full_query.py`. 이 디렉터리에서 재호출하지 않는다. 상태·실패 로그는 보존한다. 오프라인 분석은 runtime-archive.json에 따라 별도 폴더로 복원 후 수행한다.\n\n최종 검사: `.venv/bin/python -B 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1016-final-selected-connection-scope --final` 및 `graph --adr-root 04_EXPERIMENTS/ADR`.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 최종 선택 범위 연결의 실제 질문 비교\n\n'+''.join(h+'\n\n'+x+'\n\n' for h,x in zip(ADR_HEADINGS,parts)))
for row in m['questions']:
    vals=['run-001/candidate; actual request attempted once. control skipped on provider error.',read(ART/'known-request.json')['json']['question'],
        'No approved answer gold. Source integrity and execution audit only; article97/163 are observed targets, not forced product actions.',
        '[Exact request](../artifacts/known-request.json), [frozen binding](../artifacts/known-query/candidate/execution-binding.json), [exact provider request bytes](../artifacts/known-query/candidate/model/).',
        '[Ledger](../artifacts/retrieval-ledger.json); original_read→final_cited. No final citation after provider failure.',
        '[All input/output files](../artifacts/known-query/candidate/model/), [compact audit](../artifacts/known-query/candidate/calls-audit.json), [native failed response](../artifacts/known-query/candidate/response.json).',
        'request-entry successful, source-law-navigation-1-read-choice provider429; no further calls, retry, repair, monitor or judge.',
        'No model judge; source/hash/ACL/usage checks only.', '\n\n'.join(findings[2:5])]
    qp=ADR/'실험'/row['file'];qp.write_text('# '+row['case_id']+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));row['sha256']=sha(qp)
save(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실행 질문\n\n- [known-query](질문-001-known-query.md): 제공자429, 실제2회 호출, 행동 비교 불가.\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=index.read_text();line='- [ADR-1016 최종 선택 범위 연결](ADR-1016-final-selected-connection-scope/README.md) — 실제2호출, 두 번째 제공자429, 선택 전 입력 확인, 선택 후 행동 비교 불가.\n'
assert 'ADR-1016-final-selected-connection-scope/README.md' not in txt
index.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n'+line))
print(json.dumps(summary,ensure_ascii=False,indent=2))
