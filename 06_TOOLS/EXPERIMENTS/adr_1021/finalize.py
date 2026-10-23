from common import *
import sys, tarfile, shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS, QUESTION_HEADINGS_V4
s=read(ART/'stage.json'); f=read(ART/'design-freeze.json')
o=read(ART/'observations.json')['by_arm']['candidate']; P=ART/'known-query/candidate'
assert read(ART/'guard-result.json')['stop']['status_code']==429
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert all(sha(ROOT/s['roots']['candidate']/n)==h for n,h in f['files']['candidate'].items())
assert '89 passed' in (ART/'contracts-frozen.log').read_text()
assert '11 passed' in (ART/'working-api.log').read_text()
assert not read(ART/'working-final-check.json')['working_answer_progress_control']
physical=[json.loads(l) for l in (P/'physical-calls.jsonl').read_text().splitlines()]
calls=read(P/'calls-audit.json'); count=len(physical)
assert count==9 and o['service_status']==503
assert not o['observed_targets']['소득세법 시행령']
trace=[{'call':c['call'],'stage':c['source_stage'],
        'choice':c['proposal'].get('choice'),
        'connection_cards':len(c['references'].get('dependency_cards',[])),
        'progress_status':c['proposal'].get('answer_progress',{}).get('status'),
        'previous_effect':c['proposal'].get('answer_progress',{}).get('previous_effect'),
        'evidence':str((P/'model'/c['call']/'response.json').relative_to(ROOT))} for c in calls]
save(ART/'failure-path.json',{'call_trace':trace,
 'observed_chain':'97조①② 읽기 → 연결 범위 선택 없이 FINISH → 검토에서 근거 없는155조를 부족 대상으로 제시 →155조 조회 → 같은 선택 보정 → 검토429',
 'mechanical_scope_refresh':'Proven by deterministic tests; this native run made no connection-scope selection, so no native refresh execution is claimed.',
 'remaining_defects':['Connection cards remain unavailable before explicit FOLLOW_CONNECTION selection.',
 'Free-text assessment gap target can invent a locator and drive subsequent search.',
 'Invalid repeated READ validation/repair happens before answer-progress handoff.'],
 'legal_judgment':'This is an execution-path audit of the frozen corpus, not a current-law answer or gold certification.'})
