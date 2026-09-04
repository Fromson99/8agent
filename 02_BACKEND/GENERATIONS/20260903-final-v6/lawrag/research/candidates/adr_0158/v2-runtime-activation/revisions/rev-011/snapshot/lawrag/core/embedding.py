"""문장 임베딩 공용 인코더 — 컴파일(용어 디듀프·구역 색인)과 검색(벡터 단)이
같은 모델을 써야 한다. 모델이 갈리면 질의 벡터와 구역 벡터가 다른 공간에
있어 코사인이 무의미해진다.

결정 변경 기록 (2026-08-10): 애초 임베딩은 용어 생성 배치 전용이었으나,
"용어가 아직 없는 초반"의 회수를 위해 **검색 사다리의 후순위 단**으로도
쓰기로 했다 (사용자 결정). 규율은 유지된다:
  · 용어 단(정확·부분)이 항상 먼저다 — 벡터는 용어가 빗나갔을 때만
  · 벡터가 찾아준 착지는 승격 후보로 적재된다 — 벡터 히트는 종착이 아니라
    용어가 태어나는 신호다 (자기상각)
  · 무거운 import 는 전부 지연 — 모델이 없으면 벡터 단은 조용히 빠지고
    렉시컬만으로 동작한다 (오프라인 환경 보존)

백엔드는 둘이다 (2026-08-18, lawrag/core/llm.py 와 같은 구도):
  · local — sentence-transformers 로 EMBED_MODEL(기본 BAAI/bge-m3)을 프로세스에
    하나 띄운다(~2GB). 첫 호출이 느린 것은 로드 비용이다.
  · genos — GenOS 임베딩 서빙. 서비스 라우터(유형 "서빙 - Embedding")가
    `{GENOS_EMBED_URL}/v1/embeddings` 로 노출한다 (실측: genos-docs v1.9.0
    "서비스 라우터" — 경로만 문서에 있고 몸통 스키마는 없다). 요청·응답은
    OpenAI 형식으로 가정한다 — `{"model", "input": [...]}` →
    `{"data": [{"index", "embedding": [...]}]}`. 그쪽 엔진(vLLM·TEI 계열)이
    다 이 형식이다. 첫 호출이 400 이면 그때 형식을 맞춘다.
  고르는 규칙: EMBED_BACKEND 가 있으면 그것, 없으면 GENOS_EMBED_URL 이 있을 때
  genos, 아니면 local.

**벡터 색인과 질의는 같은 백엔드·같은 모델이어야 한다.** 색인을 다른 모델로
다시 만들면(그쪽에서 재생성) 옛 vectors.npz 를 지우고 만들어라 —
embed_sections 는 sha1 이 같으면 옛 벡터를 재사용한다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Optional

MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
BACKENDS = ("local", "genos")

_model = None
_failed = False
_genos = None            # (session, url, model) — 첫 호출 때 세운다
_local_runtime_configured = False
_local_artifact_cache: tuple[
    str,
    str,
    tuple[tuple[object, ...], ...],
] | None = None

EMBEDDING_IDENTITY_SCHEMA = "embedding-model-fingerprint-v2"
DOCUMENT_PROFILE = "lawrag-shared-encode-v1"
QUERY_PROFILE = "lawrag-shared-encode-v1"


def _sealed() -> bool:
    return os.environ.get("LAWRAG_SERVING_SEALED", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def local_model_artifact_sha256(path: str | os.PathLike[str]) -> str:
    """Hash the exact local model bytes with paths, rejecting symlink aliases."""

    global _local_artifact_cache
    root = Path(path)
    if not root.is_absolute():
        raise RuntimeError("local embedding model artifact path must be absolute")
    for component in (root, *root.parents):
        if component.is_symlink():
            raise RuntimeError("local embedding model artifact contains a symlink")
    if root.is_file():
        paths = [root]
        base = root.parent
    elif root.is_dir():
        members = sorted(root.rglob("*"))
        if any(candidate.is_symlink() for candidate in members):
            raise RuntimeError("local embedding model artifact contains a symlink")
        if _sealed():
            directory_members = [root, *(candidate for candidate in members if candidate.is_dir())]
            if any(stat.S_IMODE(candidate.stat().st_mode) & 0o222 for candidate in directory_members):
                raise RuntimeError("sealed local embedding model artifact tree is writable")
        paths = [candidate for candidate in members if candidate.is_file()]
        base = root
    else:
        raise RuntimeError("local embedding model artifact does not exist")
    if not paths:
        raise RuntimeError("local embedding model artifact is empty")
    cache_key = str(root.resolve())
    rows: list[dict[str, object]] = []
    inspected: list[tuple[Path, str, os.stat_result, tuple[object, ...]]] = []
    for candidate in paths:
        relative = candidate.relative_to(base).as_posix()
        try:
            before = candidate.lstat()
        except OSError as exc:
            raise RuntimeError("cannot inspect local embedding model artifact") from exc
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise RuntimeError("local embedding model artifact member is not regular")
        if _sealed() and stat.S_IMODE(before.st_mode) & 0o222:
            raise RuntimeError("sealed local embedding model artifact is writable")
        identity = (
            relative,
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        inspected.append((candidate, relative, before, identity))
    identity_manifest = tuple(item[3] for item in inspected)
    if _local_artifact_cache is not None and _local_artifact_cache[0] == cache_key:
        if _local_artifact_cache[2] != identity_manifest:
            raise RuntimeError(
                "sealed local embedding model artifact changed after admission"
            )
        return _local_artifact_cache[1]
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError("local embedding model verification requires no-follow opens")
    for candidate, relative, before, _member_identity in inspected:
        try:
            descriptor = os.open(
                candidate,
                os.O_RDONLY | getattr(os, "O_BINARY", 0) | no_follow,
            )
        except OSError as exc:
            raise RuntimeError("cannot safely open local embedding model artifact") from exc
        digest = hashlib.sha256()
        try:
            opened = os.fstat(descriptor)
            identity = lambda value: (
                value.st_dev,
                value.st_ino,
                value.st_mode,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )
            if identity(before) != identity(opened):
                raise RuntimeError("local embedding model artifact changed before read")
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            if identity(opened) != identity(os.fstat(descriptor)):
                raise RuntimeError("local embedding model artifact changed during read")
        finally:
            os.close(descriptor)
        rows.append(
            {
                "path": relative,
                "bytes": before.st_size,
                "sha256": digest.hexdigest(),
            }
        )
    result = hashlib.sha256(
        _canonical(
            {
                "schema_version": "embedding-local-model-artifact-v1",
                "kind": "file" if root.is_file() else "directory",
                "files": rows,
            }
        )
    ).hexdigest()
    if _sealed():
        _local_artifact_cache = (cache_key, result, identity_manifest)
    return result


def require_uninitialized_runtime() -> None:
    """Reject an encoder client/model constructed before release admission."""

    if _model is not None or _genos is not None or _failed:
        raise RuntimeError(
            "embedding runtime was initialized before release admission"
        )


def _verified_local_model_path() -> Path:
    raw = os.environ.get("EMBED_MODEL_ARTIFACT_PATH", "").strip()
    if not raw:
        raise RuntimeError("sealed local encoder requires EMBED_MODEL_ARTIFACT_PATH")
    path = Path(raw)
    actual = local_model_artifact_sha256(path)
    expected = os.environ.get("EMBED_MODEL_SHA256", "").strip()
    if actual != expected:
        raise RuntimeError("local embedding model artifact SHA-256 mismatch")
    return path


def runtime_identity() -> dict[str, object]:
    """Describe the encoder configuration that the code actually consumes.

    In release mode mutable model aliases are forbidden: local loading receives
    the exact revision below, and GenOS requests name the exact model ID.  The
    returned fields use the same canonical contract as release.py.
    """

    raw_backend = os.environ.get("EMBED_BACKEND", "").strip().lower()
    if _sealed() and raw_backend not in BACKENDS:
        raise RuntimeError("sealed encoder requires an explicit EMBED_BACKEND")
    selected_backend = backend()
    if selected_backend == "local":
        model_id = os.environ.get("EMBED_MODEL", MODEL).strip()
        model_revision = os.environ.get("EMBED_MODEL_REVISION", "").strip()
        model_artifact_sha256 = os.environ.get("EMBED_MODEL_SHA256", "").strip()
        raw_dimensions = os.environ.get("EMBED_DIMENSIONS", "").strip()
        if _sealed():
            if os.environ.get("EMBED_LOCAL_FILES_ONLY") != "1":
                raise RuntimeError("sealed local encoder must use local files only")
            _verified_local_model_path()
    else:
        model_id = os.environ.get("GENOS_EMBED_MODEL", "").strip()
        model_revision = os.environ.get(
            "GENOS_EMBED_MODEL_REVISION", ""
        ).strip()
        model_artifact_sha256 = os.environ.get(
            "GENOS_EMBED_MODEL_SHA256", ""
        ).strip()
        raw_dimensions = os.environ.get("GENOS_EMBED_DIMENSIONS", "").strip()
    if not model_id or not model_revision:
        raise RuntimeError("release encoder requires an exact model ID and revision")
    if len(model_artifact_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in model_artifact_sha256
    ):
        raise RuntimeError(
            "release encoder requires an exact model artifact SHA-256"
        )
    try:
        dimensions = int(raw_dimensions)
    except ValueError as exc:
        raise RuntimeError("release encoder dimensions must be an integer") from exc
    if dimensions <= 0:
        raise RuntimeError("release encoder dimensions must be positive")
    return {
        "schema_version": EMBEDDING_IDENTITY_SCHEMA,
        "backend": selected_backend,
        "model_id": model_id,
        "model_revision": model_revision,
        "model_artifact_sha256": model_artifact_sha256,
        "dimensions": dimensions,
        "normalized": True,
        "document_profile": DOCUMENT_PROFILE,
        "query_profile": QUERY_PROFILE,
    }


def runtime_fingerprint() -> str:
    """Derive the model-space fingerprint; never trust a digest string alone."""

    derived = hashlib.sha256(_canonical(runtime_identity())).hexdigest()
    declared = os.environ.get("RAG_EMBEDDING_MODEL_FINGERPRINT", "").strip()
    if declared and declared != derived:
        raise RuntimeError("declared embedding fingerprint disagrees with runtime config")
    return derived


def _expected_dimensions() -> int | None:
    try:
        return int(runtime_identity()["dimensions"])
    except RuntimeError:
        return None


def _load_env() -> None:
    """독립 색인 명령에서도 저장소 루트의 `.env`를 읽는다."""
    from pathlib import Path

    if _sealed():
        return

    root = Path(__file__).resolve().parent.parent.parent
    candidate = root / ".env"
    if not candidate.exists():
        return
    for line in candidate.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if value and not os.environ.get(key):
            os.environ[key] = value


def _genos_embed_url() -> str:
    """직접 URL 또는 GenOS 기본 주소 + 임베딩 서빙 ID로 완성한 endpoint."""
    _load_env()
    direct = (os.environ.get("GENOS_EMBED_URL") or "").strip()
    if direct:
        return direct.rstrip("/")
    serving_id = (os.environ.get("GENOS_EMBED_SERVING_ID") or "").strip()
    base = (os.environ.get("GENOS_BASE_URL") or "").strip().rstrip("/")
    if not base or not serving_id or not serving_id.isdigit():
        return ""
    return f"{base}/api/gateway/rep/serving/{serving_id}"


def _configure_local_runtime() -> None:
    """WSL/CPU에서 과도한 BLAS·Torch 스레드 경쟁을 피한다.

    실측상 기본 스레드 자동 선택은 BGE-M3 첫 질의를 7분 이상 끌었고, 4개로
    제한하면 같은 입력이 10.5초였다. 명시한 OMP/MKL 값은 존중한다.
    """
    global _local_runtime_configured
    if _local_runtime_configured:
        return
    threads = max(1, int(os.environ.get("EMBED_CPU_THREADS", "4")))
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(threads))
    try:
        import torch

        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
    except Exception:
        pass
    _local_runtime_configured = True


def backend() -> str:
    b = (os.environ.get("EMBED_BACKEND") or "").strip().lower()
    if b in BACKENDS:
        return b
    return "genos" if _genos_embed_url() else "local"


def available() -> bool:
    """임베딩을 할 수 있는가 — local 이면 sentence-transformers 가 깔려 있고,
    genos 면 URL 이 있고. 명시적으로 끄면(RAG_VECTOR=0) 둘 다 아니다.
    실패도 기억한다 — 매 질의마다 다시 실패하면 안 된다."""
    if os.environ.get("RAG_VECTOR", "1") == "0":
        return False
    if _sealed():
        try:
            runtime_fingerprint()
        except RuntimeError as exc:
            from lawrag.core.rag.content_snapshot import ContentSnapshotError

            raise ContentSnapshotError(
                "sealed embedding runtime identity is invalid"
            ) from exc
    if _failed:
        return False
    if backend() == "genos":
        return bool(_genos_embed_url())
    try:
        _configure_local_runtime()
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def _encode_local(texts: list[str], batch_size: int):
    global _model
    _configure_local_runtime()
    if _model is None:
        from sentence_transformers import SentenceTransformer
        kwargs = {"device": os.environ.get("EMBED_DEVICE", "cpu")}
        revision = os.environ.get("EMBED_MODEL_REVISION", "").strip()
        if revision:
            kwargs["revision"] = revision
        if os.environ.get("EMBED_LOCAL_FILES_ONLY", "0") == "1":
            kwargs["local_files_only"] = True
        source = _verified_local_model_path() if _sealed() else Path(
            os.environ.get("EMBED_MODEL_ARTIFACT_PATH", MODEL)
        )
        loaded_model = SentenceTransformer(str(source), **kwargs)
        if _sealed():
            _verified_local_model_path()
        _model = loaded_model
    return _model.encode(texts, normalize_embeddings=True,
                         batch_size=batch_size,
                         show_progress_bar=False).astype("float32")


def _encode_genos(texts: list[str], batch_size: int):
    """OpenAI 호환 /v1/embeddings — 배치로 끊어 보내고 정규화해 돌려준다."""
    global _genos
    import numpy as np
    import requests

    if _genos is None:
        _load_env()
        url = _genos_embed_url()
        if not url:
            raise RuntimeError("GENOS_EMBED_URL 또는 GENOS_BASE_URL·GENOS_EMBED_SERVING_ID가 필요합니다")
        s = requests.Session()
        s.trust_env = False
        s.headers["Content-Type"] = "application/json"
        key = os.environ.get("GENOS_EMBED_KEY", "")
        if key:
            s.headers["Authorization"] = f"Bearer {key}"
        tenant_id = os.environ.get("GENOS_EMBED_TENANT_ID", "").strip()
        if tenant_id:
            s.headers["x-genos-user-id"] = tenant_id
        model = os.environ.get("GENOS_EMBED_MODEL", "")
        if os.environ.get("LAWRAG_SERVING_SEALED", "").strip().lower() in {
            "1", "true", "yes", "on",
        } and not model:
            raise RuntimeError("sealed GenOS embedding requires GENOS_EMBED_MODEL")
        if not model:                          # LLM 쪽과 같은 절차 — /v1/models 첫 모델
            try:
                r = s.get(
                    url + "/v1/models", timeout=15, allow_redirects=False
                )
                r.raise_for_status()
                model = r.json()["data"][0]["id"]
            except Exception:
                model = MODEL                  # 못 물으면 로컬 기본 이름으로 — 서빙이 무시할 수도
        _genos = (s, url, model)
    s, url, model = _genos
    bs = int(os.environ.get("GENOS_EMBED_BATCH", str(batch_size)))
    out = []
    for i in range(0, len(texts), bs):
        chunk = texts[i:i + bs]
        r = s.post(
            url + "/v1/embeddings",
            json={"model": model, "input": chunk},
            timeout=(15, 300),
            allow_redirects=False,
        )
        r.raise_for_status()
        payload = r.json()
        if _sealed() and payload.get("model") != model:
            raise RuntimeError("GenOS embedding response has another/missing model")
        if _sealed():
            expected_headers = {
                "x-lawrag-model-revision": os.environ.get(
                    "GENOS_EMBED_MODEL_REVISION", ""
                ),
                "x-lawrag-model-sha256": os.environ.get(
                    "GENOS_EMBED_MODEL_SHA256", ""
                ),
                "x-lawrag-credential-binding-id": os.environ.get(
                    "GENOS_EMBED_CREDENTIAL_BINDING_ID", ""
                ),
                "x-lawrag-credential-binding-version": os.environ.get(
                    "GENOS_EMBED_CREDENTIAL_BINDING_VERSION", ""
                ),
                "x-lawrag-trust-policy-id": os.environ.get(
                    "GENOS_EMBED_TRUST_POLICY_ID", ""
                ),
            }
            if any(not value for value in expected_headers.values()) or any(
                r.headers.get(key) != value
                for key, value in expected_headers.items()
            ):
                raise RuntimeError(
                    "sealed GenOS embedding response lacks exact serving attestation"
                )
        data = sorted(payload["data"], key=lambda d: d.get("index", 0))
        if len(data) != len(chunk):
            raise RuntimeError(f"임베딩 응답 행 수 불일치 — 보냄 {len(chunk)}, 받음 {len(data)}")
        out.extend(d["embedding"] for d in data)
    m = np.asarray(out, dtype=np.float32)
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def encode(texts: list[str], batch_size: int = 64):
    """정규화된 float32 행렬. 호출 전에 available() 로 걸러라 —
    여기서 실패하면 None 을 돌려주고 이후 available() 도 False 가 된다."""
    global _failed
    if _sealed():
        if os.environ.get("RAG_VECTOR") != "1":
            from lawrag.core.rag.content_snapshot import ContentSnapshotError

            raise ContentSnapshotError(
                "sealed retrieval has no admitted embedding runtime"
            )
        try:
            runtime_fingerprint()
        except RuntimeError as exc:
            from lawrag.core.rag.content_snapshot import ContentSnapshotError

            raise ContentSnapshotError(
                "sealed embedding runtime identity is invalid"
            ) from exc
    if not texts:
        import numpy as np
        return np.zeros((0, 1024), dtype=np.float32)
    try:
        if backend() == "genos":
            value = _encode_genos(texts, batch_size)
        else:
            value = _encode_local(texts, batch_size)
        expected_dimensions = _expected_dimensions()
        if expected_dimensions is not None and (
            getattr(value, "ndim", 0) != 2
            or value.shape[1] != expected_dimensions
        ):
            raise RuntimeError(
                "embedding response dimensions disagree with runtime identity"
            )
        return value
    except Exception as exc:
        _failed = True
        if _sealed():
            from lawrag.core.rag.content_snapshot import ContentSnapshotError

            if isinstance(exc, ContentSnapshotError):
                raise
            raise ContentSnapshotError("sealed embedding request failed") from exc
        return None


def encode_one(text: str) -> Optional[object]:
    m = encode([text])
    return None if m is None or len(m) == 0 else m[0]
