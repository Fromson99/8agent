"""Record technical completion and independently reviewed semantic coverage separately."""
from common import *

out = ART/'build-live'
result = read(out/'result.json')
inspection = read(ART/'saved-build-review.json')
review = read(ART/'content-review.json')
integration = read(ART/'working-integration.json')
tests = read(ART/'compiler-contracts/result.json')
working = read(ART/'working-service-check/result.json')
candidate = read(DES/'candidate.json')
assert all(sha(ROOT/n)==h for n,h in read(DES/'freeze.json')['files'].items())
assert all(sha(ROOT/n)==h for n,h in integration['changed_hashes'].items())
assert all(sha(ROOT/candidate['code_root']/n)==h for n,h in candidate['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer']
summary = {'outcome':review,'result':result,'stored_knowledge':inspection['knowledge'],
           'stage_counts':inspection['logical_stage_counts'],'submitted':inspection['submitted'],
           'exact_source_literals':inspection['exact_source_literals'],'archived_judgment_literals':inspection['archived_judgment_literals'],
           'unexpected_literals':inspection['unexpected_literals'],'published':inspection['publication_count'],
           'physical_calls':result['physical_calls'],'unknown':result['unknown'],'reported_cost_usd':result['reported_cost_usd'],
           'seconds':result['seconds'],'candidate_tests_passed':tests['passed'],'working_rechecks_passed':working['passed'],
           'working_changes':integration['total_changed'],'candidate_revision':candidate['pin']['revision_id'],
           'selected_main':read(DES/'baseline.json')['pointer']['generation']}
put(RUN/'result.json',summary)
design = read(DES/'criteria.json')
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'record':'ADR1368/repaired'},'repaired':summary},
                    comparisons=[],judge_disagreements=0,usage={k:summary[k] for k in ('physical_calls','unknown','reported_cost_usd')},
                    latency={'build_seconds':result['seconds']},error_taxonomy=review['issues'])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
notes=[review['headline'],'부모1368에서는 자유롭게 생성한 노드 2개와 별도 커버리지 표를 생성했다. 7개 문장을 전부 포함으로 표시해 5개 오연결이 최초와 4회 보완에서 반복됐다.',
       design['hypothesis']+' '+str(design['success']), '문장별 용도를 먼저 판단하고 포함한 문장에서만 노드 원문과 본문 슬롯을 복원한다. 근거·판단은 모델이 선택하며 기존 검토기·네 번의 보완·중단 조건을 유지한다.',
       '공개 상법 433/434조의 기보관 실제 정관 판단, 원문과 모델·전송은 완료1368과 동일. rev001의 설계 검토에서 노드에 실제 관찰이 필요한 제약을 발견하여 송신 전 rev002로 동결했다.',
       review['detail'],str(review['issues']),f"{result['physical_calls']}회, 결과불명 {result['unknown']}회, {result['seconds']:.3f}초, 보고비용 USD {result['reported_cost_usd']:.8f}. 고정된 입력으로 새 회수 단계 없음.",
       review['meaning'],'정관 변경 1건의 재현이며 법률 내용 전반이나 온톨로지 ON/OFF 성능을 인증하지 않는다.',
       f"작업 제품 1개와 현재 엔진 핀에 반영. 후보 검사 {tests['passed']}건, 작업 재확인 {working['passed']}건. 선택 MAIN142와 현장 승격 별도. 작업 변경 전 바이트는 artifacts/working-before.",
       'setup→후보 격리 변경→freeze rev002→check→build --preflight→입력·실행기 해시동결→build→inspect_build→내용 대조→integrate/작업검사→finish 및 최종 기록 검증. 실제 외부 호출 원본 경로 재사용 금지.']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 문장별 온톨로지 자동 구축\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,notes),1))+'\n')
q=m['questions'][0]
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
qs=['run-001/repaired/rev002','정관 변경의 주주총회 결의요건과 각 비율의 기준 재사용','별도 정답 주입 없이, 저장된 원문 양쪽과 비율·분모, 범위와 실제 근거 인용을 대조한다.',
    '### 회수·탈락 단계 원장 — run·arm별\n\n검색 없음. design/records.json, design/originals.json의 고정 자료 사용.',
    'artifacts/build-live/raw, canonical에 실제 요청·원응답 보존.',str(inspection['logical_stage_counts']),
    '별도 평가모델 0회. 저장소와 원문 대조, 반복은 검토기 거절이 확인된 경우만 허용한다.',review['headline']+' '+review['detail']]
(ADR/'실험'/q['file']).write_text('# 정관 변경\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,qs),1))+'\n')
(ADR/'실험/README.md').write_text(f"# 실험 기록\n\n- [정관 변경]({q['file']})\n")
report=ROOT/'09_ARTIFACTS/AUDITS/20261105-ontology-auto-build-1371'
report.mkdir(exist_ok=True)
(report/'자동구축_결과.txt').write_text('\n\n'.join([review['headline'],review['detail'],review['meaning'],notes[7],notes[10]])+'\n')
if inspection['compiled']:
    compiled = read(ART/'build-live/compiled.json.gz')
    paths = compiled['package']['paths']
    parts = ['자동 생성 초안', review['headline'], review['detail'], review['meaning']]
    for path in paths:
        pending = ', '.join(r['slot'] for r in path['unresolved'])
        parts.extend([path['title']+' ('+path['status']+')', path['body'], '남은 검토 항목: '+pending])
    (report/'생성묶음_미리보기.txt').write_text('\n\n'.join(parts)+'\n')
print(review['headline'])
