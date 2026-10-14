from pathlib import Path
import json,hashlib,sqlite3,tarfile,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0708-grounded-title-body-retest';O=A/'artifacts/run-001';C=O/'body-retest/body-content-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(C/'result.json');m=read(A/'실험/manifest.json');s=read(O/'summary.json')
p=next((C/'runtime').rglob('journal.sqlite'));db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
events=[{'kind':k,'payload':json.loads(v)} for k,v in db.execute('SELECT kind,payload_json FROM event ORDER BY seq')];db.close()
hint=next(e['payload'] for e in events if e['kind']=='LAW_TITLE_HINTS');entry=next(e['payload'] for e in events if e['kind']=='REQUEST_ENTRY_ACCEPTED')
trace={'law_title_hints':hint,'entry':entry,'first_discovery':next(e['kind'] for e in events if e['kind'] in ('LAW_FULLTEXT_DIRECTORY','LAW_STRUCTURE_DIRECTORY')),
 'rejections':[e['payload'].get('error') for e in events if e['kind']=='LAW_DECISION_REJECTED'],'result_status':r['http_status'],'physical_attempts':r['attempts'],'model_seconds':sum(a['seconds'] for a in r['attempts']),
 'final_answer_completed':False,'product_code_changed':False,'main_unchanged':r['active_pointer_before']==r['active_pointer_after']}
put(O/'trace-review.json',trace)
summary=f"HTTP{r['http_status']} / {r['request_seconds']:.3f}초 / 실제 LLM {r['model_calls']}회. 제목 힌트0개 → FULLTEXT 선택 → 구조 검색 선행 없이 본문 검색 실행은 확인했다. 이후 같은 RESEARCH 검색식을 반복하고 보정도 동일하여 최종 답변은 실패했다."
sections=[
 ('결정 요약',summary+' 속도 개선·최종 답변 성공·MAIN 반영으로 보고하지 않는다.'),
 ('문제와 변경 전 구조','ADR0707의 본문 질문은 후보의 첫 해석 전에 두 upstream429로 실패했다. 해당 실행의23.6초를 검색 성능으로 볼 수 없어 같은 코드로 질문1개만 새로 동결했다.'),
 ('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json): 제목 없는 본문 요청에서 첫 FULLTEXT 선택과 전체 요청을 확인한다. 동일 코드·모델·데이터이며 추가 재실행/튜닝은 하지 않는다. 난이도 예산 정책은 만들지 않는다.'),
 ('실험 설계','완료 부모 ADR0707/title-entry에서 retests 분기, arm body-retest 하나, 질문1개/1회. 모든 제품 파일 바이트 동일을 freeze 전에 확인했다. 비교군을 새로 실행하지 않았고 이전 실패와 속도를 비교하지 않는다.'),
 ('데이터·모델·재현성','공개 합성 본문 질문, 공개65문서, term-source-8729f978a28924cb8c5b. Qwen3.8 qwen/qwen3.8-27b / OpenRouter Parasail FP8 / reasoning none / fallback 없음 / ExperimentClient. [정확 코드·프로필·원문·실행기](artifacts/design/freeze.json). 현장 GENOS 아님.'),
 ('결과',summary+'\n\n[요청·최종 응답·시도별 계측](artifacts/run-001/body-retest/body-content-001/result.json), [앞단/첫 검색/거절 원인](artifacts/run-001/trace-review.json). 제목 대조는 '+f"{hint['seconds']*1000:.3f}ms, 모델0회. 앞단1회와 탐색3회(보정1회 포함), 모델 합계{trace['model_seconds']:.3f}초, 요청의 나머지{r['request_seconds']-trace['model_seconds']:.3f}초다. 후자는 준비·검색·저장 등을 포함하며 개별 원인으로 단정하지 않는다."),
 ('사례별 오류 분석','첫 fulltext 결과에서 관련 후보를 찾았지만 모델이 원문을 읽겠다는 이유로 RESEARCH를 골랐다. 다음 응답과 보정에서도 같은 검색식을 반복했다. 서버는 unchanged fulltext expression으로 두 번 거절하고 SOURCE_INVESTIGATION_INCOMPLETE로 종료했다. 이미 제시된 읽기 도구로 진행해야 하는 이후 행동 선택의 문제다. 앞단 제목 힌트/검색 도구 분류 성공과 최종 답변 실패를 구분한다.'),
 ('비용·지연·회수 규모','[사용량/회수 집계](실험/manifest.json), [회수 단계 원장](artifacts/run-001/retrieval-ledger.json.gz). 확보·모델 전달·채택은 별도며 HTTP422를 빠른 답변으로 취급하지 않는다. 1회/승인 gold 없음으로 p50/p95·정답률·gold recall은 미측정이다.'),
 ('해석','사용자 문장에 맞춰 구조 검색과 fulltext를 고르는 앞단은 실제로 연결됐다. 제목 매칭을 별도 LLM으로 판단하지 않는다. 그러나 첫 검색 성공만으로 읽기·채택·최종 답변의 성공이 보장되지 않는다. 후속 개선은 이미 얻은 후보를 읽지 않고 같은 검색을 반복하는 행동 선택을 다뤄야 한다.'),
 ('한계와 일반화 가능 범위','공개 한 문항 재검증, provider 가용성 및 모델 출력 변동이 있다. 일반 정확도·안정적 속도·망분리 현장 성능은 인증하지 않는다. 부모의 단위/계약46통과 기록을 참조하되 이번에 반복 테스트한 것으로 세지 않는다.'),
 ('운영 결정·롤백 조건','Proposed / probe / in_sample=true / decision_eligible=false. 코드 수정0, MAIN 활성 포인터48 유지, Git main 병합·제품 MAIN 승격·GENOS 적용0. 남은 탐색 오류를 해결하기 전 서비스 완료로 표시하지 않는다. 원시 실패와 부모 기록은 보존한다.'),
 ('재현 명령','동결 run.py --arm body-retest --case body-content-001. 기존 출력 덮어쓰기 금지; 다음 호출은 새 ADR. [압축 원본](artifacts/run-001/raw.tar.gz), [복원·해시](artifacts/run-001/raw-archive.json). 모든 실제 system/user/schema/응답/journal을 보존했다.')]
