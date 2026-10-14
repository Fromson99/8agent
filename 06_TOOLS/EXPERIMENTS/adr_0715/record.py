"""Record audit findings without changing the tested candidate or MAIN."""
from pathlib import Path
from hashlib import sha256
import json
import xml.etree.ElementTree as ET

R=Path.cwd();A=R/'04_EXPERIMENTS/ADR/ADR-0715-deduction-execution-audit'
sha=lambda p:sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

r=read(A/'artifacts/run-001/result.json')
assert r['oracle']['total']==1200
suites=ET.parse(A/'artifacts/regression.xml').getroot().findall('testsuite')
reg=dict(tests=sum(int(x.attrib['tests']) for x in suites),failures=sum(int(x.attrib['failures'])+int(x.attrib['errors']) for x in suites))
assert reg==dict(tests=25,failures=0)
fail=[x for x in r['records'] if not x['passed']]
assert len(fail)==4
m=read(A/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={
    'baseline':dict(status='complete',mode='Pinned completed parent reference; byte equality verified, no separate effect measurement',revision='ADR0713/rev007'),
    'audited':dict(status='complete',groups=r['groups'],oracle=r['oracle'],regression=reg,all_criteria_met=False)},
    usage=dict(model_calls=0,input_tokens=0,output_tokens=0,cost_usd=0),latency=r['latency_ms'],
    error_taxonomy=[dict(type='other',id='missing-goal-greedy-binding',cases=['missing-prefers-available-branch'],detail='Greedy first relation binding misses a branch needing just Ready(d).'),
                    dict(type='other',id='global-support-cap',cases=['many-independent-supports','unrelated-support-limit'],detail='A ninth valid proof alternative causes global LIMIT_REACHED, including unrelated known targets.'),
                    dict(type='other',id='proof-selection-order',cases=['reorder-independent-rules'],detail='Proof replay compares against one newly selected proof hash; valid old proof fails when only rule ordering changes.')])
