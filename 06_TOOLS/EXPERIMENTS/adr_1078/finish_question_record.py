"""Authorized administrative finalization; preserve all evaluated inputs/results."""
from common import *
from datetime import datetime,timezone
import gzip
import shutil
import subprocess

folder = ADR/'artifacts/administrative-finalization'
folder.mkdir(exist_ok=False)
question = ADR/'실험/질문-001-fsc-hard-005.md'
manifest_path = ADR/'실험/manifest.json'
manifest = read(manifest_path)
assert manifest['reservation']['status']=='completed' and manifest['results']['status']=='failed'
before_manifest = manifest_path.read_bytes()
before_question = question.read_bytes()
before_index = (ADR/'artifacts/manifest.json').read_bytes()
with gzip.open(folder/'question-scaffold-before.md.gz','xb') as out:out.write(before_question)
(folder/'source-manifest-before.json').write_bytes(before_manifest)
(folder/'artifact-manifest-before.json').write_bytes(before_index)
shutil.copyfile(ADR/'artifacts/final-validation.txt',folder/'final-validation-before.txt')
freeze = read(DESIGN/'freeze.json')
protected = {p:sha(ADR/'artifacts'/p) for p in ('run-001/result.json','run-001/state-pairs.jsonl.gz',
    'run-002/result.json','run-002/optimized/result.json','run-002/optimized/transport-checks.json')}
