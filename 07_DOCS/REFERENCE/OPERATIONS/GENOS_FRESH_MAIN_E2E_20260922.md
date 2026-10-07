# GENOS 새 MAIN 세대 전체 구축과 E2E 확인 — 2026-09-22

이 절차는 코드스페이스의 등록 RAW와 선택 용어집에서 새 구조화·검토·연결·색인
세대를 만들고, 공유 볼륨 `/nfs-root/diamo/8-agent`에 발행한 뒤 코드서빙과
워크플로우에서 답변까지 확인한다. 기존 `full-80k-002-linked`는 재사용하지 않는다.
외부 WSL에서 GENOS 프로세스와 공유 볼륨에 접근할 수 없으므로 현장 결과는 아래
명령의 출력으로 확인해야 한다.

## 0. 중단 조건과 삭제 범위

사진에서 PID 1016은 `STAT D`로 남았고 `SIGKILL` 뒤에도 종료되지 않았다.
새 색인과 NFS 복사를 시작하기 전에 현장에서 해당 프로세스와 저장소 상태를
해결해야 한다. 같은 볼륨에 동시 실행을 늘리지 않는다.

```bash
ps -p 1016 -o pid,ppid,stat,wchan:32,etime,args
findmnt -T /nfs-root/diamo/8-agent
```

`RAW`, `LEXICON`, 구조화의 원본 영수증, 현재 코드서빙이 읽는 generation,
`CURRENT`와 활성화 영수증은 새 실행의 입력 또는 복구 기준이다. 삭제 대상은
현장 목록과 현재 서빙 경로를 확인한 후 **실패·중단된 파생 run의 정확한 경로**로
한정한다. 실행 중인 프로세스가 잡은 `.lock`이나 부모 run의 STRUCTURE 캐시를
삭제하지 않는다. 새 run ID는 별도 디렉터리를 만들므로 먼저 삭제하지 않아도
새 실행의 입력·산출물이 섞이지 않는다.

## 1. 코드와 입력 확인

새 코드 ZIP을 별도 코드 디렉터리에 풀고 ZIP manifest를 검증한다. 이 전달본에는
`build-all --glossary-corpus-policy replace` 배선과 현행 `term_references.py` 및
`term_index.py`가 함께 있어야 한다. 실행 디렉터리의 `01_DATA/RAW`와
`01_DATA/LEXICON`에는 현장 등록 원본·선택 사전·knowledge bundle을 동일 상대
경로로 배치한다. ZIP에 데이터와 비밀 환경변수는 없다. 현재 `/workspace` 위에
코드만 덮어풀면 구 파일이 남을 수 있으므로 새 디렉터리를 쓴다.

```bash
python3 06_TOOLS/COMMANDS/code_ship.py verify /반입/새코드.zip
python3 06_TOOLS/pipeline.py build-all --help | grep glossary-corpus-policy
python3 06_TOOLS/pipeline.py glossary knowledge check
sha256sum 02_BACKEND/semantic_runtime/term_references.py 02_BACKEND/semantic_runtime/term_index.py
```

코드서빙에도 같은 코드 리비전을 배포해야 새 navigation-v4와 v5 소비자를 읽는다.
코드스페이스 ZIP 압축 해제만으로 코드서빙 리비전은 바뀌지 않는다.

## 2. 새 전체 구축

아래 ID는 예시다. 실제 실행에서는 사용한 적 없는 ID 하나를 정하고 두 명령에
동일하게 쓴다. `replace`는 이전 용어집의 문서 출현·정의 연결을 새로 선택한
원문에 맞춰 다시 만들며 원본 용어집을 바꾸지 않는다. 기존 서빙 세대를
자동 병합하지 않으므로 전체 RAW를 새로 선택할 때 `--base-generation`을
임의로 붙이지 않는다.

```bash
RUN_ID=genos-main-fresh-20260922-001
python3 06_TOOLS/pipeline.py build-all --run-id "$RUN_ID" --glossary-corpus-policy replace --check-only
python3 -u 06_TOOLS/pipeline.py build-all --run-id "$RUN_ID" --glossary-corpus-policy replace --max-review-jobs 100 --execute
```

전체 구조화가 완료되지 않으면 `build-all`은 후속 검토·색인으로 진행하지 않는다.
기존 `full-80k-002`의 2,105건 선택과 21건 제외는 부분 범위이며 전수 완료가
아니다. 새 실행에서도 실패가 남으면 `01_DATA/LOGS/$RUN_ID/doc-status.html`과
상태 원장으로 실패 입력을 수정한 뒤 새 run ID로 전수 실행한다. 성공분만 별도로
연결하려면 `document-release select --allow-incomplete --reason` 경로를 사용하고
최종 범위를 `PARTIAL`로 기록한다. 이를 전체 완료로 표시하지 않는다.

