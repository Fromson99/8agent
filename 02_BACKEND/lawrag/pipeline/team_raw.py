"""Team-owned RAW working tree; immutable packages and historic paths stay intact.

CATALOG/TEAM_LAYOUT.json selects this tree, never an implicit latest directory.
Team membership is navigation metadata, not an access-control grant.
"""
from __future__ import annotations
import json
import re
import shutil
from pathlib import Path
from .genos_stages import plain_path
from . import genos_build as builder
from semantic_runtime.contracts import sha
from semantic_runtime.document_roles import role_of_row

VERSION = 'team-raw-v1'
RISK_NAMES = '''금융투자업규정
금융투자업규정시행세칙
자본시장과 금융투자업에 관한 법률
자본시장과 금융투자업에 관한 법률 시행령
자본시장과 금융투자업에 관한 법률 시행규칙
금융투자회사의 리스크관리 모범규준
금융투자회사의 영업 및 업무에 관한 규정
금융투자회사 표준내부통제기준
외국환거래법
외국환거래규정
상법
금융복합기업집단 감독규정
금융복합기업집단의 감독에 관한 법률
금융복합기업집단의 감독에 관한 법률 시행령
금융회사의 지배구조에 관한 법률
금융회사의 지배구조에 관한 법률 시행령
금융회사 지배구조 감독규정
금융회사 지배구조 감독규정 시행세칙
신용정보의 이용 및 보호에 관한 법률
전자금융감독규정
전자금융감독규정시행세칙
금융기관의 업무위탁 등에 관한 규정
은행업감독업무시행세칙
개인정보 보호법
개인정보 보호법 시행령
공공기관의 운영에 관한 법률
독점규제 및 공정거래에 관한 법률
독점규제 및 공정거래에 관한 법률 시행령'''.splitlines()


def segment(value):
    if not value or value in {'.', '..'} or any(c in value for c in '/\\'):
        raise ValueError('invalid path segment: ' + value)
    return value


def config(data):
    p = plain_path(Path(data) / 'CATALOG/TEAM_LAYOUT.json')
    if not p.exists():
        return None
    value = json.loads(p.read_text())
    if value.get('schema_version') != VERSION:
        raise ValueError('unknown team RAW layout')
    return value


def inputs(data, *, only_internal=False, exclude_internal=False, teams=None):
    """Read only the explicitly selected source/team branches; arbitrary teams work."""
    raw = plain_path(Path(data) / 'RAW')
    for source in ('internal', 'external'):
        if (source == 'internal' and exclude_internal) or (source == 'external' and only_internal):
            continue
        base = plain_path(raw / source)
        if not base.exists():
            continue
        for team in sorted(base.iterdir()):
            # Old internal categories remain as historical compatibility copies.
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*_team', team.name):
                continue
            if teams and team.name not in teams:
                continue
            plain_path(team)
            if not team.is_dir():
                raise ValueError('team must be a directory: ' + str(team))
            for path in sorted(team.rglob('*')):
                plain_path(path)
                if any(p.startswith('.') for p in path.relative_to(team).parts):
                    continue
                if path.is_file():
                    yield path, source, team.name