inventory = read(DESIGN/'secondary-inputs.json')
request = read(ROOT/inventory['request']['path'])
native = read(ADR/'artifacts/run-002/optimized/result.json')
reservation = read(ADR/'artifacts/run-002/optimized/reservation.json')
question.write_text(f'''# 질문 001 — fsc-hard-005

## 1. 실행 메타

- ADR: ADR-1078 / experiment: ADR-1078-experiment-v1 / case: fsc-hard-005
- run-001: 법률질문 없이 신규280개 합성 상태쌍 검사. 아래 실제질문 재생은 run-002 / optimized다.
- 실행 시각: 보존한 [native reservation](../artifacts/run-002/optimized/reservation.json)의 실제시각.
- 원본 상태: exact. 질문·wire·provider응답은1075의원본hash로결속했고,새native재구성은36번째요청에서실패했다.
- 신규 제품/중간/평가 모델 호출0. 과거 qwen/qwen3.8-27b / Parasail 응답35개만재생했다.

## 2. 사용자 질문 원문

```text
{request['json']['question']}
```

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

법률정답 채점은하지않았다. 원래1075완료답변은 재현성 비교용 기존관측값이며 정답으로간주하지않는다. 이번재생은최종답변도미완주다. 원본경로와hash는 [입력목록](../artifacts/design/secondary-inputs.json)의 response에있다.

## 4. 제품 입력을 구성한 원값

원본질문과허용문서ID65개는입력목록의 request에,전체wire/schema/응답38개와최종답변은같은목록의calls/response에있다. 대량본문을중복복사하지않으며각원본은정확한path/hash로보존한다. 새run의원문·행동·자료전달은native journal과35개view-001..035검사에남아있다.

### 회수 전 전체·후보·제시 규모

```json
{{"corpus_total":null,"before_filter":null,"after_filter":null,"presented_navigation_windows":35,"reason":"Known transcript reconstruction, not a new retrieval/golden-recall benchmark"}}
```

### 회수 좌표·조문·정의·Wiki·관계 — 전체

원문·좌표·관계의전체값은입력목록의original_journal과새실패journal에있다. 원본에대한35개frame data/actions/location hash가전부일치했다. 자료를정답으로재채점하거나새개념으로승인하지않았다.

### 회수·탈락 단계 원장 — run·arm별

| run | arm | stage | kind | before | +added | -discarded | after | gold before | gold + | gold - | gold after/total | recall | 대표 탈락 이유 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| run-002 | optimized | NAVIGATION | known replay | 35 | 0 | 0 | 35 exact | 해당없음 | 해당없음 | 해당없음 | 해당없음 | 해당없음 | 법률gold평가없음 |

```json
{{"stage_ledger_artifact":null,"discarded_gold_and_reasons":null,"gold_visible_to_product":false,"reason":"No new golden retrieval scoring; all original frame values remain in hash-bound journals"}}
```

## 5. 제품 모델 호출 — run·arm별 실제 원문

### run-002 / optimized / system

원본35개요청의system은입력목록 calls[0:35].wire에바이트그대로있다.36번째도system은같았으나schema/alias가달라응답전차단됐다. 새모델에는전송하지않았다.

### run-002 / optimized / user

원본user는같은wire에,실제재생user는실패journal의model_attempt.request_json에있다. 최초35개는보호내용exact이고36번째는V1/V2역할별칭47경로차이가있다. [차이 원값](../artifacts/run-002/optimized/post-failure-difference.json).

### run-002 / optimized / schema·tool

```json
{{"source":"artifacts/design/secondary-inputs.json calls[].wire","actual":"run-002/optimized native journal model_attempt.request_json","protected_requests_exact":35,"schema_mismatch_call":36,"response36_delivered":false}}
```

### run-002 / optimized / provider 원응답·structured output·usage·지연

```json
{{"new_model_calls":0,"new_tokens":0,"new_cost_usd":0,"literal_prior_responses_delivered":35,"response_rewrite":false,"completed":false,"view_seconds":{native['view_seconds']},"request_seconds":{native['request_seconds']}}}
```

원래provider/raw/output/usage는입력목록의각response에보존했다. 역사적토큰을신규사용량으로세지않는다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

```json
[]
```

신규중간모델호출과자동재시도없음.

## 7. 채점 호출과 반복 판정

### judge system/user — 기준답변 포함

```json
[]
```

### judge 원응답과 최종 다수결

```json
{{"judge_calls":0,"majority_vote":null,"legal_quality_certified":false}}
```

## 8. 사례 최종 판정

| run | arm | 정답 | 핵심 근거 | 실패 유형 |
|---|---|---:|---|---|
| run-002 | optimized | 평가안함 | 35frame·35요청exact,36번째schema/alias불일치 | other: harness protected alias mismatch |

- 사전 지정 비교쌍의 신규 정답·회귀: 법률채점없음. 원래38응답/답변완주요건실패.
- 공통 실패 유형: other — HARNESS_PROTECTED_VIEW_PREVIEW_ALIAS_SWAP.
- 코드·기록으로 확인한 직접원인: randomV UUID와고정previewV ID가같은정렬namespace에서V1/V2순서를바꿨다. cache만의현상이라고단정하지않는다.
- 다음 분기 가설: canonical preview/원장view 역할의일대일대응을검증하고변경alias를원응답이참조하면중단하는새비교계약. 이실패의기준은변경하지않는다.

관리마감: 이파일은실험종료표시뒤누락된질문scaffold를원시기록으로채운행정정정이다. 원래실패·후보·동결기준·runraw를바꾸지않았으며별도finalization receipt를남겼다.
''')
subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(ADR)],cwd=ROOT,check=True)
updated = read(manifest_path)
before_copy,after_copy = read(folder/'source-manifest-before.json'),dict(updated)
before_copy.pop('questions');after_copy.pop('questions')
assert before_copy == after_copy
assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
assert all(sha(ADR/'artifacts'/p)==h for p,h in protected.items())
put(folder/'receipt.json',{'kind':'ADMINISTRATIVE_FINALIZATION_ONLY',
    'authorized_by':'Parent root explicit instruction after reporting missed question scaffold',
    'completed_at':datetime.now(timezone.utc).isoformat(),
    'scope':'Question prose, its manifest hash and artifact index only; no evaluation outcome or criterion revised.',
    'source_before_sha256':sha(folder/'source-manifest-before.json'),'source_after':bound(manifest_path),
    'question_after':bound(question),'protected_result_hashes':protected,
    'original_failure_preserved':True,'frozen_inputs_unchanged':True})
paths = [p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json'
    and p.name not in ('final-validation.txt','graph-check.txt')]
paths += list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1078').glob('*.py'))
paths.append(ROOT/'06_TOOLS/EXPERIMENTS/adr_1078/state-matrix.json')
put(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1078',
    'created_at':manifest['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
    'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
        'description':'Preserved failed experiment or authorized administrative question finalization; frozen criteria/runraw unchanged.',
        'contains_raw_prompts_and_outputs':'run-002' in str(p)} for p in sorted(paths)]},replace=True)
print('Question scaffold finalized with explicit administrative receipt; experiment outcome unchanged')