용어 검토가 `REVIEW_PENDING`/exit 3으로 끝나면 입력·코드·모델을 유지한 채 같은
`build-all --execute` 명령을 다시 실행한다. 실패 작업 재시도는 원인을 고친 뒤
`--retry-review-failed`로 명시한다. `--skip-meaning-review`는 별도
`document-release index` 경로의 보류 세대를 생성하므로 전체 의미 검토 E2E의
대체 명령이 아니다.

## 3. 관계 코드가 실제 세대에 들어갔는지 확인

`build_generation`은 현재 `term_index.compile_index`를 호출한다. 그 함수는
`term_references.compile_references`로 명시 참조를 만들고, 결과는
`navigation/navigation.sqlite`의 `reference`, `reference_target` 등으로
저장된다. 생성 결과의 의존성 해시가 실행 코드와 같아야 한다.

```bash
python3 06_TOOLS/pipeline.py document-release verify --release "01_DATA/TERM_RELEASES/$RUN_ID"
RUN_ID="$RUN_ID" python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
run = os.environ['RUN_ID']
release = Path('01_DATA/TERM_RELEASES') / run
result = json.loads((release / 'serving/result.json').read_text())
manifest = json.loads((release / 'serving/generation/navigation/manifest.json').read_text())
actual = hashlib.sha256(Path('02_BACKEND/semantic_runtime/term_references.py').read_bytes()).hexdigest()
assert result['identity']['dependencies']['term_references.py'] == actual
assert manifest['schema_version'] == 'term-navigation-index-v4'
print('relation compiler bound:', actual)
print('navigation reference count:', manifest['counts']['reference'])
PY
```

이는 배선·해시 검사다. 개별 관계의 법적 정확도나 GENOS 모델 품질 인증은 아니다.
현재 로컬 관계 감사에는 부칙 제목을 본문 인용으로 잘못 잡는 후보가 남아 있으므로
최종 검색 품질은 별도 현장 원문 검토가 필요하다.

## 4. NFS 발행과 서빙 E2E

이전 DOC 1건의 NFS PDF 생성·회수는
[현장 기록](GENOS_ZIP_TO_PDF_NFS.md#11-drm-해제-후-doc-1건-pdf-확보-nltk-데이터-누락)에서 확인됐다.
이 사실이 RAG 세대 발행이나 코드서빙의 같은 경로 접근 성공을 뜻하지는 않는다.
이전 RAG 발행 명령은 `/nfs-root/diamo/8-agent/term-releases`를 지정했으나
발행 완료 영수증은 외부 기록에서 찾지 못했다. 해당 디렉터리가 코드스페이스·
코드서빙 양쪽에서 읽히고 쓰기가 허용되는지 현장에서 확인한다. `publish-shared`는 검증한 generation만
새 경로에 복사·해시 검증하며 기존 세대와 `CURRENT`를 바꾸지 않는다.

```bash
mkdir -p /nfs-root/diamo/8-agent/term-releases
python3 06_TOOLS/pipeline.py document-release publish-shared \
  --release "01_DATA/TERM_RELEASES/$RUN_ID" \
  --shared-root /nfs-root/diamo/8-agent/term-releases
```

출력의 `generation_path`를 코드서빙의 `GENOS_GENERATION`에 정확히 설정하고,
`SEMANTIC_LLM_BACKEND=genos` 및 내부 LLM 설정을 확인한 뒤 같은 코드 리비전을
새로 배포한다. 코드서빙에서 `generation_path/manifest.json`을 읽을 수 있어야 한다.
워크플로우에서 `{"question":"자료 목록","use_llm":false}`로 데이터 연결,
이어 실제 근거 질문에 `use_llm:true`로 모델·답변·인용을 확인한다. 요청 ID로
워크플로우·코드서빙·모델 로그를 연결한다. 답변 성공 전에는 이전 세대와 롤백
설정을 보존한다.

## 5. 새 E2E 성공 후 파생물 정리

먼저 GENOS에서 현재 코드서빙의 `GENOS_GENERATION` 값과 모든 후보 디렉터리를
대조한다. 오래된 run의 `TERM_RELEASES`, `LOGS`, 미완료 임시 디렉터리와 NFS
발행본은 실행/서빙 참조가 없는지 확인한 정확한 경로만 삭제한다. RAW·사전·
완료 영수증·활성/롤백 세대는 정리 대상에 넣지 않는다. 삭제 전 목록과 경로를
기록한다. PID 1016의 `D` 상태가 남아 있으면 그 run의 파일을 삭제하지 않는다.
