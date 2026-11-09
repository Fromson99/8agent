"""Per-question record files, experiment index and artifact manifests for ADR-1464 and the stopped ADR-1463."""
from common import *
import subprocess
G=read(ART/'grades.json')['grades'];rows=read(ART/'review-input.json')['rows'];E=ADR/'실험'
grading={g['id']:g for g in read(DES/'grading-only.json')}
qs=[]
for i,r in enumerate(rows,1):
    c=r['case_id'];g=G[c];f=f'질문-{i:03d}-{c}.md'
    t=(f"# {c}\n\n## 1. 실행 메타\n\nMAIN179+탐색 수정 3파일+정의 우선순위 4가지 스냅숏, 하이브리드(선택 세대 SQLite 원문, Oracle Gold bge-m3 벡터 초기검색), Qwen3.8 Parasail/none, 출력상한 없음, 외규 모드, 1회.\n\n"
       f"## 2. 사용자 질문 원문\n\n{r['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n{grading[c]['reference_answer']}\n\n"
       f"## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/public-live/{c}-candidate (canonical 입력), 필수 조문 확보 {r['required_acquired']}/{r['required_total']}, 인용 {r['required_cited']}.\n\n"
       f"## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nartifacts/public-live/{c}-candidate/raw, 물리 {r['physical_calls']}회, 결과 불명 {1 if r['unknown'] else 0}.\n\n"
       f"## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\ngenerations.json 원장.\n\n## 7. 채점 호출과 반복 판정\n\n판정 모델 0. 이 세션이 기준답변·저장 원문과 직접 대조.\n\n"
       f"## 8. 사례 최종 판정\n\n{g[0]}{(' '+g[1]) if g[1] else ''} — {g[2]}. (ADR-1461: {r['adr1461']['grade']} {r['adr1461']['failure_type']})\n")
    (E/f).write_text(t);qs.append({'number':i,'case_id':c,'file':f,'sha256':sha(E/f),'grade':g[0]})
idx='\n'.join(f"| {q['number']:03d} | `{q['case_id']}` | `run-001` | {G[q['case_id']][0]} | {G[q['case_id']][1] or '-'} | {G[q['case_id']][2]} | [{q['file']}]({q['file']}) |" for q in qs)
t=(E/'README.md').read_text()
for old,new in [('- 이 분기의 변경 가설: TODO','- 이 분기의 변경 가설: 정의 우선순위 4가지가 정의 연결로 새는 첫 조사를 줄여 51문항 정답률을 올린다'),
 ('| `baseline` | baseline | ROOT | TODO | TODO |','| `baseline` | baseline | ROOT | ADR-1461 MAIN178+3 참조 | 미실행 |'),
 ('| `candidate` | candidate | baseline | TODO | TODO |','| `candidate` | candidate | baseline | MAIN179+3+정의 우선순위·벡터(하이브리드) | 51/51 종료 |'),
 ('| - | - | - | - | - | - | 질문 단위 평가 없음 |',idx),
 ('- arm별 정답: TODO','- arm별 정답: candidate PASS37·PARTIAL5·FAIL9; baseline(ADR-1461) PASS25·PARTIAL9·FAIL17'),
 ('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO','- 사전 지정 비교쌍별 신규 정답 / 회귀: 나아짐 13 / 나빠짐 1'),
 ('- judge 불일치: TODO','- judge 불일치: 판정 모델 없음'),
 ('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |','| `run-001` | candidate | 51 | 291 | 0 | $1.41 | 3,806초 | 73/98 | artifacts/CM51_결과.csv |')]:
    assert old in t,old;t=t.replace(old,new,1)
(E/'README.md').write_text(t)
m=read(E/'manifest.json');m['questions']=qs;put(E/'manifest.json',m)
subprocess.run([sys.executable,str(Path(__file__).with_name('manifest.py')),'ADR-1464'],check=True,cwd=Path(__file__).parent)
# ADR-1463
A3=ROOT/'04_EXPERIMENTS/ADR/ADR-1463-main179-definition-priority-cm51-qwen';E3=A3/'실험';t=(E3/'README.md').read_text()
for old,new in [('- 이 분기의 변경 가설: TODO','- 이 분기의 변경 가설: ADR-1464와 같음(첫 문항 자원 중단)'),
 ('| `baseline` | baseline | ROOT | TODO | TODO |','| `baseline` | baseline | ROOT | ADR-1461 참조 | 미실행 |'),
 ('| `candidate` | candidate | baseline | TODO | TODO |','| `candidate` | candidate | baseline | MAIN179+3+정의 우선순위 | cm-001에서 자원 중단 |'),
 ('- arm별 정답: TODO','- arm별 정답: 판정 0'),('- 사전 지정 비교쌍별 신규 정답 / 회귀: TODO','- 사전 지정 비교쌍별 신규 정답 / 회귀: 해당 없음'),
 ('- judge 불일치: TODO','- judge 불일치: 해당 없음'),
 ('| `run-001` | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |','| `run-001` | candidate | 1 | 1 | 0 | $0.0023 | - | - | resource stop |')]:
    assert old in t,old;t=t.replace(old,new,1)
(E3/'README.md').write_text(t)
env=dict(os.environ);code=f"import sys;sys.argv=['manifest.py','ADR-1463'];import common;common.ADR=common.ROOT/'04_EXPERIMENTS/ADR/ADR-1463-main179-definition-priority-cm51-qwen';common.ART=common.ADR/'artifacts';exec(open('manifest.py').read().replace('from common import *','from common import *\\nADR=common.ADR;ART=common.ART'))"
subprocess.run([sys.executable,'-c',code],check=True,cwd=Path(__file__).parent)
print('docs ok',len(qs))
