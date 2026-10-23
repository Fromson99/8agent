"""Finalize measured outcomes and a separate offline review, without new model calls."""
from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
assert (ART/'guard-result.json').exists()
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');obs=read(ART/'observations.json');review=read(ART/'manual-review.json')
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
integration=read(ART/'working-integration.json')
assert integration['main_unchanged']
assert all(sha(ROOT/n)==x['after'] for n,x in integration['changed_files'].items())
assert obs['main_unchanged']
for arm,files in f['files'].items():
    assert all(sha(ROOT/s['roots'][arm]/n)==h for n,h in files.items())
rows={};usage={k:0 for k in ('input_tokens','output_tokens','cost_usd')};calls=0;seconds=0;model_seconds=0
for arm,o in obs['by_arm'].items():
    P=ART/'known-query'/arm;r=o['native_result']
    physical=[json.loads(line) for line in (P/'physical-calls.jsonl').read_text().splitlines()]
    elapsed=sum(x['seconds'] for x in physical)
    rows[arm]={'service_status':o['service_status'],'physical_calls':r['model_calls'],
        'returned_calls':sum(x['status']=='returned' for x in physical),'call_phases':physical,
        'service_seconds':r['seconds'],'model_attempt_seconds':elapsed,'non_model_seconds':r['seconds']-elapsed,
        'reported_usage':o['usage'],'source_checks':o['source_checks'],'outcome':o['outcome'],
        'scope_selection_count':o['scope_selection_count'],'catalog_count':o['catalog_count'],
        'catalog_scope_violations':o['catalog_scope_violations'],'preselection_catalog_count':o['preselection_catalog_count'],
        'observed97':bool(o['observed_targets']['소득세법']),'observed163':bool(o['observed_targets']['소득세법 시행령'])}
    calls+=r['model_calls'];seconds+=r['seconds'];model_seconds+=elapsed
    for k in usage:usage[k]+=o['usage'][k]
    runtime=P/'runtime';archive=P/'runtime.tar.gz'
    assert runtime.exists() and not archive.exists()
    hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
    with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
    with tarfile.open(archive,'r:gz') as t:
        for name,digest in hashes.items():
            with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==digest
    save(P/'runtime-archive.json',{'archive':'runtime.tar.gz','sha256':sha(archive),'verified_files':hashes,
        'restore':'Extract archive into an empty directory; original relative paths preserved.','process_finished':True})
    shutil.rmtree(runtime)
summary={'status':'COMPLETE','verdict':review['verdict'],'criteria_met':review['criteria_met'],
    'by_arm':rows,'physical_calls':calls,'reported_usage':usage,'service_seconds':seconds,
    'model_attempt_seconds':model_seconds,'guard':read(ART/'guard-result.json'),
    'quality_certified':False,'decision_eligible':False,'main_changed':False,'genos_changed':False,
    'working_integration':integration,'deterministic_verification':read(ART/'regression-review.json'),'limitations':review['limitations']}
