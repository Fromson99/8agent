"""Offline report only. Native run/criteria are immutable; no model calls."""
from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');m=read(ADR/'실험/manifest.json')
review=read(ART/'manual-review.json');o=read(ART/'observations.json')['by_arm']['candidate'];P=ART/'known-query/candidate'
assert (ART/'guard-result.json').exists()
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert all(sha(ROOT/n)==h for n,h in s['working_before'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
physical=[json.loads(l) for l in (P/'physical-calls.jsonl').read_text().splitlines()];count=len(physical)
reported=len(o['native_result'].get('usage',[]));complete=reported==count
summary={'status':'COMPLETE','verdict':review['verdict'],'criteria_met':review['criteria_met'],
 'by_arm':{'candidate':{'service_status':o['service_status'],'physical_calls':count,'reference_model_calls':review['reference_model_calls'],'outcome':o['outcome'],'source_checks':o['source_checks']}},
 'reported_usage':o['usage'],'usage_complete':complete,'usage_reporting_calls':reported,'service_seconds':o['native_result']['seconds'],
 'guard':read(ART/'guard-result.json'),'quality_certified':False,'decision_eligible':False,'main_changed':False,'genos_changed':False,'working_product_changed':False,'limitations':review['limitations']}
runtime=P/'runtime';archive=P/'runtime.tar.gz'
assert runtime.exists() and not archive.exists()
hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
with tarfile.open(archive,'r:gz') as t:
 for name,h in hashes.items():
  with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h
save(P/'runtime-archive.json',{'sha256':sha(archive),'verified_files':hashes,'process_finished':True,'restore':'Extract runtime.tar.gz into an empty directory and verify the recorded hashes before inspection.'})
shutil.rmtree(runtime)
save(ART/'result.json',summary)
assert m['design']==f['design']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),executed_arm_ids=['candidate'],skipped_arm_ids=[])
m['results'].update(status='complete',by_arm={
 'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'accuracy_not_scored_reason':'Complete ADR1033 contract-only baseline; no new control model calls.'},
 'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'Known exposed question; no approved legal answer gold. Operational/source audit only.','new_calls':count}},
 comparisons=[],judge_disagreements=0,usage={'physical_calls':count,'reported_calls':reported,'complete':complete,**o['usage']},
 latency={'service_seconds':o['native_result']['seconds'],'sample_size':1,'p50':o['native_result']['seconds'],'p95':o['native_result']['seconds']},error_taxonomy=review['error_taxonomy'])
n=len(o['final_coordinates']);corpus=o['corpus_total']
m['retrieval_accounting'].update(corpus_total=corpus,before_filter={'candidate':len(o['read_coordinates'])},after_filter={'candidate':n})
for k in ('presented_total','presented_mean','presented_p50','presented_p95'):m['retrieval_accounting'][k]={'candidate':n}
m['retrieval_accounting']['golden_recall']={'candidate':None};m['retrieval_accounting']['selectivity']={'candidate':n/corpus if corpus else 0}
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[review['verdict'],
 'ADR1033에서 원문별 판단·이유·부족·행동 연결과 누적 판단의 최종 검토를 구현했다. 같은 실제 질문으로 판단 보존·누락·반복·답변을 확인한다.',
 m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
 'Qwen3.8 / qwen/qwen3.8-27b, Parasail FP8 only, reasoning none, no fallback. ADR1033과 현재 작업 코드가 동일한511파일·기존 데이터·질문·14호출 한도를 사전 동결했다. read_judgment=true, answer_progress_control 기본false, answer_first=false다. ADR1032는 이전 실행의 참고 기록이며 동시 대조군이 아니다. [동결](artifacts/design-freeze.json).',
 '\n\n'.join(review['findings']),
 '[호출 경로](artifacts/execution-review.json), [판단 누적 검사](artifacts/judgment-review.json), [원문 검사](artifacts/known-query/candidate/source-audit.json), [모델 원시 입출력](artifacts/known-query/candidate/model/).',
 json.dumps({'physical_calls':count,'usage':o['usage'],'usage_complete':complete,'seconds':o['native_result']['seconds'],'corpus':corpus,'read_coordinates':len(o['read_coordinates']),'final_cited':n},ensure_ascii=False)+'\n\n[단계 원장](artifacts/retrieval-ledger.json). 현재 질문은 승인된 정답 gold가 없어 recall/정답률은 미채점이며 p50/p95는 단일 표본이다.',
 review['interpretation'],'\n\n'.join(review['limitations']),
 '제품 수정 없이 현재 작업 코드와 동일한 ADR1034 격리 후보를 실행했다. 작업511파일·선택 MAIN102 포인터 해시 불변, GENOS 미변경. 판단·최종 검토 감사를 judgment-review.json에 보존했다.',
 '실행: `.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1034/guard.py`. 완료 실행 덮어쓰기·자동 재실행 금지. runtime은 무손실 압축과 파일 해시로 보존했다. `06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1034-read-judgment-live-question --final`, `graph --adr-root 04_EXPERIMENTS/ADR`로 검사한다.']
assert len(parts)==len(ADR_HEADINGS)
(ADR/'README.md').write_text('---'+front+'---\n\n# 읽기 판단 누적 실제 질문 실험\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
(ADR/'RESULT.txt').write_text(review['verdict']+'\n\n'+'\n\n'.join(review['findings']+review['limitations'])+'\n')
for r in m['questions']:
 vals=['run-001 / candidate. ADR1033 implementation baseline; ADR1032 historical unpaired context only.',read(ART/'known-request.json')['json']['question'],
 'Approved answer gold unavailable. No judge calls. Target reach is an execution observation, not legal truth.',
 '[Exact request](../artifacts/known-request.json) and [provider payloads](../artifacts/known-query/candidate/model/).',
 '[Retrieval ledger](../artifacts/retrieval-ledger.json): original_read → final_cited. Canonical coordinates; no gold given to product.',
 '[Exact provider requests/responses](../artifacts/known-query/candidate/model/). Large raw inputs retained once; reports link rather than duplicate them.',
 '[Physical calls](../artifacts/known-query/candidate/physical-calls.jsonl), [execution audit](../artifacts/execution-review.json).',
 'Offline source/hash/authorization and execution audit. No legal correctness score.','\n\n'.join(review['findings'])]
 assert len(vals)==len(QUESTION_HEADINGS_V4)
 p=ADR/'실험'/r['file'];p.write_text('# '+r['case_id']+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));r['sha256']=sha(p)
save(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실행 질문\n\n'+''.join('- ['+r['case_id']+']('+r['file']+'): '+review['verdict']+'\n' for r in m['questions']))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';text=p.read_text();link='ADR-1034-read-judgment-live-question/README.md';assert link not in text
p.write_text(text.replace('# ADR workspace\n','# ADR workspace\n- [ADR1034 읽기 판단 누적 실제 질문]('+link+') — '+review['verdict']+'.\n'))
print(json.dumps({'verdict':review['verdict'],'calls':count,'status':o['service_status'],'criteria_met':review['criteria_met']},ensure_ascii=False))
