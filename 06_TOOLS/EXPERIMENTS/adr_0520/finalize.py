"""Package completed diagnostic evidence and run repository validation gates."""
import json,subprocess,hashlib
from pathlib import Path
from bootstrap import R,A,C
from report import sha,read,write

def command(args,path):
    with path.open('w') as out:
        result=subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),*args],cwd=R,stdout=out,stderr=subprocess.STDOUT)
    return result.returncode

def main():
    summary=read(A/'artifacts/summary.json');audit=read(A/'artifacts/db-audit.json');totals=summary['totals']
    report=R/'07_DOCS/REFERENCE/REPORTS/EVIDENCE_BOUND_REFERENCE_EXPLORATION_20260922.md'
    t=totals['exploration'];b=totals['baseline']
    report.write_text(f'''# DB 관계와 새 시작점을 구분하는 탐색 — ADR-0520

## 사용자가 정정한 기준

90/90은 필수 합격 기준이 아니다. DB에서 유효한 관계로 도달했다면 그 하위에서도 정방향·역참조·준용·위임 탐색을 계속한다. 시작점에서만 역참조를 허용하는 제한은 폐기했다. 원문 전체 보존과 실제 탐색 범위는 별개다.

| 이동 | 필요한 근거 | 다음 처리 |
|---|---|---|
| DB 관계 | 관계 ID, 원문 span/hash, 정확한 양끝 범위·방향·상태 | 도달 범위의 관계를 계속 탐색 |
| DB 누락·오류 조사 | 명시 참조 원문, 실패한 좌표, 조사 이유 | 정확한 문서/조 원문을 확인할 후보. 확인 전에는 확정 간선으로 승격하지 않음 |
| 새로운 시작점 | 검색/위치 찾기 경로, 원질문·부족한 쟁점, 선택 이유 | 독립 경로로 탐색을 시작 |
| 제목·이름 유사성 | 검색 단서만 있음 | 참조 간선으로 만들지 않고 검색 후보로 다룸 |

DB 누락 의심만으로 다른 조 전체를 확정 연결로 만들어 재귀 확장하지 않는다. 원문 확인 후 정확 범위를 확정하는 별도 검토·수정 절차가 필요하다. 이번 후보는 미해결 후보와 조사 경로를 제공하며 임의의 LLM 추정 간선을 자동 승인하는 기능은 없다.

## 구현과 검증

격리 후보: [candidate.json]({C/'candidate.json'}), frozen rev-002.
- DB 생성: 구조 제목 오인용 제외, 출발 범위는 가장 깊은 실제 마디, 대상별 범위 유지, 세부 좌표 실패는 확정 간선과 분리.
- 탐색: 선택된 DB와 원문 witness를 검증. 모든 도달 범위에서 양방향 탐색. 동일 상태 순환 종료, 시작점별 소유와 미방문 경로 보존.
- v5 도구: READ 이후 같은 규칙을 적용. 조 전체 READ가 기존 연결의 항·호 탐색 범위를 확대하지 않는다. 새 검색과 연결 READ를 기록에서 구분.
- 새 계약 12건, v5 회귀 53건, 기존 호·목 계약 중 변경되지 않은 13건 통과. 기존 2건은 세부 좌표 실패를 확정 조 연결로 남기라는 구 계약이므로 새 gap 계약으로 대체해야 한다. 첫 실행에서 이 두 구 계약은 실패했으며 통과했다고 집계하지 않았다.
- 실제 시스템 작업에서 3단계 이상 연결 및 연결 대상의 역참조를 확인.

| DB 관찰값 | 기존 DB | 별도 재생성 DB |
|---|---:|---:|
| 관계 행 | {audit['old']['total']} | {audit['new']['total']} |
| 세부 좌표 실패인데 확정 대상이 있는 행 | {audit['old']['partial_canonical_targets']} | {audit['new']['partial_canonical_targets']} |
| 원문 확인용 inspection 후보를 둔 행 | {audit['old']['inspection_candidates']} | {audit['new']['inspection_candidates']} |

제10호 및 제39호 나목 대상 좌표는 그대로 보존됐다. 역참조의 출발 범위는 실제 인용이 있는 제8호·제4호로 좁혔다. 확인한 부칙 제1조 제목→본문 제1조 오인용 행은 생성되지 않았다. 총행 수 감소를 정확도 개선율로 해석하지 않는다.

## 고정된 과거 시작점 재생

| 항목 | 기존 완료 기록 | 새 DB 그래프 재생 |
|---|---:|---:|
| 질문 | {b['cases']} | {t['cases']} |
| 로컬 보존 원문 gold 조 | {b['gold_obtained']}/{b['gold_total']} | {t['gold_obtained']}/{t['gold_total']} |
| 평균 보존 조 수 | {b['source_count_mean']:.1f} | {t['source_count_mean']:.1f} |
| 미완료 탐색 | 해당 방식 아님 | {t['partial_cases']}건 |

새 모델 호출 0회. 기존 검색 기록에서 독립적으로 발견되고 읽기 대상으로 선정됐던 조를 모두 시작점으로 사용했다. 질문별 모델의 시작점 관련성 검토는 재실행하지 않았다. 후보는 전체 조 원문을 로컬 파일에 보존했으며 모델에 전달하지 않았다. 이 gold 수치는 중요한 항·호를 탐색했는지나 답변에서 올바르게 사용했는지를 보증하지 않는다.

두 실행은 동일한 전체 제품 파이프라인 A/B가 아니다. 기존 결과는 과거 회수 기록, 후보는 정확 범위를 추적하는 제한된 그래프 재생이다. 처리 예산은 질문당 10,000 상태/30초이며 PARTIAL과 미방문 큐를 기록했다. 기록 직렬화·파일 저장 시간은 graph seconds 밖에 있으므로 이를 전체 응답 지연으로 인용하면 안 된다.

## 판단과 남은 작업

DB/탐색 계약을 고치는 후보는 구현·검증했지만, 폭발과 놓침을 모두 해결했다고 판정하지 않는다. 다수 시작점에서 유효한 DB 관계를 반복 탐색하면 여전히 큰 묶음이 생긴다. 역참조를 임의로 끊기보다 질문과 무관한 시작점, 소유자별 반복 계산·증거 복사, 실제 DB 오류를 각각 분리해야 한다.

현재 그래프는 시작점별 상태와 경로를 기록하므로 공유 하위 그래프의 계산·원문 witness 기록이 중복된다. 이 표현을 공통 그래프와 시작점별 소유로 분리하는 최적화는 후속 후보에서 동일 도달 집합을 확인해야 한다. 현재 예산을 처리 완료나 의미상 필요성 판정으로 취급하면 안 된다.

별도 누락 조사의 승인·DB 수정·재구축 자동 연결, 새 질문으로 재검색하는 모델의 판단 품질, 최종 시작점 재검토, 출처 표시 계약은 이번 재생으로 검증하지 않았다. ADR-0519의 과거 frozen 원문 묶음 함수 자체를 덮어쓰지 않았고 그 실험 파이프라인을 새 탐색기로 교체한 것도 아니다.

활성 MAIN release·DB 포인터와 GENOS 배포는 변경하지 않았다. 후보 재생 DB는 reference 표 검증용이며 전체 serving generation이 아니다. 운영 적용은 소비자 계약 이행, 새 전체 세대 생성, 일반화 검증, 명시적 MAIN 승격 절차가 필요하다.

[실험 기록]({A/'README.md'}) · [질문별 기록]({A/'실험/README.md'}) · [원시 요약]({A/'artifacts/summary.json'})
''')
    assert command(['adr_structure.py','status','--path',str(A.relative_to(R)),'--status','completed','--note','Frozen diagnostic replay complete; no mandatory90/90 gate; candidate and DB contracts tested; MAIN unchanged, product efficiency/answer quality not certified.'],A/'artifacts/status-completed.txt')==0
    assert command(['adr_structure.py','hash',str(A.relative_to(R))],A/'artifacts/question-hashes.txt')==0
    files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in {'manifest.json','validation-final.txt','graph-check.txt'}]
    files += [A/'PLAN.md',A/'README.md',A/'product-cases.json',A/'gold-cases.json',C/'candidate.json',report]
    files += list(Path(__file__).parent.glob('*.py'))
    files += [R/f['frozen_path'] for f in read(C/'candidate.json')['revisions'][-1]['files']]
    write(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0520','created_at':'2026-09-22','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Immutable diagnostic source, execution, contract or report artifact.','contains_raw_prompts_and_outputs':False} for p in sorted(set(files))]})
    codes={name:command(['adr_structure.py',*args],A/'artifacts'/name) for name,args in [('validation-final.txt',['validate',str(A.relative_to(R)),'--final']),('graph-check.txt',['graph','--adr-root','04_EXPERIMENTS/ADR'])]}
    print(json.dumps(codes))
if __name__=='__main__':main()
