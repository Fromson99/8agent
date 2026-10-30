"""Same-Pod GENOS parser/converter. No cross-Pod filesystem path transport."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import hashlib
from functools import lru_cache
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

UPSTREAM = 'aa610c3db24aaa02c65e953279f1a60d014babaf'
VERSION = 'genos-pod-parser-v1'


def root():
    return Path(__file__).resolve().parents[3]


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def activate():
    vendor = root() / 'pod_vendor'
    if not (vendor / 'genon/preprocessor/facade/parser_processor.py').is_file():
        raise ValueError('POD_VENDOR_SOURCE_MISSING')
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    spec = importlib.util.find_spec('genon.preprocessor.facade.parser_processor')
    if not spec or Path(spec.origin).resolve() != (vendor / 'genon/preprocessor/facade/parser_processor.py').resolve():
        raise ValueError('POD_VENDOR_MODULE_COLLISION')
    return vendor


@dataclass(frozen=True)
class Settings:
    config: Path
    config_sha256: str
    runtime_sha256: str
    max_response_bytes: int
    response_mode: str = 'docling'

    @classmethod
    def from_env(cls):
        import yaml
        value = os.environ.get('GENOS_STRUCTURE_CONFIG', '').strip()
        if not value or not Path(value).is_absolute():
            raise ValueError('POD_PARSER_CONFIG_REQUIRED')
        config = Path(value)
        if not config.is_file():
            raise ValueError('POD_PARSER_CONFIG_MISSING')
        cfg = yaml.safe_load(config.read_text())
        if (not isinstance(cfg, dict) or cfg.get('enrichment') != [] or
            (cfg.get('output') or {}).get('format') != 'docling' or
            not isinstance(cfg.get('layout'), dict) or not isinstance(cfg.get('ocr'), dict)):
            raise ValueError('POD_PARSER_CONFIG_INVALID')
        layout = cfg['layout']
        if layout.get('layout_model_type') != 'genos_layout':
            raise ValueError('POD_GENOS_LAYOUT_CONFIG_REQUIRED')
        from urllib.parse import urlsplit
        endpoint = str((layout.get('genos_layout') or {}).get('endpoint', ''))
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or '<' in endpoint or parsed.username or parsed.password:
            raise ValueError('POD_GENOS_LAYOUT_CONFIG_REQUIRED')
        versions = {}
        for package in ('genon-docling','docling-core','docling-ibm-models','docling-parse','torch','transformers','PyMuPDF'):
            try: versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError: versions[package] = 'MISSING'
        versions['vendor'] = sha(root() / 'POD_VENDOR_SOURCE.json')
        versions['python'] = sys.version
        limit = int(os.environ.get('GENOS_PREPROCESSOR_MAX_RESPONSE_MB', '128'))
        if not 1 <= limit <= 512: raise ValueError('POD_RESPONSE_LIMIT_INVALID')
        return cls(config, sha(config), hashlib.sha256(json.dumps(versions,sort_keys=True).encode()).hexdigest(), limit*1024*1024)

    @property
    def revision(self):
        return UPSTREAM + ':' + self.config_sha256 + ':' + self.runtime_sha256

    def identity(self):
        return {'contract': VERSION, 'transport': 'same-pod', 'upstream_revision': UPSTREAM,
                'config_sha256': self.config_sha256, 'runtime_sha256': self.runtime_sha256,
                'response_mode': self.response_mode, 'output_format': 'docling',
                'required_server_enrichment': 'disabled'}


@lru_cache(maxsize=2)
def processor(settings):
    activate()
    path = root() / 'pod_parser.py'
    spec = importlib.util.spec_from_file_location('_lawrag_pinned_pod_parser', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DocumentProcessor(config_path=str(settings.config))


def preflight(settings):
    """Construct without processing a document or calling a model."""
    activate()
    from genon.preprocessor.facade.common.file_probe import has_any_pdf_converter
    if not has_any_pdf_converter():
        raise ValueError('POD_PDF_CONVERTER_MISSING')
    processor(settings)
    return {'ready': True, 'parser': settings.identity(), 'model_execution': 'NOT_TESTED'}


class Request:
    """Cancellation is owned by the worker process group, not an HTTP connection."""
    headers = {}
    async def is_disconnected(self):
        return False


def parse(source, settings):
    from . import genos_preprocessor as wire
    source = Path(source)
    fingerprint = sha(source)
    evidence = wire._plain(Path(wire._evidence.get() or source.parent/'preprocessor') / uuid.uuid4().hex)
    evidence.mkdir(parents=True,mode=0o700)
    staged = evidence / 'source.pdf'
    shutil.copyfile(source,staged)
    receipt = {'request_id': evidence.name,'parser':settings.identity(),'source_sha256':fingerprint,'status':'STARTED'}
    wire._save(evidence/'request.json',receipt)
    started = time.monotonic()
    try:
        if sha(staged) != fingerprint: raise ValueError('POD_SOURCE_COPY_CHANGED')
        if sha(settings.config) != settings.config_sha256: raise ValueError('POD_CONFIG_CHANGED')
        result = asyncio.run(processor(settings)(Request(), str(staged)))
        raw = json.dumps({'code':0,'data':result},ensure_ascii=False).encode()
        if len(raw) > settings.max_response_bytes: raise ValueError('POD_RESPONSE_TOO_LARGE')
        (evidence/'response.json').write_bytes(raw)
        receipt['response_sha256'] = hashlib.sha256(raw).hexdigest()
        if sha(source) != fingerprint or sha(staged) != fingerprint: raise ValueError('POD_SOURCE_CHANGED')
        if sha(settings.config) != settings.config_sha256: raise ValueError('POD_CONFIG_CHANGED')
        return wire.decode_response(raw,source,settings,evidence,receipt,fingerprint)
    except Exception as exc:
        receipt.update(status='FAILED',error_type=type(exc).__name__)
        raise
    finally:
        receipt['elapsed_seconds'] = round(time.monotonic()-started,3)
        wire._save(evidence/'receipt.json',receipt)


def convert(source, work):
    from lawrag.pipeline.raw_preprocess import pdf_check
    from .genos_preprocessor import _save, _plain
    activate()
    from genon.preprocessor.facade.common.pdf_convert import convert_to_pdf
    source,work = _plain(source),_plain(work)
    work.mkdir(parents=True,exist_ok=True)
    # ASCII staging avoids a known upstream non-ASCII output-name mismatch.
    staged = work / ('source'+source.suffix.lower())
    fingerprint = sha(source)
    evidence = {'transport':'same-pod','upstream_revision':UPSTREAM,'source_sha256':fingerprint,'status':'STARTED'}
    _save(work/'conversion.json',evidence)
    started = time.monotonic()
    try:
        with staged.open('xb') as dst,source.open('rb') as src: shutil.copyfileobj(src,dst)
        if sha(staged) != fingerprint: raise ValueError('POD_SOURCE_COPY_CHANGED')
        result = convert_to_pdf(str(staged),use_pdf_sdk=True)
        if result is None: raise ValueError('POD_PDF_CONVERSION_FAILED')
        pdf = _plain(result)
        if pdf != staged.with_suffix('.pdf') or not pdf.is_file(): raise ValueError('POD_PDF_OUTPUT_PATH_INVALID')
        pages = pdf_check(pdf)
        if sha(source) != fingerprint or sha(staged) != fingerprint: raise ValueError('POD_SOURCE_CHANGED')
        evidence.update(status='CONVERTED',pdf_path=str(pdf),pdf_sha256=sha(pdf),pages=pages)
        return pdf,evidence
    except Exception as exc:
        evidence.update(status='FAILED',error_type=type(exc).__name__)
        raise
    finally:
        evidence['elapsed_seconds'] = round(time.monotonic()-started,3)
        _save(work/'conversion.json',evidence)
