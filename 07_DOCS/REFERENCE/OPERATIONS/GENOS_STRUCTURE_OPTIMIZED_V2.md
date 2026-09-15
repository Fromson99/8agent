# GENOS 최적화 v2 — 설치본 span-only 호환

첫 최적화 실행에서 Unsupported installed source grouping: covering이 발생했다.
현장 사진의 genos_build.py SHA256은 cfa42e40ebbe114ee5ab3533ebfd71f0ea00ca5bcd54d643863e7b3e258caacb이며
기존 genos-four-stage-20260910.zip과 일치한다. 그 버전은 span-only 소속 배정이고
최신 로컬 코드는 span-or-attachments다. v1은 후자만 인식해 실행 전 중단했다.

v2는 두 AST 표현을 명시적으로 인식하고 기존 소속 규칙을 그대로 사용한다.
구버전에서는 ownership_attachments=false, 최신에서는 true를 지문/영수증에 기록한다.
독립 동일성 검사도 같은 정책을 쓴다. 알 수 없는 producer/consumer는 여전히 거절한다.

새 파일 genos_structure_optimized_v2.py.txt와 기존 genos_structure_timing.py.txt를
DEV/TRANSFER에 둔 뒤 다음을 실행한다. 기존 optimizer 파일을 덮어쓸 필요 없다.

```bash
cd /home/genos/DEV
.venv/bin/python -u TRANSFER/genos_structure_optimized_v2.py.txt --from-run external-nfs-001 --rebuild
```

이번 오류는 원본·캐시 수정 전 발생했다. 새 명령은 별도 scratch 폴더에 한 문서를 만든다.
LLM은 호출하지 않는다. 전체 파이프라인 옵션은 v1과 같으며 새 run-id를 사용한다.
반드시 종료 상태와 counts.equivalence.status=PASSED를 확인한다.
parser_identity_matches=false는 새 optimizer 지문에 따른 예상된 차이다.
실제 GENOS 개선 시간/용량은 아직 측정하지 않았다.
