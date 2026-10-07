# GENOS PeCab fulltext 전환 및 NFS 인계

2026-09-29 사용자 지시로 현행 구축·후보 실행에 Kiwi 호환 경로를 허용하지 않는다.
현재 서비스 진입점도 frozen runtime을 import하기 전에 PeCab 1.0.8 v2 색인을 확인한다.
기존 색인이 있는 세대는 아래 명령에 `--rebuild`를 지정한다. 원본을 덮어쓰지 않는다.
로컬 공개 자료 색인은 명시적인 공개 문서 범위만 생성하며, 해당 범위를 벗어난 검색은
오류로 중단한다. 실제 내규를 포함한 GENOS 재구축에서는 `--document-scope`를 쓰지 않는다.
2026-09-23 Kiwi 설치·복구 TXT는 과거 기록이며 현재 반입에 사용하지 않는다.

작업 코드 기준: `pecab==1.0.8`. GENOS 현장 배포·새 generation 생성 결과는 아직
확인되지 않았다. 기존 Kiwi fulltext(`semantic-fulltext-v1`)와 새 PeCab fulltext
(`semantic-fulltext-v2`)는 검색 계약이 다르다. 기존 세대의 색인 파일이나 manifest를
수정하지 않고 새 불변 NFS generation 패키지를 만든다.

## 코드와 의존성

`requirements.txt`가 설치 정본이고 `requirements-serving.txt` 및
`requirements-pipeline.txt`가 이를 참조한다. 코드스페이스와 **별도 코드서빙
리비전의 Python 환경** 모두에 PeCab과 의존성이 필요하다. 사용자가 제공한
2026-09-24 사진에는 코드스페이스 `python3 -m pip install pecab` 성공이 보이지만
코드서빙의 설치 여부는 확인되지 않았다. PeCab은 실행 명령이 아니라 라이브러리다.

```bash
python3 - <<'PY'
import importlib.metadata as md
from pecab import PeCab
print('pecab', md.version('pecab'))
print(PeCab().pos('회사가 담보를 제공한다'))
PY
```

PeCab 1.0.8의 공개 `pos()`에는 원문 오프셋이 없어 코드가 고정 버전의
`_tokenize()` 결과를 검증해 사용한다. Kiwi의 복수 후보 분석과 같지 않다.
예를 들어 PeCab은 `민감도`의 `도`를 조사로 분석해 해당 용어의 자동 회수가
빠질 수 있다. 실제 내부 질문 품질은 현장에서 별도 검증해야 한다.

## 기존 세대에서 fulltext만 새로 만들기

기존 `GENOS_GENERATION`의 navigation·원문·용어집을 재사용한다. 전체
`build-all`이나 구조화를 반복하지 않는다. 아래 코드 경로는 **새 PeCab 코드
ZIP을 백업 후 적용한 기존 `~/DEV` 경로**다. `--scratch-root`는 NFS가 아닌 코드스페이스
로컬 디스크의 여유 공간이 있는 디렉터리다. navigation SQLite와 생성될
fulltext SQLite를 담을 용량이 필요하다. 지정하지 않으면 NFS staging에서
색인을 만든다.

```bash
CODE_ROOT="$HOME/DEV"
SOURCE_GENERATION=/기존/NFS/generation/절대경로
SCRATCH_ROOT=/코드스페이스/로컬/임시디렉터리
python3 "$CODE_ROOT/06_TOOLS/COMMANDS/genos_fulltext_repair.py" \
  --source-generation "$SOURCE_GENERATION" \
  --scratch-root "$SCRATCH_ROOT" --workers 2 --rebuild \
  --output-root /기존/NFS/term-releases/절대경로
```

명령은 원본을 보존하고 새 NFS 패키지의 `GENOS_GENERATION`과
`SHARE_RECEIPT`을 출력한다. `FULLTEXT`와 복사·검증 로그의 단계 시간을
구분해 병목을 확인한다. `--workers`를 늘리면 CPU와 메모리 사용량도 늘어나므로
GENOS 자원 제한에 맞춘다. 현장 속도 개선 폭은 미측정이다.

## 검증·배포·복구

새 generation을 만든 뒤 내부 원문에서 결과를 아는 짧은 검색어 2개로
읽기 전용 회수 점검을 할 수 있다. 상위 5개 문서·조문만 출력하고 원문 본문이나
모델 요청은 출력하지 않는다. 두 검색어의 정답 문서가 실제로 보이는지 현장에서
판단한다. 이는 소표본 점검이며 정답률이나 전체 품질 인증은 아니다.

```bash
GENOS_GENERATION='/출력된/새/NFS/generation' \
  python3 "$CODE_ROOT/06_TOOLS/COMMANDS/genos_pecab_smoke.py"
```

새 코드 ZIP과 실제 push할 checkout의 바이트를 일치시킨 뒤, 그 checkout 및
같은 Python 환경에서 선택한 **새 NFS generation**을 E2E로 검증한다.
`genos-release-integrity` 게이트와
[세대 교체 서빙 계약](GENOS_RAG_GENERATION_HANDOFF.md)을 따른다.

```bash
python3 "$CODE_ROOT/06_TOOLS/COMMANDS/genos_generation_e2e.py" \
  --code-root "$CODE_ROOT" --generation '/출력된/새/NFS/generation'
```

새 코드서빙 리비전에 출력된 절대경로를 `GENOS_GENERATION`으로 지정한다.
코드스페이스 설치·ZIP 해제·NFS 생성·Git push·리비전 배포·실제 질문 성공은
각각 별도 확인 항목이다. 실패 시 이전 코드 리비전과 이전에 검증한 generation
설정으로 복귀하며 원본 NFS 세대를 보존한다.

## 300초와 긴 진행 로그

v5의 `wall_seconds=300`은 legal-agent의 모델·도구 단계 예산이다. 현재 코드의
`RequestContext`는 원문·색인·용어집 등 `resources` 준비가 끝난 뒤 생성된다.
따라서 `resources.index` 또는 `resources.matcher`가 오래 걸리면 전체 HTTP 요청은
300초보다 길 수 있다. `request.heartbeat`는 요청이 살아 있음을 기록하며
300초 종료 타이머가 아니다. 워크플로우와 코드서빙 게이트웨이의 HTTP timeout도
별도로 확인해야 한다. 이전 사진의 최종 오류는 fulltext 생성/사용 중
`ModuleNotFoundError: kiwipiepy`였으므로, 300초 timeout과 동일 원인으로
단정하지 않는다.