def migrate(data, *, apply=False):
    """Publish the selected documents into a new working tree with exact lineage.

    This is copy-on-migration: old scope/RAW readers must remain reproducible.
    The new marker makes old paths inactive for new builds, without deleting them.
    Caller owns the exclusive RAW lock.
    """
    from . import document_scope
    data = plain_path(data)
    existing = config(data)
    if existing:
        for rel, item in existing['files'].items():
            if sha(plain_path(data / rel)) != item['sha256']:
                raise ValueError('migrated file changed: ' + rel)
        return {'status': 'REUSED', 'files': len(existing['files'])}
    scope_path = document_scope.configured(data)
    scope = json.loads(scope_path.read_text()) if scope_path else {'documents': []}
    for receipt in scope.get('provenance', []):
        if sha(document_scope.local_path(data, receipt['path'])) != receipt['sha256']:
            raise ValueError('scope provenance changed')
    rows = {}

    def add(origin, rel, metadata):
        origin, target = plain_path(origin), plain_path(data / rel)
        identity = sha(origin)
        item = {**metadata, 'sha256': identity, 'original_path': str(origin.relative_to(data))}
        if rel in rows and rows[rel]['sha256'] != identity:
            raise ValueError('migration destination collision: ' + rel)
        if target.exists() and sha(target) != identity:
            raise ValueError('existing destination differs: ' + rel)
        rows.setdefault(rel, item)

    risk = {n.replace(' ', '') for n in RISK_NAMES}
    # Explicit completed conversion receipts, never a newest-file heuristic.
    hwpx_origins = {}
    packages = set()
    for doc in scope['documents']:
        for item in doc['files']:
            parts = Path(item['path']).parts
            if 'ARTIFACTS' in parts:
                packages.add(data.joinpath(*parts[:parts.index('ARTIFACTS')]))
    for package in sorted(packages):
        conversion = package / 'ARTIFACTS/CONVERSION_MANIFEST.json'
        if not conversion.exists():
            continue
        manifest = json.loads(plain_path(package / 'manifest.json').read_text())
        artifact = next((a for a in manifest['artifacts'] if a['path'] == 'ARTIFACTS/CONVERSION_MANIFEST.json'), None)
        if not artifact or sha(conversion) != artifact['sha256']:
            raise ValueError('package conversion manifest mismatch')
        for entry in json.loads(conversion.read_text()).get('items', []):
            if 'hwpx_sha256' in entry:
                hwpx_origins[entry['hwpx_sha256']] = entry['original_sha256']
    for receipt in (data / 'DERIVED/hancom-hwpx-20260917').glob('*/receipt.json'):
        entry = json.loads(plain_path(receipt).read_text())
        hwpx_origins.setdefault(entry['hwpx_sha256'], entry['original_sha256'])
    for doc in scope['documents']:
        for item in doc['files']:
            origin = document_scope.local_path(data, item['path'])
            if sha(origin) != item['sha256']:
                raise ValueError('scope source changed: ' + item['path'])
            source = item['source']
            team = 'risk_team' if source == 'internal' or doc['name'].replace(' ', '') in risk else 'financial_team'
            # Preserve original basename and document grouping, including attachments.
            parts = origin.parts
            matching = [i for i, part in enumerate(parts[:-1]) if part == doc['name']]
            tail = parts[matching[-1] + 1:] if matching else (origin.name,)
            rel = '/'.join(('RAW', source, team, segment(item['external_source']), segment(doc['name']), *tail))
            add(origin, rel, {**item, 'name': doc['name'] if item['role'] == 'body' else item.get('title', origin.stem),
                'team': team, 'scope_document': doc['name'], 'source_metadata': doc.get('source_metadata', {})})
            if source == 'external' and item.get('security_class') == 'public' and origin.suffix.lower() in {'.hwp', '.hwpx'}:
                fingerprint = hwpx_origins.get(item['sha256'], item['sha256'])
                receipt = data / 'DERIVED/hancom-pdf-20260917' / fingerprint / 'receipt.json'
                pdf = receipt.with_name('source.pdf')
                if receipt.exists():
                    rendered = json.loads(plain_path(receipt).read_text())
                    if rendered['original_sha256'] != fingerprint or sha(pdf) != rendered['pdf_sha256']:
                        raise ValueError('official PDF receipt mismatch')
                    add(pdf, str(Path(rel).with_suffix('.pdf')), {**rows[rel],
                        'render_origin': rel, 'conversion_receipt': str(receipt.relative_to(data)),
                        'conversion_receipt_sha256': sha(receipt)})
    if not scope_path:
        from .genos_corpus import SOURCES
        for external_source in SOURCES:
            base = data / 'RAW' / external_source
            if not base.exists():
                continue
            for origin in sorted(base.rglob('*')):
                plain_path(origin)
                if not origin.is_file():
                    continue
                relative = origin.relative_to(base)
                document = relative.parts[0] if len(relative.parts) > 1 else origin.stem
                team = 'risk_team' if document.replace(' ', '') in risk else 'financial_team'
                add(origin, 'RAW/external/' + team + '/' + external_source + '/' + str(relative),
                    {'source': 'external', 'team': team, 'external_source': external_source, 'kind': external_source,
                     'role': 'body', 'security_class': 'restricted', 'export_allowed': False})
    internal = data / 'RAW/internal'
    if internal.exists():
        for origin in sorted(internal.rglob('*')):
            plain_path(origin)
            rel = origin.relative_to(internal)
            if origin.is_file() and not re.fullmatch(r'.*_team', rel.parts[0]):
                add(origin, 'RAW/internal/risk_team/' + str(rel), {'source': 'internal', 'team': 'risk_team',
                    'kind': 'internal', 'external_source': 'internal', 'role': 'body',
                    'security_class': 'restricted', 'export_allowed': False})
    result = {'schema_version': VERSION, 'status': 'COMPLETED' if apply else 'PLANNED',
              'scope': {'path': str(scope_path.relative_to(data)), 'sha256': sha(scope_path)} if scope_path else None,
              'files': rows, 'risk_document_names': RISK_NAMES,
              'legacy_policy': 'historical paths retained, excluded from new team builds',
              'security_policy': 'team is metadata only; original security/export restrictions retained'}
    if apply:
        for rel, item in rows.items():
            origin, target = plain_path(data / item['original_path']), plain_path(data / rel)
            if sha(origin) != item['sha256']:
                raise ValueError('source changed before migration')
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                with target.open('xb') as out, origin.open('rb') as inp:
                    shutil.copyfileobj(inp, out)
            if sha(target) != item['sha256']:
                raise ValueError('migration checksum mismatch')
        for source in ('internal', 'external'):
            for team in ('risk_team', 'financial_team'):
                (data / 'RAW' / source / team).mkdir(parents=True, exist_ok=True)
        builder.atomic(data / 'LOGS/team-raw-migration/receipt.json', result)
        builder.atomic(data / 'CATALOG/TEAM_LAYOUT.json', result)
    return {'status': result['status'], 'files': len(rows), 'scope': result['scope'],
            'counts': {s + '/' + t: sum(r.startswith('RAW/' + s + '/' + t + '/') for r in rows)
                       for s in ('internal', 'external') for t in ('risk_team', 'financial_team')}}


