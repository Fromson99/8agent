"""Ordered preparation: safe ZIP merge -> XML Markdown -> missing sidecar PDF.

The PDF step covers PDF_SOURCES only: formats without a structure-reading parser
(.doc/.hwp and the Office tabular/presentation formats). Structured originals keep
their native route and never wait on the converter.

No model calls in this client. GENOS /run may continue parsing after conversion;
its backend behavior is distinct from client-side VLM policy.
Caller holds the exclusive RAW lock. Originals and existing PDFs are never replaced.
"""
from __future__ import annotations
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
from urllib.parse import urlsplit
import uuid
from xml.etree import ElementTree as ET
from .genos_stages import plain_path
from . import genos_build as builder
from semantic_runtime.contracts import sha

VERSION = 'raw-preparation-v1'
CONVERTIBLE = {'.xml', '.hwpx', '.hwp', '.docx', '.doc', '.html', '.htm', '.md', '.txt', '.xlsx', '.xls', '.pptx', '.ppt'}
# PDF 사이드카를 요청하는 형식만. 나머지(.xml/.hwpx/.docx/.html/.htm/.md/.txt)는
# 원문 자체에 구조가 있어 파서가 직접 읽고(document_representations.PRIORITY 에서
# PDF 보다 앞선다), 좌표·열람용 PDF 는 core.structure.synthpdf 가 만든다 —
# 변환기로 보내도 주 입력이 되지 않으므로 보내지 않는다.
PDF_SOURCES = {'.doc', '.hwp', '.xlsx', '.xls', '.pptx', '.ppt'}


def pdf_check(path):
    import fitz
    path = plain_path(path)
    with path.open('rb') as inp:
        if inp.read(5) != b'%PDF-':
            raise ValueError('not a PDF: ' + str(path))
    with fitz.open(path) as doc:
        if doc.needs_pass or doc.page_count < 1:
            raise ValueError('empty/encrypted PDF')
        for page in doc:
            _ = page.rect
        return doc.page_count