verdict='범위 보존 회귀 통과; 종료 정책 실제 검증 실패·비활성 유지'
findings=[
 '선택한 구조 범위는 같은데 추가 원문으로 scope ID가 바뀌어 연결 카드가 사라지는 결함을 수정했다. 동일 구조·제외 범위이고 기존 원문 해시를 모두 보존한 확장일 때만 전달 상태를 갱신한다. 다른 항이나 조로 자동 확대하지 않는다.',
 '남은 조사 호출이2회일 때도 좁은 원문 선택 계약을 유지한다. 기존 총 예산·검토 예약은 늘리지 않았다.',
 '동결 후보498파일의 회귀·API 검사89개, 작업 코드 통합 후 검사11개 통과. 원문 추가·범위 변경·삭제·변조·잘못된 해시·예산·재개·중복·권한·표시 경로를 포함한다.',
 '실제 질문: '+read(ART/'known-request.json')['json']['question'],
 '실제 모델 호출9회 중 마지막 검토 호출이 제공자429로 실패해 서비스503으로 종료했다. 재시도·모델 fallback은 수행하지 않았다.',
 '호출3에서97조①②를 읽었고 호출4에서 연결 범위를 선택하지 않은 채 충분하다고 FINISH했다. 호출5 검토는 시행령 세부 원문이 필요하다고 판단하면서 근거 없는155조 번호를 제시했고, 다음 탐색이 이를 따라갔다. 시행령163조 원문은 이번 실행에서 확보하지 못했다.',
 '이번 원문 검증153건에서 해시/본문 불일치0·권한 위반0. 최종 법률 답변은 생성되지 않았다.',
 '보고된 입력396316토큰·출력3650토큰·비용0.09793224달러는 응답한8회의 합계다. 실패한9번째 호출의 사용량은 제공되지 않았다. 중단된 실패 실행이므로 이전13회보다 비용이 줄었다고 평가하지 않는다.',
 'answer_progress_control=true는 실제 종료 품질을 개선하지 못해 작업 코드에서는 false를 유지했다. 후보의 제품2모듈·검사4파일만 통합했으며 프로필은 제외했다.',
 '직전 ADR1020은 연결 전용 모델 판단을 제거하고 제한 답변을 생성했지만13회/입력890807토큰으로 총 탐색 비용 개선에 실패했다. 이번 범위 보존 수정의 실제 질의 비용 효과도 확인되지 않았다.'
]
limitations=[
 '알려진 질문1개이며 이전 실행과 시간 차이가 있는 비동시 비교다. 승인된 정답 골드·미사용 평가셋은 없고 법률 정답을 인증하지 않는다.',
 '합성 검사에서 확인한 범위 보존과 실제 모델의 적절한 종료는 별개다. 이번 실제 실행은 FOLLOW_CONNECTION을 선택하지 않아 범위 갱신 경로 자체를 밟지 않았다.',
 '97조만 보고 끝내는 문제, 근거 없는 부족 조항 번호, 중복 선택 보정의 추가 호출이 남아 있다. 특정163조를 강제로 읽는 규칙은 추가하지 않았다.',
 '작업 코드의 종료 프로필은 동결 실험 후보와 다르다(false 대 true). 통합 후 서비스 진입점은 모의 모델 검사로 검증했으며 이 조합의 실제 외부 모델 재실행은 하지 않았다.',
 '선택 MAIN102/활성 포인터와 GENOS 배포는 변경하지 않았다. 병행 Oracle 작업 파일은 덮어쓰지 않았다.'
]
review={'verdict':verdict,'criteria_met':False,'findings':findings,'limitations':limitations,
 'legal_correctness':None,'interpretation':'확정 가능한 범위·해시 보존 수정만 반영했다. 답변 진전 자기평가를 추가하는 것만으로 조기 종료·잘못된 재탐색을 해결하지 못했다.',
 'comparisons':[], 'error_taxonomy':[{'type':'other','count':1,'total':1,'detail':'Provider429 on final assessment; before that premature FINISH at97 and ungrounded155 locator. Native semantic success absent.'}]}
save(ART/'manual-review.json',review)
summary={'status':'COMPLETE','verdict':verdict,'criteria_met':False,
 'by_arm':{'candidate':{'service_status':503,'physical_calls':count,'reference_model_calls':0,
   'claims':0,'source_only':False,'outcome':o['outcome'],'source_checks':o['source_checks']}},
 'reported_usage':o['usage'],'usage_complete':False,'usage_reporting_calls':8,
 'service_seconds':o['native_result']['seconds'],'guard':read(ART/'guard-result.json'),
 'quality_certified':False,'decision_eligible':False,'main_changed':False,'genos_changed':False,
 'working_integration':read(ART/'working-integration.json'),'working_final_check':read(ART/'working-final-check.json'),
 'limitations':limitations}
# The guard has completed; archive only this request's disposable runtime after byte verification.
runtime=P/'runtime'; archive=P/'runtime.tar.gz'
assert runtime.exists() and not archive.exists()
hashes={str(p.relative_to(P)):sha(p) for p in runtime.rglob('*') if p.is_file()}
with tarfile.open(archive,'w:gz',compresslevel=6) as t:t.add(runtime,arcname='runtime')
with tarfile.open(archive,'r:gz') as t:
    for name,h in hashes.items():
        with t.extractfile(name) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h
save(P/'runtime-archive.json',{'sha256':sha(archive),'verified_files':hashes,'process_finished':True,
 'restore':'Extract runtime.tar.gz into an empty directory; verify hashes before replay.'})
shutil.rmtree(runtime)
save(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json'); assert m['design']==f['design']
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),executed_arm_ids=['candidate'],skipped_arm_ids=[])
m['results'].update(status='complete',by_arm={
 'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'accuracy_not_scored_reason':'Historical ADR1020 native outcome; no new control calls.'},
 'candidate':{'status':'complete','correct':None,'total':1,'accuracy':None,'accuracy_not_scored_reason':'Failed request; no approved legal answer gold. Operational and source audit only.','new_calls':count}},
 comparisons=[],judge_disagreements=0,usage={'physical_calls':count,'reported_calls':8,'complete':False,**o['usage']},
 latency={'service_seconds':o['native_result']['seconds'],'sample_size':1},error_taxonomy=review['error_taxonomy'])
