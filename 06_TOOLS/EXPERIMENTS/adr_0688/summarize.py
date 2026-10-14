from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,statistics,xml.etree.ElementTree as ET,gzip,tarfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def suite(name):
 p=O/(name+'.xml');cases=list(ET.parse(p).getroot().iter('testcase'))
 return {'artifact':str(p.relative_to(R)),'sha256':sha(p),'tests':len(cases),
  'failures':[c.get('name') for c in cases if c.find('failure') is not None or c.find('error') is not None]}
f=read(D/'freeze.json');code=R/f['code_root'];b=read(D/'baseline.json')
for p,h in f['shared_files'].items():assert sha(R/p)==h,p
for p,h in f['serving_files'].items():assert sha(code/p)==h,p
base=read(D/'baseline-snapshot-receipt.json')
for p,h in base['files'].items():assert sha(R/base['code_root']/p)==h,p
suites={group:{arm:suite(group+'-'+arm) for arm in ('baseline','integrated')} for group in ('primary','existing','regression')}
checks={'required_18':suites['primary']['integrated']['tests']==18 and not suites['primary']['integrated']['failures'],
 'same_followup_27':all(suites['existing'][a]['tests']==27 and not suites['existing'][a]['failures'] for a in ('baseline','integrated')),
 'same_regression_61':all(suites['regression'][a]['tests']==61 and not suites['regression'][a]['failures'] for a in ('baseline','integrated')),
 'frozen_code_and_fixture_hashes':True,'active_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']}
probes=[read(p) for p in sorted((O/'probe').glob('*/*/result.json'))]
assert len(probes)==8 and sum(p['calls'] for p in probes)<=24
usage=[u for p in probes for u in p['usage']]
for u in usage:
 assert u['upstream_provider']=='Parasail' and u['model']=='qwen/qwen3.8-27b'
 assert u['thinking_tokens']==0
reported=[u for u in usage if u.get('input_tokens') is not None]
accounting={'physical_calls':sum(p['calls'] for p in probes),'reported_usage_calls':len(reported),'unreported_usage_calls':len(usage)-len(reported),
 'input_tokens_reported':sum(u['input_tokens'] for u in reported),'output_tokens_reported':sum(u['output_tokens'] for u in reported),
 'reported_cost_usd':sum(u['cost_usd'] for u in reported),'total_cost_confirmed':len(reported)==len(usage),
 'latency_seconds':[u['seconds'] for u in usage]}
probe_summary=[{'case':p['case'],'arm':p['arm'],'calls':p['calls'],'valid':all(s['valid'] for s in p['steps']),
 'original_delivered':p['original_delivered'],'actions':[s['decision']['next_action'] for s in p['steps'] if s.get('decision')],
 'failures':[s for s in p['steps'] if not s['valid']],'artifact':str((O/'probe'/p['case']/p['arm']/'result.json').relative_to(R))} for p in probes]
result={'schema_version':'followup-structure-functional-audit-v1','strict_success':all(checks.values()),'checks':checks,'suites':suites,
 'candidate_tests_passed':106,'baseline_new_features_supported':0,'baseline_existing_passed':88,
 'supplemental_in_sample_probe':probe_summary,'usage':accounting,'source_check':str((O/'local-source-check.json').relative_to(R)),
 'limitations':['Synthetic functional contracts, not legal-answer accuracy or GENOS field certification.',
 'Both arms returned finish_reason=error with null content and no usage for missing-coordinate. Cause is unknown from the upstream response; navigation recovery is unmeasured for that model case.',
 'Three successful model scenarios already worked in the baseline with existing structure tools. No semantic/model navigation improvement rate is claimed.',
 'Primary baseline failures include absent new fields/helpers and behavior; their count is not a legal quality score.',
 'Maintained 61 regression subset excludes 18 previously documented old native/completion fixture cases.',
 'Stable candidate tool via run_tool rejects pre-existing WORKSPACE receipt drift. Exact working tool hash and truthful baseline copy receipt are preserved; activation receipt was not changed.',
 'Unrelated older-engine nfs_data_probe pin discrepancy remains outside the native v6 scope. No selected MAIN pointer or GENOS deployment changed.']}
