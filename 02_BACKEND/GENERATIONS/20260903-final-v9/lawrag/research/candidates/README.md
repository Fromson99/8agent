# ADR candidate snapshots

새 연구 후보는 운영 모듈을 직접 고치거나 통째로 복제하지 않는다.

```bash
.venv/bin/python scripts/adr_candidate.py snapshot \
  --adr docs/adr/ADR-NNNN-slug \
  --candidate-id candidate-name \
  --source lawrag/core/rag/file_to_change.py
```

명시한 파일만 `adr_NNNN/candidate-name/snapshot/` 아래 원래 상대경로로 복사되고,
`candidate.json`에 upstream path·SHA-256·복사본 SHA-256이 고정된다. 이 경로는 연구·재현
전용이다. 복사본을 수정한 뒤 `adr_candidate.py freeze <candidate-directory>`로 새 revision
hash를 고정하고 `adr_candidate.py validate <candidate-directory>`로 검증한다. 운영에서
사용하려면 검증된 구현을 `lawrag/runtime/components/`로 옮기고 production
registry에 새 profile ID를 등록한 다음 MAIN promotion 절차를 거친다.