def rollback(data, *, apply=False):
    """Restore previous build selection; preserve the new tree and every receipt."""
    from datetime import datetime, timezone
    data = plain_path(data)
    pointer = plain_path(data / 'CATALOG/TEAM_LAYOUT.json')
    if not pointer.exists():
        return {'status': 'NOT_ENABLED'}
    value = config(data)
    if value.get('scope'):
        from .document_scope import configured
        previous = configured(data)
        if previous is None or sha(previous) != value['scope']['sha256']:
            raise ValueError('previous scope changed; select rollback scope explicitly')
    if apply:
        archived = data / 'LOGS/team-raw-migration' / ('rollback-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.json')
        builder.atomic(archived, value)
        pointer.unlink()
    return {'status': 'ROLLED_BACK' if apply else 'ROLLBACK_PLANNED', 'team_files_deleted': False}


def collect(data, bindings=None, *, only_internal=False, exclude_internal=False, teams=None, emit=print,
            only_internal_pdf=False, limit=None):
    """Pair native/PDF inputs and keep origin/team/category names in source.sqlite."""
    cfg = config(data) or {'files': {}}
    rows, ignored, errors, assets = [], [], [], {}
    from .raw_preprocess import catalog
    derived_catalog = catalog(data)
    derivatives = derived_catalog['files']
    extractions = derived_catalog.get('extractions', {})
    def source_metadata(rel, depth=0):
        if rel in cfg['files']:
            return cfg['files'][rel]
        extraction = extractions.get(rel)
        if extraction:
            if depth > 3 or sha(plain_path(data / extraction['archive'])) != extraction['archive_sha256']:
                raise ValueError('extracted archive provenance changed')
            parent = source_metadata(extraction['archive'], depth + 1)
            return {**parent, 'sha256': extraction['sha256'], 'role': 'attachment', 'name': Path(rel).stem,
                    'original_path': extraction['archive'] + '!' + extraction['member']}
        return {}
    for path, source, team in inputs(data, only_internal=only_internal or only_internal_pdf,
                                    exclude_internal=exclude_internal, teams=teams):
        if derivatives.get(str(path.relative_to(data)), {}).get('kind') == 'xml_markdown_projection' or path.suffix.lower() not in builder.EXTENSIONS:
            ignored.append({'path': str(path), 'reason': 'archive_or_auxiliary'})
            continue
        if only_internal_pdf and path.suffix.lower() != '.pdf':
            continue
        try:
            rel = str(path.relative_to(data))
            meta = source_metadata(rel)
            if meta and sha(path) != meta['sha256']:
                raise ValueError('registered original changed; new migration required')
            one = builder.inventory(data / 'RAW', source, bindings, selected=[path])
            row = one['files'][0]
            assets.update(one['format_assets'])
            row.update(team=team, kind=meta.get('kind', source), external_source=meta.get('external_source', source),
                       raw_role=meta.get('role', 'body'), source_metadata={**meta.get('source_metadata', {}),
                           'security_class': meta.get('security_class', 'restricted'),
                           'export_allowed': meta.get('export_allowed', False)})
            if meta.get('name'):
                row['name'] = meta['name']
            if meta.get('title') and row['raw_role'] != 'body':
                row['source_title'] = meta['title']
            row['document_role'] = role_of_row(row)
            if meta.get('scope_document') and row['raw_role'] == 'body':
                row['representation_group'] = str(path.parent) + '/scope:' + meta['scope_document']
            row['original_path'] = meta.get('original_path', rel)
            rows.append(row)
        except Exception as exc:
            errors.append({'source': source, 'item': str(path), 'error': str(exc), 'scope': 'document'})
    # Generated sidecars inherit the exact origin's explicit representation group
    # and security contract; they cannot silently become independent documents.
    from .raw_preprocess import attach_derivatives
    rows = attach_derivatives(data, rows)
    rows, alternatives = builder.select_representations(rows)
    ignored.extend(alternatives)
    unique = {}
    for row in rows:
        if Path(row['path']).suffix.lower() == '.doc':
            errors.append({'source': row['source'], 'item': row['path'], 'scope': 'document', 'error': 'DOC requires companion PDF'})
            continue
        old = unique.get(row['document_id'])
        if old:
            authority = lambda r: (r['source'], r['external_source'], r['kind'], r['raw_role'], r['doc_type'], r['engine'],
                                  r['source_metadata'].get('security_class'), r['source_metadata'].get('export_allowed'))
            if authority(old) != authority(row):
                raise ValueError('duplicate content with conflicting security/authority')
            from .document_representations import merge_context
            merge_context(old, row)
        else:
            unique[row['document_id']] = row
    rows = list(unique.values())[:limit]
    plan = {'input_root': str(data / 'RAW'), 'files': rows, 'ignored': ignored, 'format_assets': assets,
            'bindings_sha256': sha(bindings) if bindings else None, 'input_contract': VERSION,
            'representation_policy': builder.REPRESENTATION_POLICY, 'all_corpus': True}
    report = {'files': rows, 'errors': errors, 'excluded': ignored, 'sources': {}, 'warnings': [],
              'aliases': [], 'manifest_hashes': {}, 'ok': bool(rows) and not errors, 'unique_documents': len(rows)}
    emit(f'[TEAM] {len(rows)} documents; {len(errors)} input errors')
    return plan, report