put(A/'실험/manifest.json',m)
front=(A/'README.md').read_text().split('---',2)[1]
body='''
# ADR-0715: 연역 엔진 실제 실행 검증

## 1. 결정 요약

**기본 연역과 저장·재사용은 실제 실행에서 동작했다. 완전한 통과는 아니다.** 독립 계산기와 비교한 1,200개 질의는 모두 일치했다. 기존 회귀 검사 25개, 실제 HTTP/SQLite 검사 13개도 통과했다. 추가 경계 사례와 증명 안정성 검사에서 총 4건이 실패했고 원인은 3종류다. 현재 후보의 한계로 남겼으며 제품 코드는 수정하지 않았다. Proposed / MAIN unchanged / decision_eligible=false다.

[실행 결과](artifacts/run-001/result.json) · [검사 인덱스](실험/README.md) · [동결 설계](artifacts/design/plan.json).

## 2. 문제와 변경 전 구조

ADR0713 rev007은 typed Horn 규칙 합성, 증명 검사, SQL 저장, 독립 연구 화면을 구현했다. 기존 25개 계약 검사만으로는 새로운 관계 조합·여러 증명·재시작·다단계 무효화가 충분히 확인되지 않았다. 사용자가 실제 연역 작동을 확인하라고 요청하여 **완료된 후보를 바꾸지 않고** 새 ADR에서 재검증했다.

## 3. 가설과 사전 판정 기준

실행 전에 [plan.json](artifacts/design/plan.json), [입력 35개 및 생성 KB100개](artifacts/design/inputs.json), runner와 candidate hash를 동결했다. 작은 양의 Horn 입력의 독립 정답과 일치하고, 증명 재검사와 HTTP 저장·재사용·철회가 통과해야 한다. 예상과 다른 LIMIT_REACHED도 성공으로 바꾸지 않는다. 결과를 보고 성공 기준이나 표본을 완화하지 않았다.

## 4. 실험 설계

| 대상 | 코드와 데이터 | 역할 |
|---|---|---|
| baseline | 완료된 ADR0713/lab rev007 | 부모 실행 계약과 해시 기준 |
| audited | knowledge_lab 전체가 부모와 byte-identical한 ADR0715 rev001 | 동결 입력 전수 검사 |
| 독립 정답 계산 | 모든 변수에 유한 대상을 대입한 ground 규칙의 집합 고정점 | 양의 Horn 결론 도달 여부만 비교 |

모델·검색정책 A/B 실험은 아니다. 독립 정답 계산기는 엔진의 unify/solve/compose 함수를 사용하지 않는다. 100개 KB 각각 12개 목표를 검사했다. 일부 목표는 같은 KB를 공유하므로 독립된 법률 질문 1,200개로 표현하지 않는다. 부정·예외·권한·기간·가설·정의는 별도 35개 명시 사례로 검사했다.

실제 서버는 WSL loopback 5582에서 동결 create_app으로 시작하고 urllib HTTP 요청을 전송했다. 상태는 `90_RUNTIME/knowledge-lab/adr-0715-http`에 따로 보존했다. 서버를 종료·재시작하여 파생 정리 보존을 확인한 뒤 검증 서버를 종료했다. 사용 중인 5581 연구실 데이터는 변경하지 않았다.

## 5. 데이터·모델·재현성

전부 가상 사실·규칙이다. Controls/Managed/Leverage/ApprovalNeeded/Manager/MustNotify는 관계 연결을 확인하기 위한 가상 업무 규정이며 실제 법률 주장이 아니다. 실제 위키 자연어를 자동 형식화하거나 Qwen의 법률 판단 정확도를 검사한 것이 아니다.

난수 seed는 202610090715다. [binding.json](artifacts/design/binding.json)에 입력·설계·runner·candidate hash를 고정했다. LLM 호출은 0회이며 외부 전송도 없다. 최근 별도 Qwen+RAG 실측 비용은 ADR0714에 있고 이번 검사 결과와 합치지 않는다.

정본은 `artifacts/run-001/result.json`, 실행 I/O는 `artifacts/run-001/io.jsonl.gz`에 무손실 압축했다. 명시 입력은 inputs.json, 합성 및 증명 순서 사례의 결정적 생성 입력은 동결 runner에 있다. 압축 로그에 토큰·인증정보는 없다. 복원: `.venv/bin/python -m gzip -d -c < io.jsonl.gz > io.jsonl`.

## 6. 결과

| 검사 | 통과 / 전체 | 의미 |
|---|---:|---|
| 독립 정답과 결론 비교 | 1,200 / 1,200 | 거짓 증명0·도달 가능 결론 누락0·증명 재검사 실패0 |
| 명시 경계 사례 | 32 / 35 | 새 경로·대상/사건·시점·예외·가설·모순·정의 등 |
| 규칙 합성 | 4 / 4 | X∧Y∧C→D, 가설 유지, 역함의 차단, 기간 교집합 |
| 실제 HTTP/영구 저장 | 13 / 13 | 생성·저장·중복방지·재사용·재시작·철회·이력 |
| 증명 순서 안정성 | 0 / 1 | 규칙 순서 변경 시 정당한 기존 증명 거부 |
| MAIN/부모 코드 보존 | 3 / 3 | 포인터·부모 동결 코드·주요 작업 진입점 동일 |
| 기존 회귀 검사 | 25 / 25 | 이전 구현 계약 재실행 |

HTTP에서 A∧C→D를 저장한 뒤 X,Y,C 사실로 다시 질의했을 때 **증명 root가 저장한 derived ID인 것**을 확인했다. 이어 X∧Y∧C→E를 저장했고 첫 derived ID가 의존성에 들어갔다. 원래 A→B를 철회하자 두 정리가 STALE로 바뀌고 결론을 재사용하지 않았다. 별도 C→D 규칙을 등록하면 독립 경로로 답했다. 단순히 저장 건수만 확인한 검사가 아니다.

## 7. 사례별 오류 분석

1. **조사 경로 선택 누락.** Owns(a,b), Owns(a,c), Tagged(c,d)가 있고 Owns(x,y)∧Tagged(y,z)∧Ready(z)→Eligible(x)일 때 Ready(d) 하나만 더 알면 된다. 실제 missing은 Tagged(b,?z)와 Ready(?z)를 반환했다. 첫 관계에 탐욕적으로 묶여 더 짧은 경로를 놓친다. UNKNOWN 자체는 옳다.
2. **전역 지원 증명 수 제한.** 서로 다른 P0…P8 각각에서 D를 증명할 수 있으면 아홉 번째 지원 경로에서 LIMIT_REACHED가 된다. D와 관계없는 이미 입력된 Known(a)를 물어도 같은 제한으로 답하지 않는다. 틀린 결론을 확정한 것은 아니지만 지식이 늘 때 답할 수 있는 질문까지 중단할 수 있다. 숫자 한도를 없애기보다 목표 관련 탐색과 지원 경로 동등성 처리가 필요하다.
3. **규칙 순서에 따른 증명 거부.** A→D, C→D와 A,C 사실에서 생성한 정당한 증명은 규칙 배열만 뒤집으면 check_proof가 false다. 현재 검사기는 제출한 증명의 타당성뿐 아니라 새로 고른 대표 증명 hash와의 동일성까지 요구한다. 데이터 내용과 기존 증명 전제는 그대로다. 선택 순서와 증명 타당성을 분리할 필요가 있다.

처음 실행 준비에서 frozen revision의 항목에 target_path가 있다고 잘못 가정하여 runner가 kernel import 전에 중단됐다. candidate manifest의 snapshot_path 대응으로 실행기만 수정했다. 실패한 준비물과 이전 binding을 setup-failed-before-kernel에 보존했다. 테스트 입력·기준·제품 코드는 동일하다. snapshot 준비 중 잘못된 CLI 인자를 쓴 부분의 미완성 파일도 보존했다. 실제 검사 결과를 본 뒤 candidate를 수정하거나 재측정하지 않았다.

## 8. 비용·지연·회수 규모

이번 연역 검사 API 비용은 **$0**이며 Qwen 호출 0회다. 소형 가상 사례 1,235건의 엔진 계산 시간은 p50 약0.263ms, p95 약0.806ms, 최대 약8.680ms였다. proof 재검사·HTTP·DB·RAG·모델 시간은 포함하지 않으며 전체 질문 답변 속도로 해석하지 않는다. 검색·회수·원문 생성이 없어 retrieval ledger는 not_applicable이다.

별도 최신 실측 ADR0714는 Qwen3.8/Parasail FP8로 질문 1건에 5회 호출, 입력70,648·출력5,325토큰, $0.02867052였다. 이 한 사례가 서비스 평균을 뜻하지 않는다. 2026-10-09 확인한 공급자 단가 입력$0.24/백만·출력$2.20/백만과 일치한다. 현재 로컬 후보는 자연어 RAG와 형식 연역을 별도 실행하므로 연역에 따른 모델비 절감률은 아직 측정하지 않았다.

## 9. 해석

정형 규칙을 입력하면 경험하지 않은 경로를 증명하고 새 정리를 다음 증명의 재료로 쓸 수 있다. 입력 가정은 CONDITIONAL로 남고 모순·가설·철회 처리를 유지한다. 이번 범위에서 거짓 결론은 관찰되지 않았다. 그러나 경로 탐색과 저장 증명의 안정성은 보완이 필요하므로 사전 전체 성공 기준은 미충족이다.

## 10. 한계와 일반화 가능 범위

임의 자연어 질문→실제 위키 형식화→연역→최종 RAG 답변까지의 통합 품질은 미검증이다. 모델이 자동으로 정확한 규칙을 추출한다는 뜻이 아니며 실제 법률의 예외·개정·권한을 전수 인증하지 않는다. 유한·소형·합성 논리 검사이며 실무 대규모 부하와 GENOS 내부 모델은 별도다. 증명 checker와 solve가 같은 kernel을 공유한다는 점을 양의 Horn 독립 정답 비교로 일부 보완했으나 모든 확장 논리까지 독립 검증한 것은 아니다.

## 11. 운영 결정·롤백 조건

MAIN 미반영. 현재 실행 후보도 수정하지 않았다. 세 보완점은 실패 이력과 함께 후속 수정 대상으로 남겼다. 후보 동작을 바꾸는 수정·재시험은 새 ADR에서 진행해야 한다. 이번 검증용 서버는 종료했고 기존 연구실은 유지한다. 별도 검증 SQL과 원시 기록은 남겼다.

개별 ADR 최종 검증과 전역 graph 결과는 validation-status.json을 따른다. 전역 graph에 남아 있던 과거의 무관한 오류는 소급 수정하지 않으며, 전체 이력 검사가 통과했다고 표현하지 않는다.

## 12. 재현 명령

```bash
cd /home/jin/8-AGENT
.venv/bin/python -m pytest 06_TOOLS/EXPERIMENTS/adr_0713/test_contracts.py -q --override-ini addopts=''
.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0715/audited
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0715-deduction-execution-audit --final
```

이번 실제 실행은 `06_TOOLS/EXPERIMENTS/adr_0715/run.py`였다. 기존 산출물·HTTP sandbox가 있으면 덮어쓰지 않고 중단한다. 재시험은 새 ADR 및 새 출력 경로에 이 입력/동결 코드를 결속해야 한다. 원시 gzip은 Python gzip 또는 gzip -dc로 읽을 수 있다.
'''
(A/'README.md').write_text('---'+front+'---\n'+body)
(A/'실험/README.md').write_text('''# ADR-0715 실행 검사 인덱스

법률 자연어 질문 평가가 아닌 형식 연역·저장 계약 감사다. 질문 파일은0개이며 모든 가상 입력은 [동결 입력](../artifacts/design/inputs.json)에 있다. 정답은 엔진 입력에 전달하지 않았다.

| 그룹 | 통과 / 전체 | 기록 |
|---|---:|---|
| 독립 정답 계산기 비교 | 1200/1200 | [result.json](../artifacts/run-001/result.json) |
| 명시 경계 조건 | 32/35 | result.json의 handcrafted |
| 합성 | 4/4 | result.json의 composition |
| 실제 HTTP·재시작·의존성 | 13/13 | result.json의 http |
| 규칙 순서 변경 | 0/1 | result.json의 proof-stability |
| MAIN·코드 보존 | 3/3 | result.json의 integrity |
| 기존 회귀 | 25/25 | [JUnit](../artifacts/regression.xml) |

3종류 문제에 의한4개 실패를 그대로 남겼다. 실패를 제외한 재집계나 기준 변경은 없다. [결정문](../README.md), [실행 I/O gzip](../artifacts/run-001/io.jsonl.gz), [manifest](manifest.json).
''')
files=[]
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
paths += list((R/'06_TOOLS/EXPERIMENTS/adr_0715').glob('*.py'))
paths += [R/'02_BACKEND/lawrag/research/candidates/adr_0715/audited/candidate.json']
for p in sorted(paths):
    files.append(dict(path=str(p.relative_to(R)),sha256=sha(p),bytes=p.stat().st_size,
                      description='Frozen input, execution receipt, candidate binding or audit runner',contains_raw_prompts_and_outputs=p.name=='io.jsonl.gz'))
am=read(A/'artifacts/manifest.json');am['files']=files;put(A/'artifacts/manifest.json',am)
print('Recorded results with all four failures preserved')