fm=f'---\nadr_id: ADR-0708\ntitle: 동일 제목 힌트 후보의 본문 첫 검색 재검증\nstatus: Proposed\ndecision_date: 2026-10-09\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m["reservation"]["created_at"]}\nupdated_at: {m["reservation"]["updated_at"]}\nowner: Codex\nwork_status: in_progress\n---\n\n'
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(sections,1))+'\n')
case=read(A/'artifacts/design/dataset.json')['cases'][0]
body=f'''# body-content-001

## 1. 실행 메타

run-001 / body-retest / 동일코드1회 / 실제 외부Qwen·Parasail / MAIN 불변

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

승인 정답/필수근거 미사용. 법률 정답률은 미측정.

## 4. 제품 입력을 구성한 원값

### 회수·탈락 단계 원장 — run·arm별

[원장](../artifacts/run-001/retrieval-ledger.json.gz), [앞단·첫 검색·거절](../artifacts/run-001/trace-review.json). 제목 힌트는 본문 원문 근거가 아니다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

[결과와 개별 실제시도](../artifacts/run-001/body-retest/body-content-001/result.json), [원문 압축본](../artifacts/run-001/raw.tar.gz)의 body-retest/body-content-001/provider/call-*에 exact system/user/schema/provider 응답을 보존했다. [해시·복원](../artifacts/run-001/raw-archive.json).

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

앞단1, 탐색3(보정1 포함). 제목 매칭0. 총4시도, 모두 provider응답을 받았으나 모델행동이 거절돼 최종 실패했다.

## 7. 채점 호출과 반복 판정

judge0회. 원문기반 법률 정확도는 미채점. 실패 이전 검색 선택의 실제연결만 확인.

## 8. 사례 최종 판정

{summary}
'''
q=A/'실험'/m['questions'][0]['file'];q.write_text(body);m['questions'][0]['sha256']=sha(q)
(A/'실험/README.md').write_text('# 동일코드 본문 첫 검색 재검증\n\n'+summary+'\n\n[질문](질문-001-body-content-001.md)\n')
m['results']['error_taxonomy']=[{'type':'other','case_id':'body-content-001','arm':'body-retest','detail':'Repeated unchanged RESEARCH proposal after successful first FULLTEXT; repair repeated it; HTTP422'}]
m['results']['engineering_checks']={'identical_product_files':True,'first_fulltext_without_structure':True,'title_match_model_calls':0,'all_physical_calls':4,'final_answer_complete':False};put(A/'실험/manifest.json',m)
files=[p for name in ('provider','runtime') for p in sorted((C/name).rglob('*')) if p.is_file()];rows=[{'path':str(p.relative_to(O)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
archive=O/'raw.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
 for p in files:tar.add(p,arcname=str(p.relative_to(O)),recursive=False)
with tarfile.open(archive,'r:gz') as tar:
 for row in rows:assert hashlib.sha256(tar.extractfile(row['path']).read()).hexdigest()==row['sha256']
put(O/'raw-archive.json',{'archive':str(archive.relative_to(R)),'sha256':sha(archive),'files':rows,'verified':True,'restore':'Extract to a new empty directory; verify each file hash; do not overwrite completed experiment paths.'})
for name in ('provider','runtime'):shutil.rmtree(C/name)
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0708','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen identical-code rerun with exact failure records','contains_raw_prompts_and_outputs':p.name=='raw.tar.gz'} for p in sorted((A/'artifacts').rglob('*')) if p.is_file() and p.name!='manifest.json']})
p=R/'04_EXPERIMENTS/ADR/README.md';p.write_text(p.read_text().rstrip()+'\n- [ADR-0708 同一 코드 본문 검색 재검증](ADR-0708-grounded-title-body-retest/README.md) — 첫FULLTEXT 실제 확인, 반복검색 보정 실패HTTP422; MAIN불변.\n')
print(summary)
