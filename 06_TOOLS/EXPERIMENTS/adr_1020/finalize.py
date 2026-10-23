from common import *
import sys,tarfile,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');obs=read(ART/'observations.json');o=obs['by_arm']['candidate'];P=ART/'known-query/candidate'
assert (ART/'guard-result.json').exists()
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
physical=[json.loads(l) for l in (P/'physical-calls.jsonl').read_text().splitlines()]
response=read(P/'response.json');body=response.get('body',{});answer=body.get('answer',{});meta=body.get('assembly',{}).get('term_agent',{})
actual_calls=len(physical);nested=sum(c['phase'].startswith('source-reference-') for c in physical)
claims=answer.get('claims',[]);bounded=bool(answer.get('source_excerpt_reply'))
checks=o['source_checks'];criteria=o['service_status']==200 and nested==0 and actual_calls<=14 and checks['mismatches']==0 and checks['scope_violations']==0
criteria=False  # Completed answer, but observed frontier loss/re-expansion and higher cost remain.
verdict=('답변 출력 복구·탐색 비용 개선 실패' if claims else '원문 제한 응답으로 종료' if bounded else '실제 질문 실패')+'; 법률 정답 인증 아님'
findings=['이전12회/입력437016토큰/비용0.13592032달러에서 이번13회/입력890807토큰/비용0.22277276달러로 증가했다. 연결 전용 호출은 사라졌지만 총 비용 개선은 실패했다.', '추가 원문을 읽어 선택 가능한 범위의 span 집합이 변하면 이전 선택 범위 ID가 새 후보 목록에서 사라져 연결 카드가 빈 목록이 되는 결함을 확인했다. 최종 종료도 충분성만으로 끝난 것이 아니라 INVESTIGATION_BUDGET 제한을 포함했다.', f"동결 후보497파일; 모의 API·권한·원문·재개·연결 검사110개 통과.",
 f"실제 질문: {read(ART/'known-request.json')['json']['question']}",
 f"실제 호출 {actual_calls}회, 연결 전용 모델 호출 {nested}회. 이전 ADR1018은12회(연결전용2회); 다른 시점의 단일 실행 비교다.",
 f"서비스 상태{o['service_status']}, 법률 주장{len(claims)}개, 최종 coverage={meta.get('answer_coverage')}, source-only={bounded}.",
 f"원문 검증{checks['count']}건, 불일치{checks['mismatches']}·권한 위반{checks['scope_violations']}.",
 f"소득세법97조 원문 확보={bool(o['observed_targets']['소득세법'])}; 시행령163조 원문 확보={bool(o['observed_targets']['소득세법 시행령'])}.",
 '출력 한도에 걸린 검토는 재호출하지 않는다. 실패 제안은 REJECTED로 유지하고 확정하지 않은 주장 대신 검증된 원문만 반환한다. 다른 스키마 오류는 기존1회 보정을 유지한다.',
 '최종 선택 범위의 모든 검증된 연결을 부모 읽기 선택에 전달하며 미선택 링크를 SKIP으로 만들어내지 않는다. 재조회 없이 읽은 상태를 함께 표시한다.']
limitations=['알려진 질문1개와 합성 회귀 검사이며 일반화·법률 정답을 인증하지 않는다. 이전 기록과 현재 실행은 시간 차이가 있는 비동시 비교다.',
 '색인 자체의 스캔 한도와 요청 문맥 한도는 유지한다. 범위 밖 연결을 강제로 읽거나163조 번호를 제품 규칙에 추가하지 않았다.',
 '로컬 작업 코드에 반영했으며 선택 MAIN102와 GENOS 현장 배포는 변경하지 않았다.',
 '다른 작업이 Oracle 조회 모듈을 수정 중이다. 작업 코드 전체 엔진 지문 상태는 working-final-check.json에 별도 보존한다. 후보의 검증 코드·데이터 지문은 모두 고정했다.']
review={'verdict':verdict,'criteria_met':criteria,'findings':findings,'limitations':limitations,
 'legal_correctness':None,'interpretation':'불필요한 연결용 판단 단계를 제거하고 출력 한도 실패를 유한한 원문 응답으로 처리했다. 실제 질의의 내용·호출 경로는 원시 로그와 별도 검토를 확인한다.',
 'comparisons':[],'error_taxonomy':[] if o['service_status']==200 else [{'type':'other','count':1,'total':1,'detail':'Native service did not publish a completed response.'}]}
save(ART/'manual-review.json',review)
summary={'status':'COMPLETE','verdict':verdict,'criteria_met':criteria,'by_arm':{'candidate':{'service_status':o['service_status'],'physical_calls':actual_calls,'reference_model_calls':nested,'claims':len(claims),'source_only':bounded,'outcome':o['outcome'],'source_checks':checks}},
 'reported_usage':o['usage'],'service_seconds':o['native_result']['seconds'],'call_phases':physical,'guard':read(ART/'guard-result.json'),
 'quality_certified':False,'decision_eligible':False,'main_changed':False,'genos_changed':False,'working_integration':read(ART/'working-integration.json'),'limitations':limitations}
