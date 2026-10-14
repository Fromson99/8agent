"""Publish the failed request and completed bottleneck diagnosis, without reruns."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0705-cm-max-call-bottleneck-probe';O=A/'artifacts/run-001';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');r=read(O/'result.json');d=read(O/'diagnostic.json');root=read(O/'root-cause.json')
dataset=read(D/'dataset.json');question=dataset['cases'][0]['question'];old=dataset['historical_result']
table='| 구간 | 모델 호출 | 시간 |\n|---|---:|---:|\n'
table+=f"| 요청 분류·세션 해석·명령 확인·질문 이해 | 4 | {d['groups']['request_interpretation']['seconds']:.3f}초 |\n"
table+=f"| 탐색·복귀·수정 요청 | 10 | {d['groups']['navigation']['seconds']:.3f}초 |\n"
prep=d['request_preparation'][0]['elapsed_ms']/1000
table+=f"| 자료·색인 최초 준비 | 0 | {prep:.3f}초 |\n"
table+=f"| 나머지 로컬 처리·전달 | 0 | {d['non_model_seconds']-prep:.3f}초 |\n"
table+=f"| 합계 | **14** | **{d['request_seconds']:.3f}초** |\n"
calltable='| 호출 | 작업 | 초 | 입력 토큰 | 출력 토큰 |\n|---:|---|---:|---:|---:|\n'
for u in r['usage']:
 calltable+=f"| {u['call']} | {u['phase'].split('-',2)[2]} | {u['seconds']:.3f} | {u['input_tokens']:,} | {u['output_tokens']:,} |\n"
findings='''1. **약칭과 문서 연결 실패.** 요청의 `상증세법`은 선택 문서의 공식 약칭/별칭과 document-alias projection에 연결되지 않았다. `NO_EXPLICIT_PAIR → MISSING_DOCUMENT`가 세 번의 구조 탐색에서 반복됐다. 실제 `상속세 및 증여세법 시행령`(문서 ID `0798989e52ca0254`)과 제49조(unit `1037`)는 저장돼 있고 공개65문서 허용 범위에도 포함돼 있다. 모델이 말한 “허용 문서에 없다”는 사실이 아니다.
2. **구조 후보의 다음 페이지 연결 손실.** 저장 구조 목록은 전체22→52→55개, `next_offset=12`였지만 `law_candidates.structured_discovery`는 첫 페이지를 문서11→7→7개로 바꾸며 `law_page.next_cursor=null`로 전달했다. 목표 문서는 이 첫 페이지에 없었다. 이는 전체 구조 목록을 확인했다는 증거가 아니다. 모든 후속 구조 도구로 접근 불가능하다고 단정하지는 않지만, 자동 탐색 메뉴에서 이어 읽을 정보가 손실됐다.
3. **새 근거 없이 같은 시점으로 복귀.** 실제 완료한 행동은 재검색2회·RETURN_TO5회였다. 중복 검색식은3번 거절됐고 수정 모델 호출은2회 발생했다. 결국 `MODEL_DECISION_UNRESOLVED`로 중단됐다. 원문 확보0·모델 전달0·최종 근거 채택0이며 ASSESS/답변 작성까지 도달하지 않았다.
4. **모델에 큰 탐색 화면을 반복 전달.** 탐색10회에 입력342,890토큰을 사용했다. 회당28,181~41,474토큰이다. 실제 원문을 읽기 전인데도 후보·상태·복귀 이력이 반복 전달돼 비용이 커졌다. 입력 크기와 지연의 인과 효과는 별도 비교 전까지 수치로 단정하지 않는다.
5. **질문을 받는 시점의 자원 초기화.** 자료 준비44.541초 중 resources43.596초, 해당 CPU43.380초였다. 함수 profile에서 `navigation_match._build`14.327초, `multi_entry_navigation.freeze`10.176초가 확인됐다. 후자는 재귀 포함15,138,257회 호출됐으며 모델 호출 횟수가 아니다. 세대 구조를 메모리에 구성·동결하는 비용이다. 이 값들은 준비 시간에 포함되므로 합계에 중복 가산하지 않는다.'''
priorities='''1. 약칭→공식 문서 연결과 문서 식별 실패/실제 부재를 구분한다. 약칭 해소가 안 되면 제목·별칭 후보를 좁혀 확인하고, 다른 문서의 같은 조문 번호로 넘기지 않는다. 별칭은 출처와 버전을 확인해 기존 투영에 반영한다.
2. 구조 목록의 `next_offset/total`을 탐색 메뉴까지 보존한다. 첫12개 항목을 전체 문서 목록으로 취급하지 않는다. fulltext는 문서·하위 범위 선택 뒤에만 실행한다.
3. 같은 상태·같은 근거·같은 복귀 지점을 반복하는 행동을 제어한다. “마지막으로 한 번 더 확인”만 반복하지 않도록 새 정보의 유무로 진행을 판정한다. 잘못된 읽기·채택을 허용해 성공률을 맞추지는 않는다.
4. 초기 구성 비용은 기존 프로세스 캐시의 실제 재사용부터 확인한다. 검증된 세대의 구조/별칭 인덱스를 사전 준비하고, 현재 요청에 필요한 범위만 조립하는 방향을 검토한다. 무결성 검사를 제거하는 해법으로 바꾸지 않는다.
5. 앞단4회→1회 통합 설계를 이어간다. 이번 앞단26.265초가 절감 상한이며 새 통합 호출 자체의 시간도 필요하다. 이번 실패를 고치는 일은 문서 연결·페이지·반복 제어가 먼저다.'''
parts=[
 ('결정 요약',f'CM-018을 MAIN48과 동일한 제품 코드·실제 서비스와 동일한 프로필로 **한 번** 실행했다. **HTTP422, 모델14회, 요청157.538초**로 답변을 완료하지 못했다. 진단은 완료했고 실패 이력을 보존했다. 최적화 코드·MAIN·GENOS 변경은 없다.\n\n질문: {question}\n\n'+table),
 ('문제와 변경 전 구조',f'확인한 CM 단일 요청 기록 중 ADR-0677의 CM-018이 모델29회·{old["request_seconds"]:.3f}초였다. 그중 탐색23회였다. CM-003의36회는 여러 사용자 턴 합계여서 제외했다. 검색한 metric 파일2740개 중20MB 초과118개는 펼치지 않았으므로 전체 역사에서의 절대 최대라고 주장하지 않는다. 최근 CM 단일 요청 최다 확인 사례라는 범위로 선택했다.\n\nMAIN48은 여전히 앞단4호출이고, 구조 우선·범위 내 본문 검색·묶음 읽기·압축 진행·호출 계측이 연결돼 있다.'),
 ('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json): 신규 제품 요청1회, 각 전송의 작업·시간 기록, 함수·중첩 구간 기록, 코드·데이터·프로필·활성 포인터 보존. 속도 개선이나 정답률 실험이 아니라 병목 귀속을 위한 probe다. 실패하면 원인을 보존하고 같은 ADR에서 임의 재시도하지 않도록 사전 고정했다.'),
 ('실험 설계','새 ADR-0705 선점 후 MAIN48 서빙285파일을 같은 해시로 snapshot/freeze했다. 별도 runtime·새 세션에서 기존 `/v1/rag/ask`를 한 번 호출했다. runner의 시간 래퍼와 Pipeline.run의 cProfile만 관측에 사용했다. 제품 프롬프트·검색·판단 코드는 변경하지 않았다. 설정 준비 검사0호출 후 본 실행14호출이다. 기존 운영 세션을 재사용하지 않았다.\n\n일반 manifest 검사에서 `changed=false`에 대한 설명 필드가 누락된 것을 발견해 설명만 추가했다. 첫 실행은 이미 시작된 상태였으며 입력·코드·성공 기준·계측은 바꾸지 않았다. 수정 기록은 manifest의 metadata_corrections에 남겼고 그 뒤 일반 검사를 통과했다.'),
 ('데이터·모델·재현성','로컬 MAIN48 `compact-progress-20261009-r1`, 원문 `term-source-8729f978a28924cb8c5b`, 공개 허용65문서. 질문은 공개 법령의 일반 구조 질문이고 비공개 사건 사실·회사 자료·정답을 전달하지 않았다. Qwen3.8 / OpenRouter Parasail FP8 단독·reasoning none·fallback 없음, ExperimentClient 사용. 실제 유효 프로필 해시는 MAIN48 서비스 영수증과 같다.\n\n앱 준비3.158초는 요청157.538초와 별도다. 새 프로세스의 첫 요청이지만 OS 파일 캐시까지 비운 실험은 아니다. cProfile의 추가 비용을 분리 측정하지 않았으므로 관측 시간을 무계측 서비스 지연으로 일반화하지 않는다.'),
 ('결과',table+'\n원문 확보·모델 전달·최종 채택은 모두0이다. 답변 오류 대신 일반 실패 안내와 조회 번호만 반환됐다. 전체 실패·거절·모델 입출력·journal은 보존했다. `LAW_FULLTEXT_DIRECTORY`와 `LAW_SCOPED_FULLTEXT` 이벤트는 모두0이다. 이번 실행은 전체 법률 본문을 읽느라 느려진 것이 아니라, 자료 준비 뒤 문서 후보와 복귀 판단에서 막혔다.'),
 ('사례별 오류 분석',findings+'\n\n[문서·권한·제49조·약칭·페이지 증거](artifacts/run-001/root-cause.json). 실제 존재와 노출·획득·채택을 구분했다. 근거0인 실패이므로 정답/오답률과 필수 근거 회수율은 채점하지 않는다.'),
 ('비용·지연·회수 규모',f'모델 합계103.566초, 그 밖 처리53.972초다. 입력346,790토큰·출력3,125토큰, 공급자 보고 비용 합계 $0.08891292. 재시도2회는14회 안에 포함한다. 공급자 HTTP 전송은14회이며 읽기 함수·복귀 행동 횟수를 모델 호출로 세지 않았다.\n\n'+calltable+'\n함수 누적 시간은 중첩돼 있으므로 단순 합산하지 않는다. [전체 구간·함수 진단](artifacts/run-001/diagnostic.json), [함수 profile](artifacts/run-001/function-profile.json), [회수 원장](artifacts/run-001/retrieval-ledger.json.gz).'),
 ('해석',priorities),
 ('한계와 일반화 가능 범위','이전29회·667초와 이번14회·158초는 코드·데이터 세대·질의 결과가 다르다. 이번은 실패이므로 성능 향상률로 계산하지 않는다. 단일 계측 요청이라 p50/p95, warm cache 성능, 실제 운영 대화 이력, 내부 GENOS 모델 성능은 미확인이다. 앞단 통합만으로 현재 실패를 해결하거나7초 응답을 보장할 수 없다. 프로파일링의 CPU 추가 비용이 포함돼 있다.'),
 ('운영 결정·롤백 조건','상태 Proposed, probe/in_sample=true/decision_eligible=false, MAIN unchanged. 현재 포인터와 frozen 제품 파일 해시를 다시 확인했다. 제품을 수정하거나 승격하지 않았으므로 운영 롤백 작업은 필요하지 않다. 개선 후보·변형 질문 재실행·속도 비교는 결과를 보기 전 새 ADR에서 동결한다. GENOS 연결·반입·배포·실행을 수행하지 않았다.'),
 ('재현 명령','동결 실행은 `06_TOOLS/EXPERIMENTS/adr_0705/run.py`, 사후 진단은 `analyze.py`다. 기존 실행 폴더 덮어쓰기를 거부하므로 재실행은 새 ADR을 사용한다. [동결 파일](artifacts/design/freeze.json)과 [원시 압축 영수증](artifacts/run-001/raw-archive.json)을 확인한다. 원시 provider/runtime은 `raw.tar.gz`로 무손실 압축했고 모든 구성 파일의 바이트·해시를 검증한 후 중복 원본만 정리했다. 새 빈 디렉터리로 복원할 수 있다. 준비 검사와 본 실행의 로그는 구분했다.')]
fm=f'---\nadr_id: ADR-0705\ntitle: MAIN48 CM 최다 호출 질문 1회 병목 진단\nstatus: Proposed\ndecision_date: 2026-10-09\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m["reservation"]["created_at"]}\nupdated_at: {m["reservation"]["updated_at"]}\nowner: Codex\nwork_status: in_progress\n---\n\n'
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {h}\n\n{body}' for i,(h,body) in enumerate(parts,1))+'\n')
q=m['questions'][0];qp=A/'실험'/q['file']
qp.write_text('# cm-018 · MAIN48 단일 요청 병목 진단\n\n'+question+'\n\nrun-001 / measured-main48 / Qwen3.8 Parasail FP8. 알려진 사례 probe이며 정답을 제품 입력에 넣지 않았다. 기준답변·독립 judge 채점은 수행하지 않았다.\n\n'+table+'\n'+calltable+'\n실제 요청은 [request.json](../artifacts/run-001/request.json), 실제 반환은 [result.json](../artifacts/run-001/result.json), 모든 system/user/schema/provider 원응답·중간 호출은 [raw.tar.gz](../artifacts/run-001/raw.tar.gz)에 원바이트로 보존했다. [구성 파일 해시·복원](../artifacts/run-001/raw-archive.json). 보고서에 같은 입력 본문을 반복 복제하지 않는다.\n\n회수 단계: catalogue15,777 → acquired0 → presented0, adopted0. [exact identity 원장](../artifacts/run-001/retrieval-ledger.json.gz). golden recall은 미채점이며0%로 추정하지 않는다.\n\n실행 실패 HTTP422 / MODEL_DECISION_UNRESOLVED. 약칭 해소 실패·구조 다음 페이지 손실·반복 복귀가 원문 확보 없이 이어졌다. [직접 확인](../artifacts/run-001/root-cause.json). 새 호출로 재시도하지 않았다.\n')
qp.write_text('# cm-018 · MAIN48 단일 요청 병목 진단\n\n'
    '## 1. 실행 메타\n\nrun-001 / measured-main48 / Qwen3.8 Parasail FP8. 알려진 사례 probe. 신규 제품 요청1회, 준비 검사0모델 호출.\n\n'
    '## 2. 사용자 질문 원문\n\n'+question+'\n\n'
    '## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n기준답변을 불러오거나 모델에 전달하지 않았다. 이번은 지연 진단이며 법률 정답률을 채점하지 않는다.\n\n'
    '## 4. 제품 입력을 구성한 원값\n\n실제 입력은 [request.json](../artifacts/run-001/request.json), 프로필은 [profile.json](../artifacts/run-001/profile.json), 세대와 코드 지문은 [freeze.json](../artifacts/design/freeze.json)에 보존했다. 승인 공개65문서 범위다.\n\n'
    '### 회수·탈락 단계 원장 — run·arm별\n\nrun-001 / measured-main48: catalogue15,777 → acquired0 → presented0, adopted0. [exact identity 원장](../artifacts/run-001/retrieval-ledger.json.gz). golden recall은 미채점이며0%로 추정하지 않는다.\n\n'
    '## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n'+calltable+'\n'
    '모든 system/user/schema/provider 원응답은 [raw.tar.gz](../artifacts/run-001/raw.tar.gz)에 원바이트로 보존했다. [구성 파일 해시·복원](../artifacts/run-001/raw-archive.json). 같은 입력 본문을 반복 복제하지 않는다.\n\n'
    '## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n앞단4회·탐색10회(수정2회 포함)의 모든 입력과 출력이 위 압축 기록에 있다. [작업별 시간·출력 진단](../artifacts/run-001/diagnostic.json).\n\n'
    '## 7. 채점 호출과 반복 판정\n\n채점 호출0회, 독립 judge·정답률·반복 성능 통계 없음. 추가 제품 실행도 하지 않았다.\n\n'
    '## 8. 사례 최종 판정\n\n'+table+'\n'
    '실제 반환은 [result.json](../artifacts/run-001/result.json). HTTP422 / MODEL_DECISION_UNRESOLVED로 답변 실패, 병목 진단 완료. 약칭 해소 실패·구조 다음 페이지 손실·반복 복귀가 원문 확보 없이 이어졌다. [직접 확인](../artifacts/run-001/root-cause.json). MAIN 변경 없음.\n')
q['sha256']=sha(qp)
m['results']['error_taxonomy']=[{'type':'retrieval_miss','case_id':'cm-018','detail':'Explicit abbreviated law failed identification despite authorized stored original; paginated structure catalogue truncated in law menu; repeated RETURN_TO with zero acquisition; HTTP422 before assessment'}]
m['results']['diagnostic_success']=bool(d['main_unchanged'] and d['frozen_files_unchanged'] and d['profile_same_as_recorded_main48_service'] and r['model_calls']==len(r['usage']))
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# CM 최다 호출 사례 진단\n\n| 질문 | 실행 | 모델 | 시간 | 정답 채점 |\n|---|---|---:|---:|---|\n| [cm-018](질문-001-cm-018.md) | HTTP422 실패, 진단 완료 | 14회 | 157.538초 | 미실시 |\n\n실행1회, 추가 제품/평가 호출 없음. MAIN 변경 없음. 원인·한계는 [결정문](../README.md)을 따른다.\n')
index=R/'04_EXPERIMENTS/ADR/README.md';s=index.read_text();link='- [ADR-0705 MAIN48 CM 최다 호출 질문 병목 진단](ADR-0705-cm-max-call-bottleneck-probe/README.md) — CM018 1회, 14호출·157.538초·HTTP422; 약칭/페이지/반복 복귀와 초기 준비 병목, MAIN 불변.'
if 'ADR-0705-cm-max-call-bottleneck-probe/README.md' not in s:index.write_text(s.rstrip()+'\n'+link+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0705','created_at':m['reservation']['created_at'],
    'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen single-request diagnosis and preserved failure; raw provider/runtime in verified archive','contains_raw_prompts_and_outputs':p.name=='raw.tar.gz'}
             for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']})
print('Failed request and completed diagnosis recorded; MAIN unchanged')