m['retrieval_accounting'].update(corpus_total=o['corpus_total'],before_filter={'candidate':len(o['read_coordinates'])},after_filter={'candidate':0})
for k in ('presented_total','presented_mean','presented_p50','presented_p95'):m['retrieval_accounting'][k]={'candidate':0}
m['retrieval_accounting']['golden_recall']={'candidate':None};m['retrieval_accounting']['selectivity']={'candidate':0}
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[verdict,
 'ADR1020은 선택 범위 안에서 원문을 더 읽자 후보 scope ID가 바뀌어 연결 카드가 사라졌다. 답변은 생성했지만13호출·입력890807토큰이며 비용 개선에 실패했다.',
 m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],m['design']['sampling'],
 'Qwen3.8 / qwen/qwen3.8-27b, Parasail FP8 only, reasoning none, no fallback. 후보498파일·데이터·모델·질문·14호출 한도를 결과 전에 동결했다. [동결](artifacts/design-freeze.json).',
 '\n\n'.join(findings),
 '[실제 호출 감사](artifacts/known-query/candidate/calls-audit.json), [실패 경로](artifacts/failure-path.json), [모델 원시 입출력](artifacts/known-query/candidate/model/).',
 json.dumps({'physical_calls':count,'reported_usage':o['usage'],'usage_complete':False,'seconds':o['native_result']['seconds'],'corpus':o['corpus_total'],'read_coordinates':len(o['read_coordinates']),'final_cited':0},ensure_ascii=False)+'\n\n[단계 원장](artifacts/retrieval-ledger.json).',
 review['interpretation'],'\n\n'.join(limitations),
 '제품2모듈·검사4파일만 작업 코드에 통합했다. 실패한 answer_progress_control 설정은 제외했다. [통합·백업](artifacts/working-integration.json), [해시·설정 대조](artifacts/working-final-check.json). MAIN102와 GENOS는 그대로다.',
 '실행: `.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1021/guard.py`. 완료된 산출물 덮어쓰기·자동 재실행 금지. 원시 runtime은 해시를 검증한 runtime.tar.gz에 보존했다. `adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1021-retained-scope-answer-progress --final` 및 `graph --adr-root 04_EXPERIMENTS/ADR`로 검증한다.']
assert len(parts)==len(ADR_HEADINGS)
(ADR/'README.md').write_text('---'+front+'---\n\n# 선택한 연결 범위 보존과 답변 진전 종료 정책 실험\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
(ADR/'RESULT.txt').write_text(verdict+'\n\n'+'\n\n'.join(findings+limitations)+'\n')
for r in m['questions']:
    vals=['run-001 / candidate; historical ADR1020 baseline.',read(ART/'known-request.json')['json']['question'],
      'Approved answer gold unavailable. No judge calls.',
      '[Exact request](../artifacts/known-request.json) and [model inputs](../artifacts/known-query/candidate/model/).',
      '[Retrieval ledger](../artifacts/retrieval-ledger.json): original_read → final_cited. No answer gold given to product.',
      '[Exact provider requests/responses](../artifacts/known-query/candidate/model/).',
      '[Physical calls](../artifacts/known-query/candidate/physical-calls.jsonl), [failure path](../artifacts/failure-path.json).',
      'Offline exact source, ACL and execution-path audit only. Native request failed; no legal score.',
      '\n\n'.join(findings)]
    assert len(vals)==len(QUESTION_HEADINGS_V4)
    p=ADR/'실험'/r['file'];p.write_text('# '+r['case_id']+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,vals)));r['sha256']=sha(p)
save(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실행 질문\n\n- [known-query](질문-001-known-query.md): '+verdict+'\n')
p=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=p.read_text();link='ADR-1021-retained-scope-answer-progress/README.md'
assert link not in txt
p.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n- [ADR1021 연결 범위 보존·종료 정책 실험]('+link+') — '+verdict+'.\n'))
print(json.dumps({'verdict':verdict,'calls':count,'status':503,'criteria_met':False,'working_progress_control':False},ensure_ascii=False))
