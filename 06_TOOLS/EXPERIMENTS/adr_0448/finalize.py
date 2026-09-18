"""Render contract audit and link unchanged prior answer counts."""
from binding_runtime import R,T,D,A,C,read,sha
import json

def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 v=read(A/'verification.json');m=read(D/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'verification.json'))
 m['results'].update(status='complete',by_arm={'baseline':{'execution':'not run; exact completed ADR0447/bound is code parent'},'inherited':v},comparisons=[],judge_disagreements=None,usage={'model_calls':0,'external_transmission':False},latency={'not_measured':'ordinary contracts and storage verification, no speed comparison'},error_taxonomy=['DUPLICATE_DERIVED_COORDINATE preserved unresolved:17'])
 write(D/'실험/manifest.json',m)
 sections=[
 ('결정 요약','부모 구조값 상속 연결 구현·계약 확인. 후보에서 기존24472개 하위 항·호·목 중24455개에 저장 부모 scope/key를 결속했고 동일 좌표 충돌17개는 미확인으로 남겼다. 원본 DB/기존 좌표 불변. 새 LLM 실행·답변 평가·MAIN 반영 없음. Proposed/decision_eligible=false.'),
 ('문제와 변경 전 구조','ADR0447은 구형 하위 노드에도 완성된 coordinate_scope/key가 있어야 FIND_ARTICLE을 허용했다. 실제 source_unit의 family/ordinal/surface/parent와 부모 좌표만으로 연결할 수 있는 항·호·목24472개를 미확인으로 막았다. 데이터 소실이 아니라 조회 어댑터 연결 부족이었다.'),
 ('가설과 사전 판정 기준','저장 조문 부모에 연결되는 항·호·목만 상속한다. 기존 좌표·raw JSON 불변, scope 이탈0, 애매한 부모·부분 저장·중복 좌표 확정0, 기존 READ/JUDGE/Result 계약 유지. [사전 동결](artifacts/design-before-snapshot.json). 성능·정답률 전후 비교를 설계하지 않았다.'),
 ('실험 설계','phase=audit, run-001 purpose=audit. 완료된 ADR0447/bound를 코드 부모로 고정하고 inherited 후보만 일반 계약과 실제 저장 연결을 검사했다. baseline 재실행·채점·모델 호출 없음. 과거0447 후보 수 질문은 원출력·실제 요청의 읽기 전용 요약으로 별도 기록한다.'),
 ('데이터·모델·재현성','선택된 로컬 navigation-rag-20260916-v1/generation14의 불변 store.sqlite를 mode=ro로 읽었다. 원문/키/질문을 외부 모델로 전송하지 않았다. 새 후보, 부모0445/0446/0447, 구조 세대·포인터·검사 runner는 해시 결속. [입력](artifacts/input-lock.json). 모의 계약 입력은 기존 numbering template 결과에서 확장 필드만 제거해 구형 형식을 재현했다.'),
 ('결과','14개 계약 통과. 실제230417개 구조 노드 중 기존 scope/key93861개 유지, 상속24455개, 중복 좌표17개 미확인. 상속 소속은 본문22648·부칙517·반복760·별표/부록530. 기존 좌표 변경0·입력 해시 변화0·원본 저장 해시 불변. [정확한 결과](artifacts/verification.json) · [검사](artifacts/tests.json). 이 수치는 구조 연결 계약이며 답변 정확도가 아니다.'),
 ('사례별 오류 분석','부모 좌표가 없는 경우, scope/key 중 일부만 저장된 경우, 다른 문서 부모, 동일 본문좌표 중복은 추정하지 않는다. 실제 충돌17개는 같은 body key로 겹치는 상속을 거절했다. 본문/부칙/반복/별표 소속은 부모 원값 그대로 유지한다. 구형 편·장·절·관757개는 이번 조문 하강 연결 대상이 아니다.'),
 ('비용·지연·회수 규모','신규 LLM0회, 토큰0, retrieval 평가 없음. 기존0447 실행의 질문당 제시/읽기/선택/정답 수는 [별도 집계](artifacts/PRIOR_COUNTS.md). 모의7문서9조문, 근거답변10질문 모두 정답1개. 질문×조문 기준 후보11·읽기11·최종선택10·정답선택10이며 고유 정답 원문은8개. 새로운 후보 결과로 전용하거나 과거 채점11/12를 바꾸지 않았다.'),
 ('해석','RAG가 본문을 재분류하지 않고 구조화 틀이 저장한 부모와 자식 값을 연결한다. 상속값은 matcher의 메모리 투영이며 raw_structure는 원본 그대로다. non-body identity는 부모 저장 key와 자식ID로 구별한다. 후보 코드는 bind_structure→InheritedSession→FIND_ARTICLE→발급 RH→READ/JUDGE→기존 select/assemble/answer 경로로 소비한다.'),
 ('한계와 일반화 가능 범위','복수 정답 조문 조합이나 여러 유사후보 판별 검증 없음. 실제 내부·GENOS 답변 품질 미확인. 부모 구조 오류를 의미적으로 복구하지 않는다. 충돌17개는 별도 구조 점검 대상이다. 편·장·절·관 및 파서가 좌표로 읽지 못하는 구조의 검색범위 확대는 이번 변경 대상이 아니다.'),
 ('운영 결정·롤백 조건','코드는 adr_0448/inherited frozen rev-001 격리 후보. `binding_runtime.create_agent(pipeline,glossary,index,matcher,limits)`가 실제 store에서 상속 matcher를 만들고 주입한다. 운영 registry·service·MAIN·원본 세대 변경 없음. 후보 계약 회귀 시 실험에서 부모0447/bound를 선택하면 된다. 신규 모델 비교는 별도 새 ADR로 수행한다.'),
 ('재현 명령','계약: `PYTHONPATH=02_BACKEND .venv/bin/python -B -m pytest -q -p no:cacheprovider 06_TOOLS/EXPERIMENTS/adr_0448/test_binding.py`. 읽기 전용 전체 연결 검사: 같은 Python으로 `verify_binding.py` 실행하며 완료 산출물 덮어쓰기를 거부한다. `summarize_prior_counts.py`는0447의 저장 요청·출력만 집계한다. 후보/ADR 최종 검증과 graph는 stable runner 사용. [검증 상태](VALIDATION.md).')]
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# 부모 구조 좌표 상속 연결\n'+''.join(f'\n## {i}. {title}\n\n{body}\n' for i,(title,body) in enumerate(sections,1)))
 (D/'실험/README.md').write_text('# 구조 연결 계약 감사\n\n신규 모델 질문 실행이나 채점 없음. 일반 계약14개와 읽기 전용 source_unit 연결 검사만 수행했다.\n\n- [연결 결과](../artifacts/verification.json)\n- [계약 출력](../artifacts/tests.json)\n- [이전0447 질문별 후보·정답 조문 수](../artifacts/PRIOR_COUNTS.md) — 새 후보 평가가 아님\n- [설계·계보](manifest.json)\n')
 paths=[p for folder in [A,T,C] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=A/'manifest.json' and p.suffix!='.log']
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0448','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input/candidate, contract evidence or explicit prior-output summary'} for p in sorted(paths)]})
 print('audit report finalized; model calls 0')
if __name__=='__main__':main()
