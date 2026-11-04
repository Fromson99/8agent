from common import *
import shutil
r=read(ART/'comparison.json');b=r['by_arm']['before'];a=r['by_arm']['optimized'];m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical':'ADR-1310-experiment-v1/profile'},'before':b,'optimized':a},comparisons=[{'baseline':'before','candidate':'optimized','replay_reduction_percent':r['replay_reduction_percent'],'all_protected_inputs_and_answers_equal':True,'same_observer':True,'live_latency_claim':False}],judge_disagreements=0,usage={'physical_calls':0,'tokens':0,'cost_usd':0,'recorded_responses':16},latency={'before':b['seconds'],'optimized':a['seconds'],'p95':None,'p95_reason':'One fresh-process pair with model replies replayed; no population latency distribution'},error_taxonomy=[{'type':'preexisting_fixture','count':1,'before_and_after_same':True}]);put(ADR/'실험/manifest.json',m)
sections=[
('결정 요약',f"구조 전수순회와 반복 조회를 수정했다. 동일 입력·응답 재생 {b['seconds']:.3f} → {a['seconds']:.3f}초, {r['replay_reduction_percent']:.2f}% 감소. 모델 서비스 대기시간을 뺀 서버 경로 비교다. 두 실행 모두 보호 입력8/8·최종 내용 동일. 작업 제품4모듈과 관련 pin에 반영했으며 선택 MAIN136은 유지한다."),
('문제와 변경 전 구조','부모마다 전체256848개 노드를 순회하고 verify가 resolve를 다시 호출했다. 구조 색인이 이미 있었지만 Nodes.children이 사용하지 않았다. 검색 문서 필터는 원문 메타JSON을 개별 조회했고 같은 원문 블록 점조회도 반복했다.'),
('가설과 사전 판정 기준','기존 선택 범위·순서·metadata_hash·오류·원문/ACL/판본을 유지하면서 동일 관측기 재생 시간을50% 이상 줄인다. 보호 입력의 첫 차이, 새 회귀, 네트워크 접근이나 자원 기준 위반이면 중단한다. artifacts/design/criteria.json에 실행 전 동결했다.'),
('실험 설계','부모 MAIN136 검토표OFF517파일을 before/optimized로 격리하고 4제품모듈 및 종속pin만 수정했다. 같은 저장8응답과 보호 입력 비교기를 사용해 before→optimized 각1회, 새 프로세스로 순차 실행했다. OS 파일 캐시는 초기화하지 않았다. 새 모델/Oracle0. 실제 모델과 종료 감독 변경은 후속 ADR로 분리한다.'),
('데이터·모델·재현성','ADR1309 after369의 원응답을 재사용한다. 새 데이터나 정답을 제품 입력에 추가하지 않는다. 네트워크 금지, RSS4GiB/가용RAM5GiB 입장·3GiB 실행/swap증가128MiB/디스크20GiB 조건 유지. 코드·기준·실행기·원응답 해시는 design/freeze.json과 candidate descriptors에 보존.'),
('결과',f"동일 재생16/16 보호 입력·최종 내용2/2 일치. source span 직접 대조 before{b['source_span_checks']}/optimized{a['source_span_checks']}·불일치0. children 표본 {b['children_sample_seconds']:.3f}→{a['children_sample_seconds']:.3f}초. 원문 블록 점조회 {b['block_point_queries']}→{a['block_point_queries']}, source JSON 점조회 {b['source_json_point_queries']}→{a['source_json_point_queries']}. 검사89통과, 기존 Oracle fixture1은 수정전후 동일실패·새 회귀0."),
('사례별 오류 분석','최초 실행기 hook 이름 오류로 검사 시작 전 중단했고 원본을 보존했다. 신규 fixture4개는 붙임조 번호 누락·중첩dict 과도한 계측·Oracle 좌표목록 누락을 정정했다. 부분 Oracle adapter에 릴리스 binding이 없으면 memo를 사용하지 않게 보완했다. 최종 남은1개는 기존 Units.row의 fixture release_id 부재로 baseline에도 동일. 제품 오류를 성공으로 숨기지 않았다.'),
('비용·지연·회수 규모',f"새 물리호출·보고비용0. 저장 응답16개 소비를 새 모델 사용량으로 합산하지 않는다. FTS {b['fts_queries']}→{a['fts_queries']}회, {b['fts_seconds']:.3f}→{a['fts_seconds']:.3f}초. 관측SQLite API {b['sqlite_api_seconds']:.3f}→{a['sqlite_api_seconds']:.3f}초. 이는 행 복원/UDF를 포함하며 일부 직접base 호출은 개별 타이머가 없다. 전체 재생/함수/SQL 중첩 시간은 합산하지 않는다."),
('해석','Nodes.children은 기존 document_tree.children 색인을 이용한다. mutable adapter는 한 번의 해석 안에서만 부모색인을 만든다. SQLite 좌표맵은 불변으로 고정하고 성공 해석만 최대128항목/1MiB로 재사용한다. 원문판본 검사·선택/schema/hash·ACL은 매 호출 유지한다. Oracle은 기존 요청 binding/deadline 캐시를 사용한다. query_scope는 문서별ID API/Oracle SourceScope를 유지해 JSON 개별조회와 lazy scope 붕괴를 없앤다. SQLite 원문블록은 Store 소유 최대512개/4MiB로 재사용하며 내용 변경·권한세대 변경 검사와 반환복사·실패 미캐싱을 유지한다.'),
('한계와 일반화 가능 범위','첫 준비의 두 source_unit 소비자 중복은 아직 남는다. native 컴파일러 코드를 바꾸면 Gold 파생 데이터 재게시 계약까지 연동되므로 이번 동등 조회 수정에 섞지 않았다. 감독의 FINISH 추가조사도 이번 재생에서는 그대로다. 실제 모델 전체시간과 Oracle corpus 지연을 개선율로 주장하지 않는다. 원문·호출경로 동일1쌍이며 일반p95/법률품질 인증은 아니다.'),
('운영 결정·롤백 조건','검증한 제품4파일만 작업 코드에 반영하고 작업엔진 pin을 재계산했다. 후보의 최종 검토표OFF 시험설정은 작업 기본설정에 복사하지 않았다. working-before 원본과 working-integration.json으로 되돌릴 수 있다. MAIN136/Gold binding/원문세대/DB·DDL·외부배포 변경0. 다음은 FINISH 감독 조건 수정과 동일 NearAI/SQLite 실제 질문 시험이다.'),
('재현 명령','setup.py → edit.py/refine.py → freeze.py → check.py → fixture baseline 확인 → replay.py ontology-369 before → optimized → analyze.py → integrate.py → 작업 native API 검사 → 기록/보관/최종 ADR 검사. 완료 이후 새비교는 새ADR에 기록한다.')]
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0]+'\n---\n';p.write_text(front+'\n# 구조 조회 지연 수정\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n')
q=next((ADR/'실험').glob('질문-*.md'));question=read(DES/'cases.json')[0]['question']
q.write_text(f'''# ontology-369 동일 응답 속도 비교

## 1. 실행 메타

run-001/before, optimized. 각1회 새 프로세스, 동일 관측기. 새모델0.

## 2. 사용자 질문 원문

{question}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

부모ADR1309 after의 최종 본문·주장·원문과 정확 동일성 대조. design/scoring-only-originals.json은 offline용이며 제품 입력에 추가하지 않았다.

## 4. 제품 입력을 구성한 원값

### 회수·탈락 단계 원장 — run·arm별

원문369/371의 부모 정본 ledger를 상속한다. 보호된8회 전체 요청이 각arm에서 동일하여 회수 정책/선택 범위 변경0. 원장 경로·hash는 manifest.retrieval_accounting.stage_ledger에 있다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

새 물리호출0. 부모 원시 요청/응답은 design/freeze.json에 hash로 결속. 각arm의 artifacts/replay/ontology-369-<arm>/replay-checks.json으로8/8 동일 확인. usage/view_id 이외의 요청 변경은 허용하지 않았다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

같은 폴더 canonical에 전 단계 입력/출력을 gzip 보존했다. 원응답8개씩 소비, 네트워크 금지. 새judge0.

## 7. 채점 호출과 반복 판정

정답 재채점0. 최종본문/claims/원문ID/scope/판본/미해결 전체동일2/2, 보호입력16/16. 독립 원문span 대조 불일치0.

## 8. 사례 최종 판정

재생 {b['seconds']:.3f}→{a['seconds']:.3f}초({r['replay_reduction_percent']:.2f}% 감소). 실제모델전체시간 개선률이 아니다. 계약89통과/기존fixture1동일. 상세 artifacts/comparison.json.
''')
(ADR/'실험/README.md').write_text('# 질문 인덱스\n\n- [상법369 동일 응답 비교]('+q.name+') — 양쪽 입력8/8·최종내용동일, 지연 감소.\n')
report=ROOT/'09_ARTIFACTS/AUDITS/20261104-structure-latency-repair';report.mkdir(exist_ok=True)
(report/'수정과_동일응답_속도비교.txt').write_text('\n\n'.join(f'{title}\n{body}' for title,body in sections)+'\n')
shutil.copy2(ART/'comparison.json',report/'comparison.json')
files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved performance repair evidence','contains_raw_prompts_and_outputs':'canonical' in p.parts or p.name in ('response.json.gz','request.json','runtime.tar.gz')} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and not (p.parent.name=='.observer-versions' and p.name.startswith('manifest-'))]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1311','files':files})
print('Finalized records; run validation before completion.')