def publish(source, target):
    source, target = plain_path(source), plain_path(target)
    identity = sha(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha(target) != identity:
            raise ValueError('sidecar conflict; existing file preserved: ' + str(target))
        return
    fd, name = tempfile.mkstemp(prefix='.prepare-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
            shutil.copyfileobj(inp, out)
        if sha(name) != identity:
            raise ValueError('copy checksum differs')
        os.link(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def xml_markdown(source):
    """Deterministic readable projection of registered law XML, not a new authority."""
    from lawrag.core.structure import lawxml
    raw = source.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('XML DTD/entities not allowed')
    root = ET.fromstring(raw)
    if root.tag == '법령':
        tree, _ = lawxml.law_tree(root)
    elif root.tag == 'AdmRulService':
        tree, _ = lawxml.admrul_tree(root)
    else:
        raise ValueError('unsupported XML root; preserve original: ' + root.tag)
    tree += lawxml._appendix_units(root)
    lines = ['# ' + source.stem, '', '> XML 원문의 열람용 파생본. 별표의 외부 파일은 별도 원본을 확인하세요.', '']
    def walk(units, level=2):
        for unit in units:
            if unit.heading:
                lines.extend(['#' * min(level, 6) + ' ' + unit.heading, ''])
            lines.extend(text + '\n' for text in unit.content if text)
            walk(unit.children, level + 1)
    walk(tree)
    return '\n'.join(lines).encode('utf-8')


def convert(source, work):
    """Documented /run shared-file contract; return actual sidecar, never API text."""
    import httpx
    url = os.environ.get('GENOS_PDF_CONVERTER_URL', '').strip()
    if not url:
        ident = os.environ.get('GENOS_PDF_CONVERTER_ID', '187')
        if not ident.isdecimal():
            raise ValueError('invalid GENOS_PDF_CONVERTER_ID')
        url = f'http://preprocessor-{ident}:8080/run'
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('converter URL must be HTTP(S) without credentials/query')
    if parsed.path in {'', '/'}:
        url = url.rstrip('/') + '/run'
    elif parsed.path != '/run':
        raise ValueError('converter uses the documented /run endpoint')
    value = os.environ.get('GENOS_PDF_CONVERTER_SHARED_ROOT', '')
    if not value or not Path(value).is_absolute():
        raise ValueError('set GENOS_PDF_CONVERTER_SHARED_ROOT to the existing shared NFS directory')
    shared = plain_path(value)
    if not shared.is_dir():
        raise ValueError('converter shared root does not exist')
    remote = Path(os.environ.get('GENOS_PDF_CONVERTER_REMOTE_ROOT') or str(shared))
    if not remote.is_absolute() or '..' in remote.parts:
        raise ValueError('invalid converter remote root')
    timeout = int(os.environ.get('GENOS_PDF_CONVERTER_TIMEOUT', '900'))
    if not 1 <= timeout <= 7200:
        raise ValueError('converter timeout must be 1..7200 seconds')
    request_id = uuid.uuid4().hex
    staging = shared / ('pdf-' + request_id)
    staging.mkdir(mode=0o2770)
    os.chmod(staging, 0o2770)
    original = staging / ('source' + source.suffix.lower())
    publish(source, original)
    os.chmod(original, 0o660)
    identity = sha(original)
    payload = {'file_path': str(remote / staging.name / original.name),
               'params': {k: 0 for k in ('img_desc', 'chart_desc', 'doc_summary', 'table_desc', 'table_refine', 'table_text_desc')}}
    evidence = {'contract': VERSION, 'url': url, 'revision': os.environ.get('GENOS_PDF_CONVERTER_REVISION', ''),
                'request': payload, 'staging': str(staging), 'input_sha256': identity, 'status': 'PENDING'}
    builder.atomic(work / 'conversion.json', evidence)
    headers = {}
    if os.environ.get('GENOS_PDF_CONVERTER_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['GENOS_PDF_CONVERTER_API_KEY']
    try:
        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            with client.stream('POST', url, json=payload, headers=headers) as response:
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1024 * 1024:
                        break
                evidence['http_status'] = response.status_code
                try:
                    body = json.loads(raw)
                    evidence['api_code'] = body.get('code') if isinstance(body, dict) else None
                except ValueError:
                    evidence['api_code'] = None
    except httpx.TransportError as exc:
        # Preserve the request identity. Never automatically resubmit an uncertain job.
        evidence['transport_error_type'] = type(exc).__name__
        builder.atomic(work / 'conversion.json', evidence)
        raise ValueError('conversion pending; inspect saved staging job before a new run') from exc
    if sha(original) != identity:
        raise ValueError('converter modified original input')
    pdf = original.with_suffix('.pdf')
    try:
        evidence['pages'] = pdf_check(pdf)
    except Exception:
        evidence['status'] = 'PENDING' if evidence['http_status'] >= 500 else 'FAILED'
        builder.atomic(work / 'conversion.json', evidence)
        raise ValueError('converter returned no valid sidecar PDF; inspect ' + str(work))
    evidence.update(status='CONVERTED' if evidence['http_status'] == 200 and evidence['api_code'] == 0 else 'PDF_WITH_API_WARNING',
                    pdf_sha256=sha(pdf), pdf_path=str(pdf))
    builder.atomic(work / 'conversion.json', evidence)
    return pdf, evidence


def catalog(data):
    path = plain_path(data / 'CATALOG/RAW_DERIVATIVES.json')
    return json.loads(path.read_text()) if path.exists() else {'schema_version': VERSION, 'files': {}}


def attach_derivatives(data, rows):
    records = catalog(data)['files']
    by_path = {r['path']: r for r in rows}
    for row in rows:
        meta = records.get(str(Path(row['path']).relative_to(data)))
        if not meta:
            continue
        origin = plain_path(data / meta['origin'])
        if sha(origin) != meta['origin_sha256'] or sha(row['path']) != meta['sha256']:
            raise ValueError('derived companion or original changed')
        parent = by_path.get(str(origin))
        if parent:
            for key in ('kind', 'external_source', 'raw_role', 'source_metadata', 'name', 'representation_group',
                        'source_title', 'document_role'):
                if key in parent:
                    row[key] = parent[key]
            row['conversion'] = meta
    return rows


def run(root, data, logs, *, execute, unzip=True, xml_md=True, pdf=True,
        only_internal=False, exclude_internal=False, teams=None):
    from .team_raw import inputs, config
    filters = dict(only_internal=only_internal, exclude_internal=exclude_internal, teams=teams)
    registered = (config(data) or {'files': {}})['files']
    for path, _, _ in inputs(data, **filters):
        item = registered.get(str(path.relative_to(data)))
        if item and sha(path) != item['sha256']:
            raise ValueError('registered original changed before preparation: ' + str(path))
    logs.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': VERSION, 'execute': execute,
              'steps': ['zip', 'xml_markdown', 'missing_pdf'], 'files': [], 'errors': []}
    records = catalog(data)
    records.setdefault('extractions', {})
    report_path = logs / ('preparation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.json')
    def save():
        builder.atomic(report_path, report)
        if execute:
            builder.atomic(data / 'CATALOG/RAW_DERIVATIVES.json', records)
    def register(target, origin, kind, evidence=None):
        records['files'][str(target.relative_to(data))] = {
            'origin': str(origin.relative_to(data)), 'origin_sha256': sha(origin),
            'sha256': sha(target), 'kind': kind, 'evidence': evidence or {}}
        save()
    seen = set()
    if unzip:
        script = root / '06_TOOLS/OFFLINE/genos_unpack_internal.py'
        spec = importlib.util.spec_from_file_location('raw_zip_helper', script)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        for depth in range(4):
            archives = [p for p, _, _ in inputs(data, **filters) if p.suffix.lower() == '.zip' and str(p) not in seen]
            if not archives:
                break
            if depth == 3:
                raise ValueError('nested ZIP depth exceeds 3; inspect archives')
            for archive in archives:
                seen.add(str(archive))
                target_report = logs / ('zip-' + uuid.uuid4().hex + '.json')
                code = helper.run(SimpleNamespace(root=archive.parent, zip=[archive], encoding='cp949', layout='auto',
                    max_bytes=4 * 1024**3, report=target_report, apply=execute))
                report['files'].append({'step': 'zip', 'path': str(archive), 'report': str(target_report), 'ok': code == 0})
                if code:
                    save()
                    raise ValueError('ZIP merge conflict; originals preserved')
                if execute:
                    for item in json.loads(target_report.read_text())['files']:
                        records['extractions'][str(Path(item['target']).relative_to(data))] = {
                            'archive': str(archive.relative_to(data)), 'archive_sha256': item['zip_sha256'],
                            'member': item['member_name'], 'sha256': item['sha256']}
                    save()
            if not execute:
                break
    # XML projections first, all before any PDF request.
    originals = [(p, s, t) for p, s, t in inputs(data, **filters)
                 if p.suffix.lower() in CONVERTIBLE and str(p.relative_to(data)) not in records['files']]
    for source, _, _ in originals:
        if source.suffix.lower() != '.xml' or not xml_md:
            continue
        target = source.with_name(source.name + '.md')
        if execute:
            original_sha = sha(source)
            content = xml_markdown(source)
            if sha(source) != original_sha:
                raise ValueError('XML changed during Markdown conversion')
            with tempfile.TemporaryDirectory(dir=logs) as tmp:
                scratch = Path(tmp) / 'projection.md'
                scratch.write_bytes(content)
                publish(scratch, target)
            register(target, source, 'xml_markdown_projection')
        report['files'].append({'step': 'xml_markdown', 'source': str(source), 'target': str(target)})
    # Convert at most one preferred native representation for each same-name PDF.
    targets = {}
    from .document_representations import PRIORITY
    for source, _, _ in originals:
        if source.suffix.lower() not in PDF_SOURCES:
            continue
        target = source.with_suffix('.pdf')
        previous = targets.get(target)
        if previous is None or PRIORITY.get(source.suffix.lower(), 99) < PRIORITY.get(previous.suffix.lower(), 99):
            targets[target] = source
    for target, source in targets.items():
        item = {'step': 'missing_pdf', 'source': str(source), 'target': str(target)}
        report['files'].append(item)
        if target.exists():
            pdf_check(target)
            item['status'] = 'EXISTING'
            continue
        if not pdf:
            item['status'] = 'DISABLED'
            continue
        if not execute:
            item['status'] = 'PLANNED'
            continue
        original_sha = sha(source)
        key = sha(source) + '-' + __import__('hashlib').sha256(str(source).encode()).hexdigest()[:12]
        work = logs / key
        work.mkdir(exist_ok=True)
        old = work / 'conversion.json'
        if old.exists():
            evidence = json.loads(old.read_text())
            if evidence['status'] in {'CONVERTED', 'PDF_WITH_API_WARNING'}:
                converted = plain_path(evidence['pdf_path'])
                if sha(converted) != evidence['pdf_sha256']:
                    raise ValueError('saved conversion PDF changed')
                pdf_check(converted)
            else:
                raise ValueError('previous conversion failed/pending; inspect ' + str(old))
        else:
            try:
                converted, evidence = convert(source, work)
            except Exception as exc:
                report['errors'].append({'source': str(source), 'error': str(exc)})
                save()
                raise
        if sha(source) != original_sha:
            raise ValueError('original changed during PDF conversion')
        publish(converted, target)
        register(target, source, 'native_rendered_pdf', evidence)
        item['status'] = evidence['status']
    save()
    return {'path': str(report_path), 'sha256': sha(report_path),
            'pdf_statuses': {s: sum(r.get('status') == s for r in report['files'])
                             for s in ('EXISTING', 'CONVERTED', 'PDF_WITH_API_WARNING', 'PLANNED', 'DISABLED')}}
