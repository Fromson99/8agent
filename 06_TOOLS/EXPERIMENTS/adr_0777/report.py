from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0777-schema-recovery-main'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=[{'baseline':'baseline','candidate':'recovery',
 'paired_count':410,'baseline_contract_correct':result['by_arm']['baseline']['contract_correct'],
 'candidate_contract_correct':410,'meaning':'new technical contract coverage, not legal accuracy'}],
 judge_disagreements=0,usage=result['usage'],latency={'kind':'Synthetic local contracts only; model latency not measured'},error_taxonomy=[])
put(A/'실험/manifest.json',m)
parts=[('결정 요약','Accepted promotion-candidate. 모델 출력의 구문/구조/판단·근거/상태 검증을 구분하고 동일 결정의 교정을 한 곳에서 최대1회 수행한다. 기존 원문·권한·revision·발행 규칙을 보존한다.'),
('문제와 변경 전 구조','MAIN61의 모델 제안 검증은 단계마다 다른 예외와 재시도 책임을 사용했다. ADR0776에서 알려진 실패와 과거 설계 이유를 조사해 격리 후보를 구현했다. 이번은 코드 변경 없이 새로 고정한 전수 계약 감사다.'),
('가설과 사전 판정 기준','criteria.json과 cases.json을 실행 전에 고정했다. 25종 JSON × 중첩4 × 종료상태4=400조합과 영속 상태10종을 모두 평가한다. 허용 오류0이며 실제 법률 정확도나 모델 오류 빈도 감소는 판정하지 않는다.'),
('실험 설계','MAIN61과 ADR0776 rev-010에서 가져온 byte-identical 후보를 서로 다른 프로세스로 평가했다. 신규410조합은 전수 프로토콜 감사이며 알려진817개 회귀는 별도 보조 검사다. 모델/검색 효과 비교나 미사용 법률 holdout으로 설명하지 않는다.'),
('데이터·모델·재현성','코드/원문 세대/모델 정책/runner/기준 포인터/작업 의존 파일을 freeze.json으로 결속했다. 실제 모델 호출0. raw JSON은 합성 예시이며 내부 질문·원문 반출은 없다. serving 파일과 build 전용 파일의 소비 경로를 구분했다.'),
('결과',f"신규 계약: 후보410/410, 기준{result['by_arm']['baseline']['contract_correct']}/410. 차이는 새로운 엄격 JSON·typed 오류·영속 원장 계약의 적용 여부다. 알려진 회귀817통과/1collection skip/0실패. 모델 정답률 수치가 아니다."),
('사례별 오류 분석','동일 key 덮어쓰기, 비표준 숫자, 불완전 JSON, 거절/길이 종료, 교정 예산 소진, 예약 후 unknown, 완료 receipt 재사용/변조, 송신 뒤 실패를 구분한다. API·AD SQL·현재 판단/근거·reference·문서 검토 소비자는 원래 검증을 계속 수행한다.'),
('비용·지연·회수 규모','모델·토큰0. 정상 제안에 추가 판단 호출을 넣지 않았다. 복구 최대1회와 전체 deadline/물리 호출 예산을 함께 적용한다. 실제 내부 모델 지연/비용/오류 발생 빈도는 미측정이다.'),
('해석','오류 문구를 숨겨 통과시킨 결과가 아니다. 틀린 제안은 실행 전에 거부하고, 같은 근거·허용 범위에서만 수정하거나 명시 실패/제한 응답으로 종료한다. 과거 source gap·조건/예외·근거 채택·shortcut 정책은 유지된다.'),
('한계와 일반화 가능 범위','GENOS 내부 모델·실제 설치·리비전·워크플로우 화면은 미확인이다. 객체 key 기반 출력과 sparse patch는 공급자별 후속 실험을 요구하는 조건부 후보이며 활성화하지 않았다. 실제 모델 스키마 오류가 0이 된다고 보장하지 않는다.'),
('운영 결정·롤백 조건','사용자 “이거 싹다 구현해봐” 승인 범위로 파일별 hash 확인 후 통합하고 qualified prepare/apply --confirm-main을 수행한다. MAIN61과 원문 세대를 보존한다. 실패 시 표준 rollback과 GENOS backup undo를 사용하며 진행 중 요청의 구 상태를 새 버전으로 자동 승인하지 않는다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_0777/{prepare,freeze,audit,report,prepare_promotion,verify_active}.py. stable adr_structure status/validate --final/graph 및 rag_main_promotion prepare/check/apply. 완료 run은 후속 ADR 없이 재실행하지 않는다.')]
meta=f"---\nadr_id: ADR-0777\ntitle: 모델 출력 복구 계약 전수 감사와 MAIN 반영\nstatus: Accepted\ndecision_date: 2026-10-14\nphase: audit\nin_sample: false\ndecision_eligible: true\nmain_wiring: promotion-candidate\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 출력 복구 계약 전수 감사\n\n400개 JSON/완료 조합과10개 영속 상태. 기준/후보 모두 같은 사전 고정 행렬. 실제 모델0회. 상세: ../artifacts/run-001/result.json.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0777','created_at':m['reservation']['created_at'],
 'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen qualification evidence',
 'contains_raw_prompts_and_outputs':p.suffix=='.log'} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']})
