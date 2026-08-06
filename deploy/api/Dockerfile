# 레거시 2엔진 API — archive/trust-parser-v1(v1) + first-agent(v0) 를 한 서비스로.
#
#   docker compose -f deploy/api/docker-compose.yml up -d --build
#   curl http://localhost:5555/health
#
# 빌드 컨텍스트는 **저장소 루트**다(compose 가 `context: ../..` 로 준다).
# 루트 `.dockerignore` 는 기본 서비스(구조 해석기) 기준이라 두 레거시 엔진을 빼므로,
# 이 이미지는 옆의 `Dockerfile.dockerignore` 로 덮어쓴다(BuildKit 규칙).
#
# 이미지가 큰 이유는 docling 이 torch 를 끌고 오기 때문이다(CPU 휠로도 ~2GB).
# PDF 파싱이 필요 없다면 requirements-light.txt 로 바꾸면 ~150MB 가 된다.

FROM python:3.12-slim

# docling → easyocr/opencv 가 libGL·glib 을 요구한다. 없으면 임포트 시점에 죽는다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models

WORKDIR /app

# 의존성 먼저 — 소스가 바뀌어도 이 레이어는 캐시된다
COPY deploy/api/requirements.txt requirements.txt
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

# 도클링 레이아웃 모델을 이미지에 구워 넣고 싶으면 주석을 푼다.
# 빌드는 몇 분 더 걸리지만 런타임 첫 요청이 빨라지고 오프라인에서도 돈다.
# RUN python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"

# 엔진 위치는 api/settings.py 의 기본값과 같아야 한다
# (PARSER_ROOT=archive/trust-parser-v1, AGENT_ROOT=first-agent).
COPY archive/trust-parser-v1/ archive/trust-parser-v1/
COPY first-agent/ first-agent/
COPY core/ core/
COPY api/ api/

RUN mkdir -p /models /app/archive/trust-parser-v1/out /app/first-agent/snapshots \
    && useradd -m -u 10001 app \
    && chown -R app:app /models /app
USER app

EXPOSE 5555
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:5555/health || exit 1

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "5555"]
