"""GENOS /run -> Docling structure or audited complete text-chunk assembly.

Both transports feed the common structure-template path. Chunk input retains
its limitations and requires original-PDF VLM review before downstream indexing.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
from urllib.parse import urlsplit
import uuid

VERSION = 'genos-parsed-document-v2'
_UNSET = object()
_selected = ContextVar('genos_pdf_parser', default=_UNSET)


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _plain(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('GENOS preprocessor paths must be absolute without parent traversal')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('GENOS preprocessor path must not be a symlink')
    return path


@dataclass(frozen=True)
class Settings:
    url: str
    revision: str
    shared_root: Path
    remote_root: str
    timeout: int
    max_response_bytes: int
    response_mode: str = 'auto'

    @classmethod
    def from_env(cls):
        transport = os.environ.get('GENOS_PREPROCESSOR_TRANSPORT', 'http').strip()
        if transport == 'pod':
            from .genos_pod import Settings as PodSettings
            return PodSettings.from_env()
        if transport != 'http':
            raise ValueError('GENOS_PREPROCESSOR_TRANSPORT must be http or pod')
        url = os.environ.get('GENOS_PREPROCESSOR_URL', '').strip()
        if not url:
            ident = os.environ.get('GENOS_PREPROCESSOR_ID', '').strip()
            if not re.fullmatch(r'[1-9][0-9]*', ident):
                raise ValueError('Set GENOS_PREPROCESSOR_ID or GENOS_PREPROCESSOR_URL in code-space environment settings')
            url = f'http://preprocessor-{ident}:8080/run'
        parts = urlsplit(url)
        if (parts.scheme not in {'http', 'https'} or not parts.hostname or
                parts.username or parts.password or parts.query or parts.fragment):
            raise ValueError('GENOS_PREPROCESSOR_URL must be an HTTP(S) URL without credentials/query/fragment')
        # Allow a base service URL, or a fully specified /run or /parser route.
        if parts.path in {'', '/'}:
            url = url.rstrip('/') + '/run'
        elif not parts.path.rstrip('/').endswith(('/run', '/parser')):
            raise ValueError('GENOS_PREPROCESSOR_URL must end in /run or /parser')
        else:
            url = url.rstrip('/')
        revision = os.environ.get('GENOS_PREPROCESSOR_REVISION', '').strip()
        if not os.environ.get('GENOS_PREPROCESSOR_SHARED_ROOT', '').strip():
            raise ValueError('Set GENOS_PREPROCESSOR_SHARED_ROOT to an existing shared NFS directory')
        shared = _plain(os.environ['GENOS_PREPROCESSOR_SHARED_ROOT'].strip())
        remote = os.environ.get('GENOS_PREPROCESSOR_REMOTE_ROOT', '').strip() or str(shared)
        if not PurePosixPath(remote).is_absolute() or '..' in PurePosixPath(remote).parts:
            raise ValueError('GENOS_PREPROCESSOR_REMOTE_ROOT must be an absolute server-side path')
        timeout = int(os.environ.get('GENOS_PREPROCESSOR_TIMEOUT', '900'))
        limit = int(os.environ.get('GENOS_PREPROCESSOR_MAX_RESPONSE_MB', '128'))
        if not 1 <= timeout <= 7200 or not 1 <= limit <= 512:
            raise ValueError('GENOS preprocessor timeout must be 1..7200 seconds; response limit 1..512 MiB')
        response_mode = os.environ.get('GENOS_PREPROCESSOR_RESPONSE_MODE', 'auto').strip()
        if response_mode not in {'auto', 'docling', 'chunks'}:
            raise ValueError('GENOS_PREPROCESSOR_RESPONSE_MODE must be auto, docling or chunks')
        return cls(url, revision, shared, remote, timeout, limit * 1024 * 1024, response_mode)

    def identity(self):
        from .genos_chunks import VERSION as assembly_version
        return {'contract': VERSION, 'url': self.url, 'declared_revision': self.revision,
                'shared_root': str(self.shared_root), 'remote_root': self.remote_root,
                'response_mode': self.response_mode,
                'chunk_assembly_version': assembly_version,
                'output_format': 'docling-or-chunks', 'required_server_enrichment': 'disabled'}


def selected():
    value = _selected.get()
    if value is not _UNSET:
        return value
    mode = os.environ.get('GENOS_PDF_PARSER', 'local').strip()
    if mode not in {'local', 'preprocessor'}:
        raise ValueError('GENOS_PDF_PARSER must be preprocessor or local')
    return Settings.from_env() if mode == 'preprocessor' else None


@contextmanager
def using(settings, evidence=None):
    token = _selected.set(settings)
    evidence_token = _evidence.set(evidence)
    try:
        yield
    finally:
        _evidence.reset(evidence_token)
        _selected.reset(token)


_evidence = ContextVar('genos_parser_evidence', default=None)


def source_identity(path, settings):
    return {**settings.identity(), 'source_sha256': _sha(path)}


def _save(path, data):
    # No authorization header is passed to this function.
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parse(path, settings):
    """Stage identical source bytes on shared NFS; validate the server document.

    A timeout may leave a server request running. Keep the unique request directory
    and evidence; never automatically retry or remove an in-flight source file.
    """
    if os.environ.get('GENOS_PREPROCESSOR_TRANSPORT', 'http') == 'pod':
        from . import genos_pod
        if not isinstance(settings, genos_pod.Settings):
            raise ValueError('POD_SETTINGS_REQUIRED')
        return genos_pod.parse(path,settings)
    import httpx

    source = Path(path)
    fingerprint = _sha(source)
    shared = _plain(settings.shared_root)
    if not shared.is_dir():
        raise ValueError('GENOS_PREPROCESSOR_SHARED_ROOT must be an existing shared directory readable by the preprocessor')
    request_id = uuid.uuid4().hex
    work = shared / request_id
    work.mkdir(mode=0o770)
    staged = work / 'source.pdf'
    # Shared-group access only; the mount must provide a common reader group.
    with staged.open('xb') as out, source.open('rb') as inp:
        import shutil
        shutil.copyfileobj(inp, out)
    # The parser writes its own image artifacts beside source.pdf. Preserve the
    # inherited shared group for those artifacts; don't expose them to everyone.
    work.chmod(0o2770)
    staged.chmod(0o640)
    if _sha(staged) != fingerprint or _sha(source) != fingerprint:
        raise ValueError('GENOS preprocessor source changed while staging')
    evidence = _plain(Path(_evidence.get() or source.parent / 'preprocessor') / request_id)
    evidence.mkdir(parents=True, mode=0o700)
    remote_path = str(PurePosixPath(settings.remote_root) / request_id / 'source.pdf')
    params = {'img_desc': 0, 'chart_desc': 0, 'doc_summary': 0,
              'table_desc': 0, 'table_refine': 0, 'table_text_desc': 0}
    payload = {'file_path': remote_path, 'params': params}
    receipt = {'request_id': request_id, 'parser': settings.identity(),
               'source_sha256': fingerprint, 'status': 'STARTED',
               'staged_path': str(staged), 'request': payload}
    _save(evidence / 'request.json', receipt)
    headers = {}
    key = os.environ.get('GENOS_PREPROCESSOR_API_KEY', '')
    if key:
        headers['Authorization'] = 'Bearer ' + key
    started = time.monotonic()
    try:
        # No proxy-env routing, redirects, or retries for internal source paths.
        with httpx.Client(timeout=settings.timeout, trust_env=False, follow_redirects=False) as client:
            with client.stream('POST', settings.url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    raise ValueError(f'GENOS preprocessor HTTP {response.status_code}; check the selected endpoint')
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > settings.max_response_bytes:
                        raise ValueError('GENOS preprocessor response exceeds configured size limit')
        (evidence / 'response.json').write_bytes(raw)
        receipt['response_sha256'] = hashlib.sha256(raw).hexdigest()
        if _sha(staged) != fingerprint or _sha(source) != fingerprint:
            raise ValueError('GENOS preprocessor source changed during request')
        return decode_response(raw,source,settings,evidence,receipt,fingerprint)
    except httpx.RequestError:
        receipt['status'] = 'PENDING_OR_FAILED'
        raise ValueError('GENOS preprocessor connection/timeout failure; source retained, inspect server before retrying') from None
    except Exception:
        receipt['status'] = 'FAILED'
        raise
    finally:
        receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
        _save(evidence / 'receipt.json', receipt)


def decode_response(raw, source, settings, evidence, receipt, fingerprint):
    """One validation contract for HTTP and same-Pod responses."""
    request_id = receipt["request_id"]
    from docling_core.types.doc import DoclingDocument
    try:
        envelope = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('GENOS preprocessor returned invalid JSON') from None
    if not isinstance(envelope, dict) or envelope.get('code') not in (0, '0') or isinstance(envelope.get('code'), bool):
        raise ValueError('GENOS preprocessor reported failure; see private response.json and server logs')
    data = envelope.get('data')
    if isinstance(data, list) and settings.response_mode != 'docling':
        from .genos_chunks import assemble
        doc = assemble(data, source)
        _save(evidence / 'assembled-input.json', doc.dump())
        receipt.update(status='COMPLETED', response_format='chunks',
                       assembled_sha256=_sha(evidence / 'assembled-input.json'))
        return doc, {'request_id': request_id, 'response_sha256': receipt['response_sha256'],
                     'parser': settings.identity(), 'response_format': 'chunks',
                     'assembled_sha256': receipt['assembled_sha256']}
    if (settings.response_mode == 'chunks' or not isinstance(data, dict)
            or not isinstance(data.get('document'), dict)):
        raise ValueError('GENOS preprocessor requires data.document or a complete indexed chunk array')
    if data.get('schema_version') == '8agent-structured-pdf-v1':
        if (data.get('provenance') or {}).get('source_sha256') != fingerprint:
            raise ValueError('GENOS structured response source hash mismatch')
        receipt['server_provenance'] = data['provenance']
    try:
        doc = DoclingDocument.model_validate(data['document'])
    except Exception:
        raise ValueError('GENOS Docling JSON schema mismatch; check server/client docling-core versions') from None
    if not doc.pages or not (doc.texts or doc.tables):
        raise ValueError('GENOS preprocessor returned an empty PDF document')
    # Keep server-only media references as evidence, never fetch them from the
    # code-space. Rasterize the source locally when a picture is needed.
    for picture in doc.pictures:
        if picture.image and not str(picture.image.uri).startswith('data:image/'):
            picture.image = None
    receipt.update(status='COMPLETED', response_format='docling')
    return doc, {'request_id': request_id, 'response_sha256': receipt['response_sha256'],
                 'parser': settings.identity(), 'response_format': 'docling',
                 'server_provenance': receipt.get('server_provenance')}
