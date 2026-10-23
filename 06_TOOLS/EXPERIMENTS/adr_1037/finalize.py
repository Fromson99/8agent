"""Offline report and lossless runtime archive after verification/integration."""
from common import *
import sys, tarfile, shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS, QUESTION_HEADINGS_V4
s=read(ART/'stage.json'); f=read(ART/'design-freeze.json'); m=read(ADR/'실험/manifest.json')
r=read(ART/'manual-review.json'); o=read(ART/'observations.json')['by_arm']['candidate']; P=ART/'known-query/candidate'
assert (ART/'guard-result.json').exists()
assert '18 passed' in (ART/'candidate-contracts.txt').read_text()
assert read(ART/'output-policy-review.json')['all_requests_uncapped']
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['root']/n)==h and sha(ROOT/n)==h for n,h in f['files']['candidate'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
physical=[json.loads(l) for l in (P/'physical-calls.jsonl').read_text().splitlines()]
count=len(physical); reported=len(o['native_result'].get('usage',[])); complete=reported==count
runtime=P/'runtime'; archive=P/'runtime.tar.gz'
assert runtime.exists() and not archive.exists()
hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
with tarfile.open(archive,'r:gz') as t:
    for name,h in hashes.items():
        with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h
save(P/'runtime-archive.json',{'sha256':sha(archive),'verified_files':hashes,'process_finished':True,
    'restore':'Extract runtime.tar.gz into an empty directory and verify recorded file hashes before inspection.'})
shutil.rmtree(runtime)
summary={'status':'COMPLETE','verdict':r['verdict'],'criteria_met':r['criteria_met'],
    'by_arm':{'candidate':{'service_status':o['service_status'],'physical_calls':count,'outcome':o['outcome'],'source_checks':o['source_checks']}},
    'reported_usage':o['usage'],'usage_complete':complete,'usage_reporting_calls':reported,'service_seconds':o['native_result']['seconds'],
    'guard':read(ART/'guard-result.json'),'quality_certified':False,'decision_eligible':False,
    'main_changed':False,'genos_changed':False,'working_product_changed':False,
    'inherited_tests':s['inherited_tests'],'new_tests_run':18,'limitations':r['limitations']}
save(ART/'result.json',summary)
assert m['design']==f['design']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),executed_arm_ids=['candidate'],skipped_arm_ids=[])
m['results'].update(status='complete',by_arm={
    'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'accuracy_not_scored_reason':'Completed parent ADR1036 capped output/final review/provider failure; unpaired, no fresh baseline calls.'},
    'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'Exposed question, no approved legal gold; operational/source audit only.','new_calls':count}},
    comparisons=[],judge_disagreements=0,usage={'physical_calls':count,'reported_calls':reported,'complete':complete,**o['usage']},
    latency={'service_seconds':o['native_result']['seconds'],'sample_size':1,'p50':o['native_result']['seconds'],'p95':o['native_result']['seconds']},error_taxonomy=r['error_taxonomy'])
n=len(o['final_coordinates']); corpus=o['corpus_total']
m['retrieval_accounting'].update(corpus_total=corpus,before_filter={'candidate':len(o['read_coordinates'])},after_filter={'candidate':n})
for k in ('presented_total','presented_mean','presented_p50','presented_p95'):m['retrieval_accounting'][k]={'candidate':n}
m['retrieval_accounting']['golden_recall']={'candidate':None}; m['retrieval_accounting']['selectivity']={'candidate':n/corpus if corpus else 0}
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[r['verdict'],
    'ADR1036에서 READ 제안이6400토큰 상한으로2회 미완료되고 최종 검토 실패 뒤429로 종료됐다. 사용자 요청으로 출력 상한을 작업 코드·MAIN103에서 제거한 뒤 동일 질문을 재실행했다.',
    m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
    'Qwen3.8 / qwen/qwen3.8-27b, Parasail FP8 only, reasoning none, no fallback. 후보513파일·질문·동일 공개 데이터·14호출/1800초 한도와 max_output_tokens=null을 호출 전에 동결했다. read_judgment=true, answer_progress_control=false, answer_first=false. [동결](artifacts/design-freeze.json).',
    '\n\n'.join(r['findings']),
    '[호출 경로](artifacts/execution-review.json), [판단 누적](artifacts/judgment-review.json), [복구 원장](artifacts/recovery-review.json), [원문 검사](artifacts/known-query/candidate/source-audit.json), [모델 원시 입출력](artifacts/known-query/candidate/model/).',
    json.dumps({'physical_calls':count,'usage':o['usage'],'usage_complete':complete,'seconds':o['native_result']['seconds'],'read_coordinates':len(o['read_coordinates']),'final_cited':n},ensure_ascii=False)+'\n\n출력 상한 제거의 선행 작업58검사·MAIN56검사 기록을 연결했고, 이번 격리 후보로 신규18계약/API검사 통과를 확인했다. 실제 모델 품질과 구분한다. [동일 코드·부모 검사](artifacts/stage.json). 승인된 정답 gold가 없어 정답률은 미채점이며 단일 질문 관찰이다.',
    r['interpretation'],'\n\n'.join(r['limitations']),
    '제품 코드 추가 변경 없이 현행 작업513파일을 격리했다. 부모1036과31개 출력 정책/어댑터/프로필/pin 파일이 다르다. 공통 외부클라이언트도 상한 제거 버전으로 해시 고정했다. 이번 실행에서 작업 코드·선택 MAIN103 포인터·GENOS를 변경하지 않았다. 실험 runtime만 분리하고 실패·원시 응답·출처 기록을 보존했다.',
    '실행: `.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1037/guard.py`. 완료 실행 덮어쓰기·자동 재실행 금지. runtime은 해시 검증 후 무손실 압축했다. 최종 validate와 graph를 확인한 뒤 reservation을 완료한다. 기존 전역 graph9오류는 별도 기록한다.']
assert len(parts)==len(ADR_HEADINGS)
(ADR/'README.md').write_text('---'+front+'---\n\n# 출력 상한 제거 후 동일 질문 재실험\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
(ADR/'RESULT.txt').write_text(r['verdict']+'\n\n'+'\n\n'.join(r['findings']+r['limitations'])+'\n\n이번 실행에서 작업 코드·MAIN103·GENOS 변경 없음. 동결한 현행 작업513파일과 동일하며 부모1036 대비31개 상한 제거 관련 변경은 사전에 명시했다.\n')
for row in m['questions']:
    assert row['case_id']=='known-query'
    vals=['run-001 / candidate. ADR1036 capped failed historical baseline only; no new capped calls.',read(ART/'known-request.json')['json']['question'],
        'Approved answer gold unavailable. No judge calls. Target reach is an execution observation, not legal truth.',
        '[Exact request](../artifacts/known-request.json) and [provider payloads](../artifacts/known-query/candidate/model/).',
        '[Retrieval ledger](../artifacts/retrieval-ledger.json): original_read → final_cited. Canonical coordinates; no gold given to product.',
        '[Exact provider requests/responses](../artifacts/known-query/candidate/model/). Raw inputs retained once.',
        '[Physical calls](../artifacts/known-query/candidate/physical-calls.jsonl), [execution audit](../artifacts/execution-review.json).',
        'Offline source/hash/authorization and execution audit. No legal correctness score.','\n\n'.join(r['findings'])]
    assert len(vals)==len(QUESTION_HEADINGS_V4)
    p=ADR/'실험'/row['file'];p.write_text('# '+row['case_id']+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));row['sha256']=sha(p)
save(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실행 질문\n\n'+''.join('- ['+row['case_id']+']('+row['file']+'): '+r['verdict']+'\n' for row in m['questions']))
p=ROOT/'04_EXPERIMENTS/ADR/README.md'; old=p.read_text();link='ADR-1037-uncapped-judgment-live-question/README.md';assert link not in old
p.write_text(old.replace('# ADR workspace\n','# ADR workspace\n- [ADR1036 출력 상한 제거 재실험]('+link+') — '+r['verdict']+'.\n'))
print(json.dumps({'verdict':r['verdict'],'calls':count,'criteria_met':r['criteria_met']},ensure_ascii=False))
