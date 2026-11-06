from common import *

P=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1373*/artifacts'))
grade=read(ART/'semantic-review.json')
old=read(P/'run-001/result.json')
cases=read(ART/'usage-inspection.json')['rows']
conf=read(ART/'followup-conflict/result.json')
checks=read(ART/'working-service-check/result.json');work=read(ART/'working-integration.json')
assert all(sha(P/'sandbox-repository'/n)==h for n,h in read(DES/'parent-files.json').items())
assert all(sha(ROOT/n)==h for n,h in read(DES/'freeze.json')['files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer']
usage={'physical_calls':conf['physical_calls']+sum(c['physical_calls'] for c in cases),
       'unknown':conf['unknown']+sum(c['unknown'] for c in cases),
       'reported_cost_usd':conf['reported_cost_usd']+sum(c['reported_cost_usd'] for c in cases)}
summary={'followup':grade,'conflict':conf,'explicit_use':cases,'parent_ordinary':old['use'],'new_usage':usage,
         'original_1373_database_and_work_objects_unchanged':True,'working_changes':work['total_changed'],'candidate_tests_passed':read(ART/'mention-contracts/result.json')['passed'],
         'working_duplicate_checks':checks['passed'],'production_publications':0,'selected_main':read(DES/'baseline.json')['pointer']['generation']}
put(RUN/'result.json',summary)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':'1373/repaired'},'repaired':summary},comparisons=[],judge_disagreements=0,usage=usage,
                    latency={'comparison_seconds':conf['seconds'],'usage_seconds':[c['request_seconds'] for c in cases]},error_taxonomy=grade['issues'])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=[grade['headline'],'이전1373은 지지 판단을 누적했고, 실제 오판의 두 번째 상법 언급을 지목한 잘못된 원문 좌표가 정리 과정에서 5회 거절됐다. 일반 ON/OFF 질문은 모두 원문전용이었다.',
       str(read(DES/'criteria.json')['success']),m['runs'][0]['selection_rule'],'누적은 완료1373 기반 후보. 명시 질의는 별도 동결한 완료1369 답변 소비자, 동일 공개 상법·같은 승인 2판·기본 검토 ON·Qwen FP8이다.',
       grade['conflict'],grade['use'],f"{usage['physical_calls']}회, 결과불명 {usage['unknown']}회, 보고비용 USD {usage['reported_cost_usd']:.8f}. 원문과 실제 전송 단계 원장 참조.",
       grade['interpretation'],grade['limits'],'실험 DB 복사 및 시험용 승인과 실제 현장/Gold는 분리한다. 작업 변경 전 파일은 artifacts/working-before. 원기록·원래 실패 응답은 보존했다.',
       'setup→후보 동결→이전 실제 5개 오류와 새 선택 계약 검사→복사본·API 준비→실행기/자료 동결→run_live→원문 및 확정 사용 검사→finish→seal/hash/status/validate --final/graph']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 상충 판단 및 명시 활용\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,parts),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
    is_q=q['case_id']=='charter-explicit'
    qs=['run-001/repaired',read(DES/'live-cases.json')[0]['steps'][0]['question'] if is_q else '이전 실제 오판 원문을 같은 묶음에 대조한다.',
        '433/434 원문, 실제 주장의 경로·근거 관계로 검토한다. 별도 채점 정답을 전송하지 않는다.',
        '### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger.json.gz에 실제 회수 기록. 고정 판단 비교는 검색 없음.',
        'followup-conflict 및 usage-live의 raw와 canonical에 모델 요청/응답 보존.', 'calls.json 및 generations.json의 단계별 기록.',
        '중복 요청, 원기록/승인 패키지·확정 사용·원문 대조, 채점 모델0.',grade['use'] if is_q else grade['conflict']]
    (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,qs),1))+'\n')
(ADR/'실험/README.md').write_text('# 사례 기록\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
report=ROOT/'09_ARTIFACTS/AUDITS/20261105-charter-accumulation-reuse'
(report/'최종_대조결과.txt').write_text('\n\n'.join([grade['headline'],old['grade']['detail'],grade['conflict'],old['grade']['reuse'],grade['use'],grade['interpretation'],grade['limits'],parts[7],*[c['answer'] for c in cases]])+'\n')
print(grade['headline'])
