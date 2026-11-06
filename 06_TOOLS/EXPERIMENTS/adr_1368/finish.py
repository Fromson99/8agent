from common import *
import collections

out=ART/'build-live'
machine=read(ART/'saved-build-review.json')
review=read(ART/'content-review.json')
work=read(ART/'working-integration.json')
tech=[read(ART/n/'result.json') for n in ('review-contracts','resume-contracts','working-service-check')]
r=read(out/'result.json')
criteria=read(DES/'criteria.json')
manifest=read(ADR/'실험/manifest.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer']
assert all(sha(ROOT/n)==h for n,h in work['changed_hashes'].items())
assert all(sha(ROOT/n)==h for n,h in read(DES/'freeze.json')['files'].items())
new=[v for a in tech[:2] for v in a['rows'] if v['outcome']=='passed' and 'CONTRACTS/test_wiki_workspace' not in v['test']]
summary={'result':r,'review':review,'machine':{k:v for k,v in machine.items() if k!='compiled'},
         'working_product_files':work['product_files'],'working_total_files':work['total_changed'],'preflight':work['preflight'],
         'candidate_contracts_passed':sum(t['passed'] for t in tech[:2]),'new_or_adapted_contracts_passed':len(new),'working_duplicate_checks_passed':tech[-1]['passed'],
         'unchanged_historical_fixture_failures':1,'active_generation':read(DES/'baseline.json')['pointer']['generation'],
         'physical_calls':r['physical_calls'],'unknown':r['unknown'],'reported_cost_usd':r['reported_cost_usd']}
put(RUN/'result.json',summary)
manifest['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
manifest['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'record':'ADR1354/repaired'},'repaired':summary},
    comparisons=[],judge_disagreements=0,usage={k:summary[k] for k in ('physical_calls','unknown','reported_cost_usd')},latency={'one_build_seconds':r['seconds']},error_taxonomy=review['findings'])
put(ADR/'실험/manifest.json',manifest)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
paragraphs=[review['outcome'],'이전 ADR1354에서는 7개 저장 뒤 문장 분해와 공유 노드로 최종 묶음이 중단됐다.',
    str(criteria['success']), '공개 원문과 과거 판단을 고정한 정관 변경 묶음 1건. 단계별 첫 시도와 최대 네 번 보완, 확인되지 않은 전송·원문/권한 변경·기한 종료 시 중단한다.',
    '완료1354 코드에서 구축 제품3파일 변경 후 rev001 동결. Parasail Qwen3.8 FP8 추론none, 기존 실제 공개 원문을 대조했다. 정답키 주입과 모델 채점은 없다.',
    review['description'], str(review['findings']), f"실제 {r['physical_calls']}회, UNKNOWN {r['unknown']}회, {r['seconds']:.3f}초, 보고비용 ${r['reported_cost_usd']:.8f}. 회수 과정은 고정 입력을 사용했다.",
    review['quality'], '정관 사례1건, 각 입력의 근거·수치·사용 목적은 개별 확인 대상이다.',
    '검증한 구축 파일3개와 현재 엔진 핀을 작업 코드에 적용했다. 원복 바이트는 artifacts/working-before에 있다. 선택 MAIN/게시/현장 자동승격 없음.',
    'setup.py → 후보 변경 → freeze.py → check.py → build.py --preflight → 호출 조건 동결 → build.py → inspect_build.py → 검토/재개/작업코드 검사 → finish.py/기록 해시검증. 실제 실험 폴더는 같은 요청을 재송신하지 못하도록 독점 생성한다.']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 정관 변경 묶음 구축과 네 번 보완\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,paragraphs),1))+'\n')
qheads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
qvalues=['run-001/repaired/rev-001','정관 변경 묶음의 검토 실패 시 4회까지 추가 보완하여 실제 저장 여부 확인.','433조 제1항과 434조의 두 기준을 원문과 대조한다.','### 회수·탈락 단계 원장 — run·arm별\n\n새 검색 없음. design/originals.json 및 records.json.','artifacts/build-live/raw에 물리별 실제 요청·응답/부분 응답을 보존했다.','artifacts/build-live/canonical, calls.json, generations.json과 saved-build-review.json을 확인한다.','평가자 모델0. 동일 묶음 구축 1회, 실패한 검토 단계만 다시 제안한다.',review['outcome']+' '+review['description']]
q=manifest['questions'][0]
(ADR/'실험'/q['file']).write_text('# 정관 변경 묶음\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qheads,qvalues),1))+'\n')
(ADR/'실험/README.md').write_text(f"# 실험 질문\n\n- [정관 변경 묶음]({q['file']})\n")
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261105-ontology-build-review-1368';OUT.mkdir(exist_ok=True)
(OUT/'구축_검토결과.txt').write_text('\n\n'.join([review['outcome'],review['description'],review['quality'],paragraphs[7], '원문·권한·판본 검증과 단계별 실패 보존. 최대 시도5회, 통과 시 조기 종료. 재개 시 시도 횟수와 기한 유지.', '검사: 후보 '+str(summary['candidate_contracts_passed'])+'통과, 변경 전부터 같은 구형 fixture 실패1건. 작업 코드 재확인 '+str(tech[-1]['passed'])+'통과. 실험 결과와 운영 게시 승인 별도.'])+'\n')
print(review['outcome'])
