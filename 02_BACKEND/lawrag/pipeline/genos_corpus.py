"""Explicit all-corpus raw selection and source-field parsing for GENOS DRAFT builds."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from semantic_runtime.contracts import sha
from semantic_runtime.genos_backend import safe
from semantic_runtime.document_roles import role_of_row
from . import genos_build as builder

SOURCES = ('law', 'krx', 'kofia', 'expc', 'fsc', 'moleg', 'prec')
CASE_SOURCES = {'expc', 'fsc', 'prec'}


def raw_path(corpus, source, value):
    """Accept bootstrapped absolute paths or historical portable corpus prefixes."""
    if not isinstance(value, str) or not value:
        raise ValueError('missing raw path')
    rel = PurePosixPath(value)
    if '..' in rel.parts:
        raise ValueError('parent traversal in raw path')
    p = Path(value)
    if not p.is_absolute():
        for prefix in (f'data/corpus/{source}/', f'01_DATA/corpus/{source}/',
                       f'corpus/{source}/', f'{source}/'):
            if value.startswith(prefix):
                p = corpus / source / value[len(prefix):]
                break
        else:
            p = corpus / source / value
    if any(x.is_symlink() for x in [p, *p.parents]):
        raise ValueError('raw symlink is not allowed: ' + str(p))
    p.resolve().relative_to((corpus / source).resolve())
    if not p.is_file() or p.stat().st_size == 0:
        raise ValueError('missing/empty raw file: ' + str(p))
    return p.resolve()


def collect(corpus, bindings=None, *, emit=print, skip_invalid=False, exclude_internal=False,
            internal_pdf_root=None, only_internal_pdf=False, limit=None, only_internal=False):
    """Select external RAW plus an explicit PDF-only internal root when supplied.

    The maintained CLI reads RAW/internal for every supported format.
    internal_pdf_root is retained only for explicitly selected compatibility callers.
    """
    if (only_internal_pdf or only_internal) and exclude_internal:
        raise ValueError('Cannot both select and exclude internal PDFs')
    if limit is not None and (not only_internal_pdf or type(limit) is not int or limit < 1):
        raise ValueError('Positive limit requires only_internal_pdf')
    corpus = Path(corpus).expanduser().absolute()
    if any(p.is_symlink() for p in [corpus, *corpus.parents]):
        raise ValueError('corpus root must not be a symlink')
    corpus = corpus.resolve(strict=internal_pdf_root is None)
    if corpus.exists() and not corpus.is_dir():
        raise ValueError('corpus root must be a directory')
    report = {'corpus_root': str(corpus), 'sources': {}, 'errors': [], 'excluded': [], 'aliases': [],
              'manifest_hashes': {}, 'warnings': [], 'files': []}
    internal_root = (Path(internal_pdf_root).expanduser().absolute()
                     if internal_pdf_root is not None else corpus / 'internal')
    if internal_pdf_root is not None:
        report['input_roots'] = {'external': str(corpus),
                                 'internal': None if exclude_internal else str(internal_root)}
    def error(source, item, exc, scope='document'):
        value = safe({'source': source, 'item': str(item), 'error': str(exc), 'type': type(exc).__name__, 'scope': scope})
        report['errors'].append(value)
        emit('[INPUT ERROR] ' + json.dumps(value, ensure_ascii=False))
    for folder in sorted(corpus.iterdir()) if corpus.is_dir() and not only_internal else []:
        if folder.is_dir() and folder.name not in {*SOURCES, 'internal'} and not folder.name.startswith('.'):
            report['excluded'].append({'source':folder.name,'path':str(folder),'reason':'source_not_selected'})
    try:
        if exclude_internal:
            # Do not walk, hash, or inspect protected internal documents.
            internal = {'files': [], 'ignored': [], 'format_assets': {},
                        'bindings_sha256': sha(bindings) if bindings else None}
            emit('[SCOPE] internal 제외: 검사/파싱/LLM/임베딩 대상 아님; 비율 분모에서 제외')
        elif internal_pdf_root is None and not internal_root.exists():
            internal={'files':[],'ignored':[],'format_assets':{},'bindings_sha256':sha(bindings) if bindings else None}
        elif skip_invalid or internal_pdf_root is not None or only_internal_pdf:
            root = internal_root
            if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
                raise ValueError('내규 입력 폴더 없음 또는 심볼릭 링크: ' + str(root))
            emit('[SCOPE] 내규 입력: ' + str(root))
            internal = {'files': [], 'ignored': [], 'format_assets': {}, 'bindings_sha256': sha(bindings) if bindings else None}
            for path in sorted(root.rglob('*')):
                rel = path.relative_to(root)
                if any(p.startswith('.') for p in rel.parts) or path.name.endswith('.genos.json') or path.name=='manifest.json':
                    continue
                if path.name.lower() in {'thumbs.db', 'desktop.ini'} or path.name.startswith('~$'):
                    report['excluded'].append({'source': 'internal', 'path': str(rel), 'reason': 'system_cache'})
                    continue
                if not path.is_symlink() and not path.is_file():
                    continue
                if only_internal_pdf and path.suffix.lower() != '.pdf':
                    continue
                if limit is not None and len(internal['files']) >= limit:
                    break
                if internal_pdf_root is not None and path.suffix.lower() != '.pdf' and not path.is_symlink():
                    report['excluded'].append({'source': 'internal', 'path': str(path), 'reason': 'non_pdf_internal'})
                    continue
                if path.suffix.lower() not in builder.EXTENSIONS and not path.with_name(path.name + '.genos.json').exists() and not path.is_symlink():
                    internal['ignored'].append(str(rel))
                    continue
                try:
                    if internal_pdf_root is not None and not path.is_symlink() and not path.stat().st_size:
                        raise ValueError('empty internal PDF')
                    one = builder.inventory(root, 'internal', bindings, selected=[path], allow_duplicates=True)
                    internal['files'].extend(one['files'])
                    internal['format_assets'].update(one['format_assets'])
                except Exception as exc:
                    error('internal', str(rel), exc)
        else:
            internal = builder.inventory(internal_root, 'internal', bindings, allow_duplicates=True)
        for row in internal['files']:
            row['relative'] = 'internal/' + row['relative']
            for field in ('aliases', 'representations', 'pdf_references'):
                for entry in row.get(field, []):
                    if not entry['relative_path'].startswith('internal/'):
                        entry['relative_path'] = 'internal/' + entry['relative_path']
                        entry['folder_names'] = ['internal', *entry.get('folder_names', [])]
                        entry['folder_path'] = ' > '.join(entry['folder_names'])
                        entry['display_name'] = 'internal > ' + entry['display_name']
            row['kind'] = 'internal'
            if internal_pdf_root is not None:
                row['input_collection'] = 'PDF/internal'
        report['files'].extend(internal['files'])
        report['excluded'].extend(internal.get('representation_exclusions',[]))
        if not exclude_internal:
            report['sources']['internal'] = {'selected': len(internal['files'])}
        for name in internal['ignored']:
            if name.lower().endswith('.zip') or not skip_invalid:
                report['excluded'].append({'source': 'internal', 'path': name, 'reason': 'archive' if name.lower().endswith('.zip') else 'unsupported'})
            if not name.lower().endswith('.zip'):
                error('internal', name, ValueError('unsupported document: add a registered format tag'))
        assets = dict(internal['format_assets'])
        bindings_sha = internal['bindings_sha256']
    except Exception as exc:
        error('internal', 'inventory', exc, 'source')
        assets, bindings_sha = {}, sha(bindings) if bindings else None

    def warning(source,item,exc):
        report['warnings'].append(safe({'source':source,'item':str(item),'warning':str(exc),
                                        'effect':'optional metadata ignored; physical files remain inputs'}))

    for source in (() if only_internal_pdf or only_internal else SOURCES):
        folder=corpus/source
        if not folder.exists():
            continue
        if folder.is_symlink():
            error(source,str(folder),ValueError('source directory symlink'),'source');continue
        hints={};manifest=folder/'manifest.json'
        if manifest.exists() or manifest.is_symlink():
            try:
                if manifest.is_symlink():raise ValueError('metadata symlink')
                data=json.loads(manifest.read_text())
                items=data.get('items') if isinstance(data,dict) else data
                if not isinstance(items,list):raise ValueError('metadata items must be a list')
                report['manifest_hashes'][source]=sha(manifest)
                for index,item in enumerate(items):
                    if not isinstance(item,dict) or item.get('status') not in (None,'ok','partial'):
                        warning(source,index,'invalid or failed legacy collection metadata');continue
                    group=f'legacy:{source}:{index}'
                    representations=[(item.get(k),item.get(h),'body',group,'') for k,h in
                                     [('file','sha256'),('body_file','body_sha256'),('body_html_file','body_html_sha256')]]
                    for attachment in item.get('attachments',[]):
                        role=str(attachment.get('role') or 'attachment')
                        representations.append((attachment.get('file'),attachment.get('sha256'),role,
                                                group if role=='body' else None,str(attachment.get('title') or '')))
                    for value,expected,role,representation,title in representations:
                        if not value:continue
                        try:
                            path=raw_path(corpus,source,value)
                            if expected and sha(path)!=expected:
                                raise ValueError('legacy metadata hash differs; use current file without stale metadata')
                            hint={'item':item,'role':role,'group':representation,'title':title}
                            if str(path) in hints and hints[str(path)]!=hint:
                                warning(source,value,'ambiguous metadata for same physical file');continue
                            hints[str(path)]=hint
                        except Exception as exc:warning(source,value,exc)
            except Exception as exc:warning(source,'manifest.json',exc)
        start=len(report['files'])
        for path in sorted(folder.rglob('*')):
            if any(x.startswith('.') for x in path.relative_to(folder).parts):continue
            if path.name=='manifest.json' or path.name.endswith('.genos.json'):continue
            if path.is_symlink():
                error(source,path,ValueError('raw symlink is not allowed'));continue
            if not path.is_file():continue
            if path.suffix.lower() not in builder.EXTENSIONS and not path.with_name(path.name+'.genos.json').exists():
                report['excluded'].append({'source':source,'path':str(path),'reason':'unsupported_or_metadata'});continue
            try:
                if not path.stat().st_size:raise ValueError('empty raw file')
                one=builder.inventory(corpus,'external',bindings,selected=[path])
                row=one['files'][0];assets.update(one['format_assets'])
                hint=hints.get(str(path),{});item=hint.get('item',{});role=hint.get('role','body')
                row.update(external_source=source,kind=str(item.get('kind') or source),raw_role=role,
                    source_metadata={k:item[k] for k in ('name','label','case_no','court','enforce','revised','replied','decided','edition') if k in item})
                if hint.get('group'):row['representation_group']=hint['group']
                if hint.get('title') and role!='body':row['source_title']=hint['title']
                row['document_role']=role_of_row(row)
                if source=='kofia' and role=='body' and path.suffix.lower() in {'.html','.htm'}:
                    from lawrag.core.batch import ATTACHMENT_ONLY_HTML_MARKERS
                    if any(marker in path.read_text(errors='replace') for marker in ATTACHMENT_ONLY_HTML_MARKERS):
                        report['excluded'].append({'source':source,'path':str(path),'reason':'attachment_index_not_body'})
                        continue
                if role=='body' and source in CASE_SOURCES and path.suffix.lower() in {'.xml','.html','.htm'}:
                    row['source_parser']=source
                if row['sidecar_sha256'] is None and (item.get('label') or item.get('name')):
                    row['name']=str(item.get('label') or item['name'])
                report['files'].append(row)
            except Exception as exc:error(source,path,exc)
        report['sources'][source]={'physical_inputs':len(report['files'])-start}
        emit(f'[0/5] {source}: 파일 기반 원문 {len(report["files"])-start}개 발견')

    report['files'],alternatives=builder.select_representations(report['files'])
    report['excluded'].extend(alternatives)
    for source,value in report['sources'].items():
        value['selected']=sum(r.get('external_source',r['source'])==source for r in report['files'])

    unique, blocked = {}, set()
    for row in report['files']:
        if Path(row['path']).suffix.lower() == '.doc':
            error(row['source'], row['relative'], ValueError('구형 DOC의 주 입력 PDF 없음: 같은 폴더에 같은 이름의 PDF를 반입하세요'))
            continue
        key = row['document_id']
        if key in blocked:
            error(row['source'], row['relative'], ValueError('same content with conflicting source authority/format'))
        elif key not in unique:
            unique[key] = row
        else:
            previous = unique[key]
            authority = lambda r: (r['sha256'], r['source'], r.get('external_source'), r.get('kind'), r.get('raw_role'), r.get('doc_type'), r.get('engine'))
            if authority(previous) != authority(row):
                error(row['source'], row['relative'], ValueError('same content with conflicting source authority/format'))
                if skip_invalid:
                    error(previous['source'], previous['relative'], ValueError('same content with conflicting source authority/format'))
                    del unique[key]
                    blocked.add(key)
                continue
            alias = builder.document_metadata(row)
            from .document_representations import merge_context
            merge_context(previous, row)
            report['aliases'].append({'document_id': key, **alias})
    report['files'] = list(unique.values())
    report['unique_documents'] = len(unique)
    report['ok'] = not report['errors'] and bool(unique)
    plan = {'input_root': str(corpus), 'files': report['files'], 'ignored': report['excluded'],
            'format_assets': assets, 'bindings_sha256': bindings_sha,
            'optional_metadata_hashes': report['manifest_hashes'], 'input_contract':'physical-files-v1',
            'representation_policy':builder.REPRESENTATION_POLICY,'all_corpus': True}
    if internal_pdf_root is not None:
        plan['input_roots'] = report['input_roots']
    if exclude_internal:
        selection = {'included': list(SOURCES), 'excluded': ['internal']}
        plan['source_selection'] = selection
        report['source_selection'] = selection
    elif only_internal:
        selection = {'included': ['internal'], 'excluded': list(SOURCES)}
        plan['source_selection'] = selection
        report['source_selection'] = selection
    return plan, report


def ingest_case(raw, filename, row, build):
    """Reuse existing source parsers; keep full precedent body, not case_text's search subset."""
    from lawrag.core import rawstore
    source = row['source_parser']
    text = raw.decode('utf-8-sig')
    if source == 'prec':
        from lawrag.sources.prec import parse_case
        case = parse_case(text)
        if not case.get('body'):
            raise ValueError('precedent full body missing')
    elif source == 'expc':
        from lawrag.sources.expc import parse_case
        case = parse_case(text)
        if not case.get('answer'):
            raise ValueError('interpretation answer missing')
    elif source == 'fsc':
        from lawrag.sources.fsc import parse_detail
        case = parse_detail(text)
        if not case.get('answer'):
            raise ValueError('FSC reply missing')
    else:
        raise ValueError('unsupported source parser: ' + source)
    blocks, nodes = [], []
    for field, value in case.items():
        if not isinstance(value, str) or not value.strip():
            continue
        index = len(blocks)
        blocks.append({'idx': index, 'text': value, 'node': index, 'kind': 'text', 'page': 1})
        nodes.append({'id': index, 'parent': None, 'family': 'source_field', 'title': field,
                      'surface': field, 'level': 1, 'span': [index, index+1], 'page': 1})
    rawstore.ensure(raw, filename, name=row['name'], folder=row['folder'], kind=row['kind'],
                    via='genos-all-corpus', corpus=build / 'corpus')
    folder = build / 'structure' / row['document_id']
    meta = {'doc_id': row['document_id'], 'name': row['name'], 'folder': row['folder'],
            'kind': row['kind'], 'passed': True, 'used_llm': False,
            'structured_by': 'source-fields:' + source}
    builder.atomic(folder / 'meta.json', meta)
    builder.atomic(folder / 'result.json', {'doc': row['name'], 'nodes': nodes, 'blocks': blocks,
                                         'source_parser': source, 'source_fields': case})
    return {'doc_id': row['document_id'], 'meta': meta}
