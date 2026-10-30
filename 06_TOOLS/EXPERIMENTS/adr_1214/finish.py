"""Record measured outcomes, including failed real runs, without promotion."""
from pathlib import Path
import json,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';O=A/'artifacts/run-001';D=A/'artifacts/design';U=R/'09_ARTIFACTS/AUDITS/20261029-gold-connected-glossary';P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
integrity=read(O/'final-integrity.json');assert integrity['originals_unchanged'] and integrity['engine_unchanged']
cases={c:read(O/'live'/c/'result.json') for c in ('cm-007','cm-009')}
calls={c:read(O/'live'/c/'calls.json') for c in cases}
replay=read(O/'live/replay-saved-cm-009-2/result.json')
assert replay['error'].startswith('REPLAY_REACHED_NEXT_MODEL_STAGE:source-law-navigation-11-') and replay['model_calls']==0
activation=read(O/'activation-result.json') if (O/'activation-result.json').exists() else {'passed':False,'reason':'channel not activated'}
cleanup=read(A/'artifacts/cleanup-result.json')
cost=sum((x.get('usage') or {}).get('cost',0) or 0 for rows in calls.values() for x in rows)
result={'status':'TECHNICAL_PORT_PASS_REAL_INFERENCE_INCOMPLETE','diagnostic_complete':True,'quality_certified':False,'documents':21,'tables':13,'columns':60,'query_id':read(O/'build-result.json')['query_id'],'glossary':read(O/'glossary-scope-audit.json'),'vectors':16085,'native_checks_passed':read(O/'check-003/result.json')['passed'],'structure_checks':read(O/'structure-check-7/result.json'),'real_cases':cases,'replay_after_fix':replay,'model_calls':sum(len(x) for x in calls.values()),'unknown':sum(x['unknown'] for x in cases.values()),'reported_cost_usd':cost,'actual_final_answers':0,'activation':activation,'integrity':integrity,'cleanup_bytes':cleanup['logical_bytes_removed'],'main_promoted':False,'source_sqlite_fallback':False,'connector_folder':str(P.relative_to(R))}
assert all('error' in x for x in cases.values()),'Review successful answer before declaring outcome'
put(O/'result.json',result)
replay_text=json.dumps(replay,ensure_ascii=False,indent=2)
report=f'''R12 골드 연결·용어집 축소·기존 엔진 실험 결과 (2026-10-30 KST)

판정: 데이터 연결과 별도 파라미터 연결기는 구현했다. 실제 전체 추론은 미통과다.
기존 MAIN120 487파일을 변경하지 않았다. 별도 작업의 활성 MAIN 변경은 따라가지 않았다.

완료한 데이터 작업
- CM 필수 21문서 범위의 기존 원문/검색 자료를 유지했다. 전체 보유 1,547문서 이관은 아니다.
- 13테이블·60컬럼 유지. 13개 PK와 11개 일반 인덱스 유지. 논리 ID 연결을 검증했으며 새 FK 제약은 만들지 않았다.
- 추가 논리 1,492,223행을 1,050,337개 물리 행으로 묶고 전체 읽기/해시 대조 후 게시했다.
- Oracle 사용자 데이터는 게시 완료 시 9,092,857,856바이트, 12GB의75.77%였다. 기존 게시물까지 포함하여9.6GB 한도 이내다.
- 기존 비고유 인덱스1개를 같은 이름·키로 접두부 압축하여594,542,592바이트를 줄였다. 데이터/PK는 변경하지 않았다.
- 용어집은 원본115,017개 중 골드 연결 범위69,813개를 보존했다. 원본 용어집을 삭제한 것이 아니다.
- 조회 표기/별칭1,933,507→107,018개. 고아 표기0·유지 근거 없는 항목0·공식 연결의 끊어진 끝점0.
- 세입자/집주인/월급 같은 일상어→법률어의 직접 공식 연결을 보존했다. 외부 개념은 검토된 동일성 연결3개만 남겼다.
- BGE-M3 1024차원 실제 벡터16,085개와 모든 구간→원문 ID 결속을 확인했다. 질문 벡터/Oracle 검색100개 원문 ID 대조 통과.

기존 엔진과 실제 모델
- native 서비스 시작, 원문/전문검색/용어집/참조, 모델 없는 질문 API 통과. 이것을 실제 추론 답변 통과로 세지 않았다.
- 7번 실제: {cases['cm-007']['seconds']:.3f}초, 모델1회 뒤 QUERY_FULL_CATALOGUE로 중단. 최종 답변0. 같은 질문 실제 재실행 없음.
- 7번 저장 응답 재생: 연결 오류·반복 읽기 보완 뒤163초/SQL6,284회로 다음 조사 모델 입력까지 도달. 추가 모델0이며 실제 답변 완료가 아니다.
- 9번 실제: {cases['cm-009']['seconds']:.3f}초, 모델8회(Parasail429 포함), Near AI 전환1회. 원문 선택을 진행했지만 SQL10,000회 한도에서 중단. 최종 답변0.
- 실제 호출 합계{result['model_calls']}회, UNKNOWN{result['unknown']}, 보고 비용${cost:.8f}. 429의 미보고 비용은 알 수 없다.
- 반복 검증된 탐색 행 조회를 요청 내16MiB/4,096개 한도로 재사용하도록 추가 보완했다. 권한/판본 변경·반환값 변조·누락 실패 검사를 통과했다.
- 문서 메타8MiB·원문16MiB도 요청 내 검증된 값만 재사용한다. 새 요청은 재검증하며 실패/불완전 결과는 캐시하지 않는다.
- 새 실모델 재시험은 하지 않았다. 저장 HTTP 응답 재생은 아래처럼 별도 기록하며, 모의 전달 영수증을 실제 전송 증거로 쓰지 않는다.
- 저장된 HTTP8개를 동일 gateway에 재생한 결과, SQL4,812회/268.152초로 이전 한도 중단 지점을 넘어 다음 조사 입력까지 진행했다. 최종 답변 완료나 동일 실모델 속도 비교는 아니다.
{replay_text}

별도 연결 폴더
{P}
connect.py의 --config / --credentials / --documents / --release-id / --channel로 연결한다.
기본은 고정된 새 게시물 ID다. 새 프로세스 전용 데이터 포트를 설치하며 기존 엔진과 같은 프로세스에 혼합하지 않는다.
실제 모델·인증·외부 전송 권한은 호스트가 제공해야 한다. CLI는 자동 외부 모델 호출을 하지 않는다.
새 실험 채널 활성 상태: {json.dumps(activation,ensure_ascii=False)}

보존·정리·한계
- 원본 DB9개와 MAIN120 487파일의 최종 SHA를 재확인했다. 기존 cm-r12·활성 MAIN을 이 작업에서 바꾸지 않았다.
- 불필요한 과거 export 사본만 {cleanup['logical_bytes_removed']:,}바이트 정리했다. 삭제 전 해시·경로·사용 중 여부와 실패 로그를 보존했다.
- 실제 여유 공간 GiB: {json.dumps(integrity['free_GiB'],ensure_ascii=False)}. 수동 trim은 실행하지 않았다.
- 최초 자동 승인 검토가 외부 목적지/전송 범위의 명시 부족으로 모델 실행을 차단했다. 사용자 명시 승인 후 해소됐으며 해당 차단 중 전송은 없었다.
- 전체 추론의 최종 성공, 법률 품질, 전체 CM51 답변, GENOS/ORDS/NFS 현장 연결, B05 실제 DB는 검증하지 않았다.
- 실패를 통과로 바꾸지 않는다. 실제 성공 확인은 별도 고정 실행으로 남겨야 한다. 승인된 이번 각1회 시험은 끝났다.
'''
(U/'골드연결_구현과_실험결과.txt').write_text(report)
b=read(P/'binding.json');f=read(D/'freeze.json');b.update(adapter_root=str(Path(f['entries']['runtime']).parent),files=f['files'],candidate_revision=f['revision_id'],inference_status=result['status'],default_channel_activated=False,experimental_channel=activation.get('channel'));put(P/'binding.json',b)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'HISTORICAL_BOOTSTRAP_FAILURE','reexecuted':False},'connected':result},comparisons=[],judge_disagreements=None,usage={'model_calls':result['model_calls'],'reported_cost_usd':cost,'unknown':result['unknown']},latency={c:x['seconds'] for c,x in cases.items()},error_taxonomy=[{'kind':c,'error':x['error']} for c,x in cases.items()])
reason='Fixed engine retrieval policy/ranking was not changed. This is a failed-baseline data-port integration probe, not a valid before/after article recall comparison. Glossary export scope changed and has a separate measured scope audit. Partial actual retrieval and all model inputs/outputs are preserved, but no final answer or complete golden-recall score is claimed.'
m['retrieval_accounting'].update(changed=False,corpus_total=21,not_applicable_reason=reason);m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
inputs={c['id']:c for c in read(D/'cases.json')}
for q in m['questions']:
 c=q['case_id'];v=cases[c];base=O/'live'/c
 values=['run-001/connected; 고정 MAIN120 / R12 21문서; 실제 각1회',inputs[c]['request']['json']['question'],'정답/정답 좌표를 제품 입력에 제공하지 않았다. 법률 품질 채점 모델0회.','동결 cases.json·21문서 권한·새 Gold 게시물.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n부분 탐색의 canonical/원시 응답/runtime journal을 보존했다. 최종 답변0이므로 완결 회수율을 계산하지 않는다.',f"실제 물리 {v['model_calls']}회. 원시 요청/응답: {base.relative_to(R)}/raw. canonical 전체 입력/출력: 같은 폴더 canonical.",json.dumps(read(base/'generations.json'),ensure_ascii=False,indent=2),'자동 같은 사례 재시험 없음. 저장 응답 재생은 별도 모의 검사로 분리한다. 기준답변 채점0회.',json.dumps(v,ensure_ascii=False,indent=2)]
 path=A/'실험'/q['file'];path.write_text('# '+c+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n');q['sha256']=sha(path)
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 실험 인덱스\n\n'+''.join(f"- [{q['case_id']}]({q['file']}): 실제 실행 미통과, 최종 답변0\n" for q in m['questions']))
sections=[('결정 요약','기술 연결 구현 완료, 실제 전체 추론 미통과. MAIN 승격 없이 별도 Gold 연결기를 제공한다.'),('문제와 변경 전 구조','ADR1212의 최신 선택·탐색·용어집·참조·벡터 계약 누락을 별도 게시물/연결부에서 구현했다.'),('가설과 사전 판정 기준','artifacts/design/criteria.json에 고정했다. 13테이블60컬럼/9.6GB/원문 권한·해시·동일 MAIN120/CM007·009 실제 각1회. 초기 기준과 후속 보완 실패는 보존한다.'),('실험 설계','baseline은 ADR1212의 역사적 실패이고 재실행하지 않았다. connected는 별도 후보의 순차 수정·동결·로컬 계약 검사·실제 시험이다. 반복 재생은 새 독립 성공 표본이 아니다.'),('데이터·모델·재현성','21문서/MAIN120 487파일. 모델 정책 및 외부 승인: artifacts/design/authorization.json. 각 실행은 해당 동결 revision의 경로가 traceback/로그에 보존된다. 최종 binding은 별도 연결 폴더에 있다.'),('결과',report),('사례별 오류 분석','7번 목록 조회 계약 오류는 후속 연결부와 저장 응답 재생으로 보완했다. 9번은 실제 원문 선택 중 SQL10,000 한도로 중단했다. 이후 반복 행 조회 보완과 모의 재생을 실제 성공으로 대체하지 않는다.'),('비용·지연·회수 규모',f"실모델{result['model_calls']}회·보고비용${cost:.8f}·UNKNOWN0. 7번{cases['cm-007']['seconds']:.3f}초/9번{cases['cm-009']['seconds']:.3f}초. 벡터/원문/용어집 검사 시간은 각 result.json이며 통합 속도 개선율로 합치지 않는다."),('해석','저장 구조·조회 계약·모의 진행·실제 답변 완성을 구분한다. 원본 일상어 연결을 보존한 축소 게시물이지 의미 자동승인이나 원본 전체 용어 삭제가 아니다.'),('한계와 일반화 가능 범위','실제 두 질문 모두 최종 답변0. 전체 CM51·법률 의미 정확성·전체1547문서·GENOS/NFS/ORDS·B05 실DB 미검증. 동시 작업 MAIN 선택을 이 실험의 결과로 해석하지 않는다.'),('운영 결정·롤백 조건','별도 프로세스/새 게시물 ID로만 사용한다. 기존 cm-r12와 MAIN 유지. 새 채널을 사용하지 않으면 기존 경로로 돌아간다. 원본 DB와 이전 게시물은 보존한다.'),('재현 명령','별도 연결 폴더 README.txt를 따른다. 완료된 실제 CM 폴더는 자동 덮어쓰지 않는다. 전체 raw와 검증/실패/삭제 전 해시는 artifacts에 보존한다.\n\n```bash\nPYTHONDONTWRITEBYTECODE=1 .venv/bin/python 06_TOOLS/COMMANDS/adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation --final\n```')]
front=(A/'README.md').read_text().split('---',2)[1];(A/'README.md').write_text('---'+front+'---\n\n# ADR-1214: R12 골드 연결 구현과 실제 엔진 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']+[U/'골드연결_구현과_실험결과.txt']+list(P.glob('*'))+list(Path(__file__).parent.glob('*.py'))
am=read(A/'artifacts/manifest.json');am['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Gold implementation, validation and preserved failed evidence','contains_raw_prompts_and_outputs':'/live/' in str(p)} for p in paths if p.is_file()];put(A/'artifacts/manifest.json',am)
print(result['status'],result['model_calls'],cost)