assert result['strict_success'];put(O/'result.json',result)
# Preserve raw input/output once, with lossless compression and restore hashes.
compressed=[]
for p in sorted(O.glob('probe/*/*/model')):
 archive=p.parent/'model.tar.gz'
 with tarfile.open(archive,'w:gz') as t:t.add(p,arcname='model')
 files={str(x.relative_to(p.parent)):sha(x) for x in p.rglob('*') if x.is_file()}
 put(p.parent/'model-archive-receipt.json',{'archive':str(archive.relative_to(R)),'sha256':sha(archive),
  'restoration':'tar -xzf model.tar.gz restores model/; check these uncompressed file SHA-256 values.', 'files':files})
 # Only newly created reproducibly archived experiment raw files are removed.
 import shutil
 shutil.rmtree(p)
for p in sorted(O.rglob('*.log')):
 raw=p.read_bytes();packed=p.with_suffix(p.suffix+'.gz')
 with gzip.open(packed,'wb') as stream:stream.write(raw)
 compressed.append({'archive':str(packed.relative_to(R)),'sha256':sha(packed),'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)})
 p.unlink()
for p in (Path('/tmp/adr688-dev.txt'),Path('/tmp/adr688-dev2.txt'),Path('/tmp/adr688-dev3.txt')):
 if p.exists():
  target=O/('development-'+p.name+'.gz')
  with gzip.open(target,'wb') as stream:stream.write(p.read_bytes())
put(O/'compression-receipts.json',compressed)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={a:{'status':'complete','new_required_tests':18,
 'new_passed':18-len(suites['primary'][a]['failures']),'unchanged_regressions_passed':88,
 'supplemental_navigation_cases':4,'supplemental_original_delivered':sum(p['original_delivered'] for p in probes if p['arm']==a)} for a in ('baseline','integrated')},
 comparisons=[{'baseline':'baseline','candidate':'integrated','metric':'New functional contracts; existing 88 unchanged contracts remain passing',
 'baseline_value':0,'candidate_value':18}],judge_disagreements=None,usage=accounting,
 latency={'measurement':'Observed eight upstream physical calls, not GENOS service latency','seconds':accounting['latency_seconds']},
 error_taxonomy=['upstream_incomplete_response_unknown_cause','new_fields_not_in_baseline','legacy_fixture_exclusions','unrelated_workspace_receipt_drift'])
# Complete cases without copying raw model messages into six reports.
for q in m['questions']:
 p=A/'실험'/q['file'];t=p.read_text()
 replacements={'## 2. 제품 요청':'## 2. 사용자 질문 원문','## 3. 기준답변':'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',
  '## 4. 제품 입력의 원값':'## 4. 제품 입력을 구성한 원값','## 5. 제품 모델 호출':'## 5. 제품 모델 호출 — run·arm별 실제 원문',
  '## 6. 중간 LLM 호출':'## 6. 중간 LLM 호출 — router/compiler/verifier/repair',
  '## 7. 채점 호출':'## 7. 채점 호출과 반복 판정','## 8. 최종 판정':'## 8. 사례 최종 판정'}
 for old,new in replacements.items():t=t.replace(old,new)
 t=t.replace('## 5. 제품 모델 호출', '### 회수·탈락 단계 원장 — run·arm별\n해당 없음: 색인·회수 품질 변경 없이 행동 선택과 정확한 READ 범위를 감사한다. 모든 제시 행동은 probe turn-*-offered.json에 있다.\n\n## 5. 제품 모델 호출',1)
 t=t.replace('측정 전 결과 미기록.','후보18개 신규 기능 계약과 기존88개 회귀 통과. 보조 모델은3개 시나리오×2arm 원문 전달 성공, 조문 부재 시나리오×2arm upstream 빈 오류 응답으로 확인 불가.')
 p.write_text(t);q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
# Reports explain the only adoption decision: merge scoped working code.
(A/'README.md').write_text(f'''---
adr_id: ADR-0688
title: 후속 구조 조회의 화면·행동 기록, 반복 탐색 전환과 실패 원인 구분
status: Accepted
decision_date: 2026-10-08
phase: audit
in_sample: false
decision_eligible: true
main_wiring: unchanged
created_at: {m['reservation']['created_at']}
updated_at: {m['reservation']['updated_at']}
owner: Codex
work_status: in_progress
---

# 후속 구조 탐색의 기록·반복 회복·실패 원인 연결

## 1. 결정 요약
사전 고정한 기능 감사 기준을 충족해 scoped 작업 코드 통합을 채택한다. 활성 MAIN45와 GENOS는 변경하지 않는다. 신규18개와 기존88개 검사106개 통과. 실제 모델 보조 실험은 법률 품질 판정 근거로 사용하지 않는다.

## 2. 문제와 변경 전 구조
앞선 작업 코드에는 조문 번호·제목 조회와 실제 문서 구조·READ가 있었지만 입력 필드와 결과가 행동/진행 화면에 연결되지 않았고, 다른 Fulltext 페이지를 얻는 것만으로 계속 진행할 수 있었다. 조회 부재·모호성·원문 연결 실패를 구분하지 않았다. 기준은 이 작업 코드274파일의 정확한 복사본이며 선택된 frozen MAIN45를 기준 코드로 오인하지 않는다.

## 3. 가설과 사전 판정 기준
[호출 전 기준](artifacts/design/criteria.json)을 그대로 적용한다. 구조 필드·현재 경로·실패 원인의 기록/표시, 같은 문서·검색식에서 새 원문 없이3페이지 후 구조 회복, 복귀/재개 보존, 원문·권한·해시 회귀 없음이 필수다. 변경된 페이지 ID라도 이미 전달한 원문 span이면 반복 회수 상태를 초기화하지 않는다. 모델 의미 오판과 upstream 오류는 보조 관측에 기록하며 기능 감사 기준과 분리한다.

## 4. 실험 설계
기준274파일 복사본과 research-only integrated rev-001을 같은 합성 fixture·고정 검사로 비교한다. 신규18개 기능/소비자 검사와 기존27+61개 회귀다. 유지된61개 외의 과거18개 fixture 오류 제외 목록은 [실행 계획](artifacts/design/execution-plan.json)에 결과 확인 전 고정했다. 부모는 완료된 ADR0683 core-route, ADR0681은 의존 관계다. 후보 모듈을 작업/서빙 registry에서 자동 선택하지 않았다.

## 5. 데이터·모델·재현성
[동결 코드와 공유 fixture/tool 해시](artifacts/design/freeze.json), [기준 inventory](artifacts/design/baseline-snapshot-receipt.json)를 따른다. 외부는 새로 작성한 합성 문서와4질문만 사용했다. Qwen3.8 / Parasail FP8 / reasoning none / temperature0 / fallback없음. arm 순서를 교대했고 case/arm당 최대3호출, 전체 최대24를 호출 전에 고정했다. 실제8호출이다. 실제 자본시장법 확인은 로컬 원문/구조 메타데이터 읽기 전용으로 수행했다. 사내 자료·사진의 현장 질문을 외부 모델에 보내지 않았다.

## 6. 결과
| arm | 신규 기능 계약 | 기존 회귀 | 보조 모델 원문 전달 |
|---|---:|---:|---:|
| baseline | 0/18 | 88/88 | 3/4 |
| integrated | 18/18 | 88/88 | 3/4 |
신규필드/API 부재를 포함한 기능 계약 수이며 정답률 개선 수치가 아니다. 실제 로컬 자본시장법 제6조는 unit59 / 제1편→제6조 / 금융투자업을 Fulltext·법률 전문 읽기 없이 직접 지정했다. 결과·원자료는 [result.json](artifacts/run-001/result.json)과 [사례별 원기록](실험/README.md)에 있다.

## 7. 사례별 오류 분석
조문 부재 보조 모델 사례는 양쪽 모두 finish_reason=error, content=null, usage 없음으로 실패했다. 원응답에 원인 상세가 없어 원인을 추정하지 않는다. 누락/중복/분기/원문 연결 실패의 도구 계약과 현재 목차 보존은 자동 감사로 통과했지만 이 사례의 실제 모델 후속 행동은 확인하지 못했다. 기준의3성공 시나리오도 원래 구조 도구로 읽기에 성공해 모델 탐색 개선을 입증하지 않았다. 개발 단계의 fixture 참조 오류·미갱신 후보 pin 로그도 압축 보존했다.

## 8. 비용·지연·회수 규모
8개 물리 호출 중6개만 usage를 보고했다. 보고된 입력 {accounting['input_tokens_reported']} / 출력 {accounting['output_tokens_reported']} tokens, 비용 ${accounting['reported_cost_usd']:.8f}. 두 오류 호출의 사용량·비용은 미확인이다. 관측 호출 지연은 result.json에 보존하며 GENOS 속도나 비용 개선을 주장하지 않는다. corpus/index/ranking을 바꾸지 않아 retrieval recall 원장은 해당 없다. 실제 제시 행동·조회 결과·READ span은 turn별 offered.json/result.json에 전부 보존했다.

## 9. 해석
세 요청의 도구·상태·화면 계약을 충족했다. 실제 법률 답변의 판단 품질과 GENOS 내부 모델 성능은 별도다. Fulltext 회복 제한은 다른 문서/검색식과 실제 새 원문 전달을 독립 처리하며 과거 메뉴로 돌아가도 현재 제한을 보존한다.

## 10. 한계와 일반화 가능 범위
합성 기능 감사106개와 보조4시나리오이며 현장 인증이 아니다. 미확인 upstream 오류2건을 성공으로 처리하지 않는다. 구 workspace 활성화 receipt drift는 고치지 않고 exact candidate tool 해시를 기록해 사용했다. 구 엔진의 nfs_data_probe pin 차이는 native v6와 별개인 기존 문제로 보존했다.

## 11. 운영 결정·롤백 조건
동결된6개 runtime/workflow 파일만 기존 작업 코드에 통합하고 바뀐파일의 engine pin만 갱신한다. unrelated dirty files, 원문 generation, 선택 포인터, 완료 실험을 보존한다. 원문·권한·상태·소비자 회귀 시 저장된 working-backup과 install receipt hash로 이 범위만 원복한다. MAIN 승격·GENOS 현장 ZIP 적용/배포는 수행하지 않았다.

## 12. 재현 명령
`.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0688/run_contracts.py <동결 code root> <execution-plan.json의 계약 파일> --junitxml=<새 실행 경로>`.
모델 원호출은 `model.tar.gz`로 한번 보존하고 SHA/복원 방법은 각 model-archive-receipt.json에 기록한다. 실험 결과 재실행은 새로운 ADR을 선점한다. 기존 결과·모델 호출 경로를 덮어쓰지 않는다.
''')
(A/'실험/README.md').write_text('''# ADR-0688 고정 기능 감사와 보조 모델 원기록

결과는 [result.json](../artifacts/run-001/result.json), 입력·제시 행동은 probe/<case>/<arm>/turn-*-offered.json, 원응답/usage는 model.tar.gz와 model-archive-receipt.json에 보존한다. 도구 요청·실패·READ span은 같은 폴더 result.json을 따른다. 본문·전체 회수 목록을 이 인덱스에 반복 복사하지 않는다.

후보106개 검사 통과, 기준은 기존88개 통과·새 계약18개 미지원. 모델은4시나리오×2arm 8호출 중6개 원문 전달 성공, 조문 부재2개 upstream 빈 응답으로 확인 불가. 법률 의미 채점·judge 없음. 기능 감사와 보조 인샘플 모델 관측을 구분한다.
''')
# Inventory records raw request/response archives and restore receipts explicitly.
items=[]
for p in sorted((A/'artifacts').rglob('*')):
 if not p.is_file() or p.name=='manifest.json' or 'baseline-code' in p.parts:continue
 items.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,
 'description':'Exact functional audit/probe record; compressed raw archives have restoration receipts.',
 'contains_raw_prompts_and_outputs':p.name in ('model.tar.gz',) or p.name.endswith('-offered.json')})
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0688','created_at':m['reservation']['created_at'],'files':items})
print('Accepted functional audit:',106,'candidate tests; model calls',accounting['physical_calls'],'reported cost',accounting['reported_cost_usd'])