# Archive only this finished request's runtime and verify every byte before removing the work copy.
runtime=P/'runtime';archive=P/'runtime.tar.gz'
assert runtime.exists() and not archive.exists()
hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
with tarfile.open(archive,'r:gz') as t:
 for name,h in hashes.items():
  with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h
save(P/'runtime-archive.json',{'sha256':sha(archive),'verified_files':hashes,'process_finished':True,'restore':'Extract runtime.tar.gz into an empty directory; verify hashes before replay.'})
shutil.rmtree(runtime)
save(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json');assert m['design']==f['design']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),executed_arm_ids=['candidate'],skipped_arm_ids=[])
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'accuracy_not_scored_reason':'Historical ADR1018 native outcome, no new calls.'},'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'No approved answer gold; operational and source audit only.','new_calls':actual_calls}},comparisons=[],judge_disagreements=0,
 usage={'physical_calls':actual_calls,**o['usage']},latency={'service_seconds':o['native_result']['seconds'],'sample_size':1},error_taxonomy=review['error_taxonomy'])
m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter={'candidate':len(o['read_coordinates'])},after_filter={'candidate':len(o['final_coordinates'])})
for k in ('presented_total','presented_mean','presented_p50','presented_p95'):m['retrieval_accounting'][k]={'candidate':len(o['final_coordinates'])}
m['retrieval_accounting']['golden_recall']={'candidate':None};m['retrieval_accounting']['selectivity']={'candidate':len(o['final_coordinates'])/o['corpus_total']};m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[verdict,'ADR1018은 연결 메뉴에서 빈 판단2회 뒤 부모가 원문을 다시 선택했고, 최종 검토2회가 각6400토큰 반복 출력으로 실패했다.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
 'Qwen3.8 / qwen/qwen3.8-27b, Parasail FP8 only, reasoning none, no fallback. 후보497파일·모델·데이터 동결. [동결](artifacts/design-freeze.json). 동결 전 Oracle 병행 수정은 freeze-upstream-drift.json에 기록하고 검증한 후보 바이트를 그대로 보존했다.',
 '\n\n'.join(findings),'[원시 호출·원문 검증](artifacts/observations.json), [실제 답변](artifacts/known-query/candidate/answer.txt).',json.dumps({'calls':actual_calls,'usage':o['usage'],'seconds':o['native_result']['seconds'],'corpus':o['corpus_total'],'read':len(o['read_coordinates']),'final_cited':len(o['final_coordinates'])},ensure_ascii=False)+'\n\n[단계별 원장](artifacts/retrieval-ledger.json).',review['interpretation'],'\n\n'.join(limitations),
 '검증한 제품5모듈·검사4파일만 작업 코드에 통합했다. 별도 Oracle 변경을 덮어쓰지 않았다. working-integration.json에 백업과 복원 범위를 보존하며 MAIN102·GENOS는 그대로다.',
 '로컬 실행: `.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1020/guard.py`. 기존 산출물 재사용·덮어쓰기 금지. 원시 저널은 runtime-archive.json 해시로 복구한다. 검사: `adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1020-direct-connections-bounded-review --final` 및 `graph --adr-root 04_EXPERIMENTS/ADR`.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 연결 선택 호출 통합과 반복 검토의 제한 종료\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
(ADR/'RESULT.txt').write_text('\n\n'.join(findings+limitations)+'\n')
for r in m['questions']:
 vals=['run-001 / candidate; historical ADR1018 baseline.',read(ART/'known-request.json')['json']['question'],'Approved legal answer gold unavailable. No judge calls.',
 '[Exact request](../artifacts/known-request.json) and [model inputs](../artifacts/known-query/candidate/model/).',
 '[Retrieval ledger](../artifacts/retrieval-ledger.json): original_read → final_cited. Gold not provided to product.',
 '[Exact provider requests/responses](../artifacts/known-query/candidate/model/).',
 '[Every phase and physical call](../artifacts/known-query/candidate/physical-calls.jsonl).',
 'Offline exact source, ACL and operational audit only. No legal score.', '\n\n'.join(findings)]
 p=ADR/'실험'/r['file'];p.write_text('# '+r['case_id']+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));r['sha256']=sha(p)
save(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실행 질문\n\n- [known-query](질문-001-known-query.md): '+verdict+'\n')
p=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=p.read_text();link='ADR-1020-direct-connections-bounded-review/README.md'
assert link not in txt;p.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n- [ADR1020 연결 호출 통합·검토 제한 종료]('+link+') — '+verdict+'.\n'))
print(json.dumps({'verdict':verdict,'calls':actual_calls,'reference_calls':nested,'source_only':bounded,'claims':len(claims)},ensure_ascii=False))
