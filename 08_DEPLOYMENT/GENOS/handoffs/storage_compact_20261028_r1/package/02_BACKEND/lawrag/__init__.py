"""lawrag — 법령·규정 문서를 수집→구조화→연결→질의응답으로 잇는 시스템의 코드 전부.

    api/        FastAPI 앱 하나(structure_app) · viewer/ · ops(폐쇄망 운반)
    core/       구조 해석(structure) · 회수·질의(rag) · 검토(casereview) · 용어(terms) · 파싱·인제스트
    sources/    수집 어댑터 (kofia · fss · krx · lawgo · expc · prec · cite)
    pipeline/   수집→변환→인제스트→위키 트리아지 CLI  (python -m lawrag.pipeline.<이름>)
    agents/     agent6 — 녹취 체크리스트 ↔ 법령 근거

저장소 뿌리는 `lawrag.ROOT`. 상태는 data/, 휘발물은 var/, 문서는 docs/, 도구는 scripts/.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