save(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json');assert m['design']==f['design']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),executed_arm_ids=list(rows),skipped_arm_ids=[x for x in s['arm_order'] if x not in rows])
by_arm={'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'accuracy_not_scored_reason':'Historical ADR1017 recorded inputs and catalog; no new baseline calls.','new_calls':0}}
for arm in s['arm_order']:
    by_arm[arm]={'status':'complete','correct':None,'total':int(arm in rows),'accuracy':None,
        'accuracy_not_scored_reason': 'No approved legal-answer gold; see offline operational audit.' if arm in rows else 'Not executed due to preregistered preceding-arm stop.',
        'new_calls':rows.get(arm,{}).get('physical_calls',0),'execution_status':'executed' if arm in rows else 'skipped'}
m['results'].update(status='complete',by_arm=by_arm,comparisons=review.get('comparisons',[]),judge_disagreements=0,
    usage={'physical_calls':calls,**usage,'provider_failed_usage':'not reported when missing'},
    latency={'service_seconds':seconds,'model_seconds':model_seconds,'sample_size':len(rows)},error_taxonomy=review['error_taxonomy'])
m['retrieval_accounting'].update(corpus_total=next(iter(obs['by_arm'].values()))['corpus_total'],
    before_filter={a:len(obs['by_arm'].get(a,{}).get('read_coordinates',[])) for a in s['arm_order']},
    after_filter={a:len(obs['by_arm'].get(a,{}).get('final_coordinates',[])) for a in s['arm_order']})
for key in ('presented_total','presented_mean','presented_p50','presented_p95'):
    m['retrieval_accounting'][key]=m['retrieval_accounting']['after_filter'].copy()
m['retrieval_accounting']['golden_recall']={a:None for a in s['arm_order']}
m['retrieval_accounting']['selectivity']={a:n/m['retrieval_accounting']['corpus_total'] for a,n in m['retrieval_accounting']['after_filter'].items()}
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
findings=review['findings']
(ADR/'RESULT.txt').write_text('\n\n'.join(findings+review['limitations'])+'\n')
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[review['verdict']+'; quality_certified=false / MAIN unchanged.',
    '이전 실행에서 선택한97조의 연결29개 중2개만 모델에 전달되어 뒤쪽163조가 보이지 않았다. 모든 연결을 간결한 목록으로 제시하고 필요한 원문만 선택하도록 변경했다.',
    m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
    m['design']['sampling']+'\n\n각 arm 최대14회·재시도0·1800초. 제공자 실패 시 남은 arm 중단.',
    '수정 후보494파일을 동결했다. 비교는 이전 기록이며 새 대조군 모델 호출은 없다. Qwen3.8 / qwen/qwen3.8-27b, OpenRouter Parasail FP8 only, reasoning none, no fallback. [동결](artifacts/design-freeze.json).',
    '\n\n'.join(findings), '[실제 호출·선택·원문 검증](artifacts/observations.json), [오프라인 판정](artifacts/manual-review.json).',
    json.dumps({'physical_calls':calls,'reported_usage':usage,'service_seconds':seconds,'model_seconds':model_seconds,'corpus':m['retrieval_accounting']['corpus_total'],'read':m['retrieval_accounting']['before_filter'],'final_cited':m['retrieval_accounting']['after_filter']},ensure_ascii=False,indent=2)+'\n\n[회수 단계 원장](artifacts/retrieval-ledger.json). 실행하지 않은 arm은 executed=false로 기록한다.',
    review['interpretation'], '\n\n'.join(review['limitations']),
    '검증한2개 제품 모듈과4개 회귀 검사 및 테스트 디코더만 작업 코드에 통합하고 엔진 지문을 갱신했다. 동결 후보와 변경 파일 해시 일치. 선택 MAIN102와 GENOS는 변경하지 않았다. working-integration.json에 백업·복원 경로를 보존한다.',
    '실제 실행: `06_TOOLS/EXPERIMENTS/adr_1018/guard.py` → `full_query.py`. 원본 호출 디렉터리는 재사용하지 않는다. runtime-archive.json의 해시와 복원 방법으로 원시 저널을 복구한다. 최종 검사: `adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1018-complete-connection-directory --final`, `graph --adr-root 04_EXPERIMENTS/ADR`.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 최종 선택 범위의 전체 연결 목록과 입력 중복 축소\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
for row in m['questions']:
    vals=['run-001; executed: '+', '.join(rows),read(ART/'known-request.json')['json']['question'],
        'No approved answer gold. Source integrity and execution audit only;97/163 are descriptive observed targets.',
        '[Exact request](../artifacts/known-request.json); per-arm exact provider input and output under [known-query](../artifacts/known-query/).',
        '[Ledger](../artifacts/retrieval-ledger.json): original_read→final_cited, skipped stages explicitly marked.',
        '[Actual raw requests/responses](../artifacts/known-query/), [native observations](../artifacts/observations.json).',
        'Each physical call and phase is preserved in physical-calls.jsonl and model/call-* per executed arm. No extra monitor or judge.',
        'Offline source/hash/ACL/usage audit and manual operational review only; no legal accuracy certification.',
        '\n\n'.join(findings)]
    qp=ADR/'실험'/row['file'];qp.write_text('# '+row['case_id']+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));row['sha256']=sha(qp)
save(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실행 질문\n\n- [known-query](질문-001-known-query.md): '+review['verdict']+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=index.read_text();link='ADR-1018-complete-connection-directory/README.md'
assert link not in txt
index.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n- [ADR-1018 전체 연결 목록·입력 중복 축소]('+link+') — '+review['verdict']+'.\n'))
print(json.dumps({'verdict':summary['verdict'],'physical_calls':calls,'executed_arms':list(rows),'reported_usage':usage},ensure_ascii=False))
