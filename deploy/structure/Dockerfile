# 구조 해석 검수 서비스.
#
#   docker compose -f docker-compose.structure.yml up -d --build
#   open http://localhost:5566
#
# 저장소 루트에서 빌드한다(컨텍스트가 루트여야 core/ 를 복사할 수 있다).

FROM python:3.12-slim AS base

# docling → easyocr/opencv 가 libGL·glib 을 요구한다. 없으면 임포트 시점에 죽는다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    STRUCTURE_STORE=/data/structure \
    # 사람이 등록한 규칙은 **볼륨**에 둔다. 이미지 안에 두면 컨테이너를
    # 다시 만들 때 통째로 사라진다.
    STRUCTURE_CUSTOM_DIR=/data/structure/custom \
    # docling 의 레이아웃 모델이 torch.compile 을 타는데, slim 이미지에는 g++ 가 없어
    # `InvalidCxxCompiler: No working C++ compiler` 로 파싱이 통째로 죽는다.
    # 컴파일러를 넣으면 이미지가 ~200MB 커진다. 추론은 eager 로도 정확도가 같고
    # 이 서비스는 문서당 한 번만 파싱하므로 컴파일을 끄는 쪽을 택했다.
    TORCHDYNAMO_DISABLE=1 \
    TORCH_COMPILE_DISABLE=1

WORKDIR /app

# 의존성 먼저 — 소스가 바뀌어도 이 레이어는 캐시된다(torch 재설치 방지).
COPY deploy/structure/requirements.txt ./requirements.txt
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# 도클링 레이아웃 모델을 이미지에 구워 넣는다. 빌드가 몇 분 길어지지만
# **런타임 첫 요청이 빨라지고 망 없이도 돈다** — 컨테이너로 관리하는 이유의 절반이다.
ARG BAKE_MODELS=1
RUN if [ "$BAKE_MODELS" = "1" ]; then \
        python -c "from docling.document_converter import DocumentConverter; DocumentConverter()" ; \
    fi

COPY core/ core/
COPY api/ api/
# AGENT6 근거 연결 화면이 읽는 것 — 체크리스트 항목과 구조화된 코퍼스.
# 이게 없으면 `/agent6/` 는 뜨지만 목록이 비어 있다(원인이 화면에 안 보인다).
COPY agents/ agents/

# 어휘·신호가 실제로 등록되는지 빌드 시점에 확인한다 — 파일 하나 빠뜨린 이미지를 만들지 않는다.
RUN python -c "import sys; sys.path.insert(0,'.'); \
from core.structure import registry; r=registry.default(); \
assert r.by_role('proposer') and r.by_role('local_guard'); \
print('신호', len(r.signals), '개 등록')"

RUN mkdir -p /models /data/structure/custom \
    && useradd -m -u 10001 app \
    && chown -R app:app /models /data /app
USER app

EXPOSE 5566
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:5566/health || exit 1

CMD ["uvicorn", "api.structure_app:app", "--host", "0.0.0.0", "--port", "5566"]
