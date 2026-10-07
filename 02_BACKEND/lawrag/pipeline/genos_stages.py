"""Explicit, phase-major GENOS DRAFT workflow. No active generation is selected."""
from __future__ import annotations

import copy
from dataclasses import replace
import fcntl
import hashlib
import importlib.metadata
import inspect
import json
import os
import re
from pathlib import Path
import shutil
import sys
import time
import uuid

from . import genos_build as build
from semantic_runtime.contracts import digest, sha
from semantic_runtime.genos_backend import Genos, error_detail


def offline_data_root(root):
    """Explicit v2 offline migration/DRAFT location, NOT active runtime routing.

    The lean GENOS delivery does not carry the developer archive/research trees.
    inspection_path still validates this canonical root and incomplete-publication
    markers. Product readers continue using activation-bound workspace.path().
    """
    from lawrag.platform.workspace import load_layout
    return plain_path(load_layout(root).inspection_path('data', layout_version='v2'))


def plain_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('symlink path is not allowed: ' + str(path))
    return path


def files_hashes(folder):
    result = {}
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():
            raise ValueError('cache symlink is not allowed')
        if p.is_file() and p.name != 'structure-receipt.json':
            result[p.relative_to(folder).as_posix()] = sha(p)
    return result


def verify_structure(folder):
    folder = plain_path(folder)
    receipt = json.loads((folder / 'structure-receipt.json').read_text())
    if receipt['plan'] != json.loads((folder / 'prepared-plan.json').read_text()):
        raise ValueError('구조화 입력 계획/영수증 불일치')
    if receipt['key'] != structure_key(receipt['input_row'], receipt['plan'], receipt['parser']):
        raise ValueError('구조화 입력/파서 지문 불일치')
    if receipt['files'] != files_hashes(folder):
        raise ValueError('구조화 캐시 파일/해시 불일치: ' + str(folder))
    source = json.loads((folder / 'source.json').read_text())
    if source['sha256'] != sha(folder / 'source.sqlite'):
        raise ValueError('구조화 원문 SQLite 해시 불일치')
    return receipt


def parser_identity(root):
    """Excludes semantic authoring settings, but binds the structural VLM policy."""
    from lawrag.core.structure.recipe_runtime import policy_identity
    from lawrag.core.structure.recipe_basic import resources_identity
    paths = [*sorted((root / '02_BACKEND/lawrag/core').rglob('*.py')),
             *sorted((root / '02_BACKEND/lawrag/core').rglob('*.yaml')),
             *sorted((root / '02_BACKEND/lawrag/sources').rglob('*.py')),
             *[root / '02_BACKEND/lawrag/pipeline' / name for name in
               ('genos_corpus.py', 'genos_doc.py', 'genos_unified.py', 'genos_e2e.py',
                'genos_admission.py', 'genos_stages.py', 'document_representations.py', 'document_scope.py',
                'team_raw.py', 'raw_preprocess.py')]]
    versions = {}
    for name in ('docling', 'docling-core', 'pypdf', 'python-docx', 'lxml', 'beautifulsoup4'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    converter = shutil.which('libreoffice') or shutil.which('soffice')
    return {'code': {str(p.relative_to(root)): sha(p) for p in paths},
            'ingest': digest([inspect.getsource(f) for f in
                             (build.document_metadata, build.registered_ingest, build._ingest_files, build.source_jobs)]),
            'versions': versions, 'python': list(sys.version_info[:3]),
            'converter': sha(Path(converter).resolve()) if converter else None,
            'recipe': 'prepared-structure-v1', 'visual_structure': policy_identity(),
            'structure_resources_sha256': resources_identity()}


def structure_key(row, plan, dependencies):
    return digest({'row': row, 'format_assets': plan.get('format_assets', {}),
                   'bindings': plan.get('bindings_sha256'), 'parser': dependencies})


def structure(row, plan, data, dependencies, timeout, emit, *, pdf_parser=None):
    from .genos_doc import prepare
    from .document_representations import verify_representations
    verify_representations(row)
    key = structure_key(row, plan, dependencies)
    folder = plain_path(data / 'STRUCTURE' / key)
    locks = plain_path(data / 'STRUCTURE/.locks')
    locks.mkdir(parents=True, exist_ok=True)
    with plain_path(locks / key).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (folder / 'structure-receipt.json').exists():
            value = verify_structure(folder)
            if value['key'] != key:
                raise ValueError('structure identity mismatch')
            emit('[CACHE] 원문·파서 지문 일치: 저장된 추출 결과 재사용')
            return folder, value['plan']
        folder.mkdir(parents=True, exist_ok=True)
        files_hashes(folder)  # Reject links left in an incomplete cache before writes.
        work = copy.deepcopy(plan)
        from lawrag.core.genos_preprocessor import using
        with build.isolated(folder), using(pdf_parser, folder / 'preprocessor'):
            emit('[STRUCTURE STEP] ' + ('GENOS 전처리기 파싱 → Docling JSON 수신 → 구조화·좌표 보존'
                 if pdf_parser and Path(row['path']).suffix.lower() == '.pdf' else
                 '파일 변환·파싱 → PDF 구간별 틀 생성·구조화·bbox 검수'))
            work['files'] = [prepare(row, folder / 'conversions', timeout=timeout, emit=emit)]
            from lawrag.core.structure.recipe_runtime import progress_events
            with progress_events(emit):
                build.ingest_files(work, folder, emit)
            emit('[STRUCTURE STEP] 구조 SQLite 저장·원문 좌표·해시 보존')
            build.source_jobs(folder, work)
        emit('[STRUCTURE STEP] 구조 결과 저장·파일 해시 검증')
        build.atomic(folder / 'prepared-plan.json', work)
        build.atomic(folder / 'structure-receipt.json',
                     {'key': key, 'input_row': row, 'plan': work, 'files': files_hashes(folder), 'parser': dependencies})
        verify_structure(folder)
        return folder, work


def prepare_provider(provider, kind):
    """Only the requested stage's connection. Installed transport remains unchanged."""
    if not isinstance(provider, Genos):
        # Synthetic providers can explicitly implement the same phase contract.
        return provider.prepare_kind(kind)
    from semantic_runtime import genos
    target, configured = genos.from_env(kind)
    if not target.headers.get('Authorization'):
        raise ValueError('GENOS ' + kind + ' 인증키 없음')
    provider.targets[kind] = replace(target, max_retries=1, read_timeout=provider.timeout)
    provider.models[kind] = genos.advertised_model(provider.targets[kind], configured)
    return {'models': dict(provider.models), 'endpoints': {k: v.root for k, v in provider.targets.items()}}


def execute(plan, options, data, run_id, stage, *, provider_factory=Genos, progress, dependencies=None, status=None):
    """All structure first; failed documents remain individually accountable."""
    if stage not in {'all','structure','index'}:raise ValueError('Supported stages: structure, index, all; semantic extraction is retired')
    data = plain_path(data)
    dependencies = dependencies if dependencies is not None else ({} if stage == 'index' else parser_identity(build.ROOT))
    documents = plan['files']
    if not documents:
        raise ValueError('처리 가능한 원문 문서가 없습니다')
    from lawrag.core import genos_preprocessor
    mode = os.environ.get('GENOS_PDF_PARSER', 'preprocessor').strip()
    if stage != 'index' and mode not in {'preprocessor', 'local'}:
        raise ValueError('GENOS_PDF_PARSER must be preprocessor or local')
    pdf_parser = None
    if stage != 'index' and mode == 'preprocessor' and any(Path(r['path']).suffix.lower() == '.pdf' for r in documents):
        pdf_parser = genos_preprocessor.Settings.from_env()
        dependencies = {**dependencies, 'pdf_parser': pdf_parser.identity()}
        if not pdf_parser.revision:
            # No declared server version: reuse only within this explicit run.
            dependencies['unversioned_parser_run'] = run_id
    report = {'stage': stage, 'total': len(documents), 'documents': {}, 'activated': False}
    if pdf_parser:
        report['pdf_parser'] = pdf_parser.identity()
        report['preprocessor_model_calls'] = None  # The public parser response has no model usage contract.
        report['llm_calls_scope'] = 'source-term-indexing-only; parser/structural-VLM usage is separate'
    prepared = {}
    selection_path = plain_path(data / 'LOGS' / run_id / 'structure-selection.json')
    selection = None
    if stage == 'index':
        if not selection_path.is_file():
            raise ValueError('No completed structure selection; run --stage structure first')
        selection = json.loads(selection_path.read_text())
        if selection.get('schema_version') != 'structure-selection-v1':
            raise ValueError('Unsupported structure selection contract')
        if any(not re.fullmatch(r'[0-9a-f]{64}', item.get('key', ''))
               for item in selection['documents'].values()):
            raise ValueError('Invalid structure selection key')
        if selection['inputs_sha256'] != digest(plan):
            raise ValueError('Structure input selection changed; run structure with the selected inputs first')
    requested = ('index',) if stage in {'all','index'} else ()
    def record(did, phase, state, **details):
        if status is not None:
            status.update(did, phase, state, **details)
    for number, row in enumerate(documents, 1):
        did = row['document_id']
        progress.document(number, len(documents), row['relative'], '구조화')
        started = time.monotonic()
        folder = data / 'STRUCTURE' / (selection['documents'].get(did, {}).get('key', 'missing')
                                      if selection is not None else structure_key(row, plan, dependencies))
        reused = (folder / 'structure-receipt.json').is_file()
        record(did, 'structure', 'RUNNING', mode='REUSED' if reused else 'NEW', output_path=str(folder),
               route=build.route_summary(row), route_record='SELECTED')
        try:
            if sha(Path(row['path'])) != row['sha256']:
                raise ValueError('원문이 입력 점검 이후 변경됨')
            if stage in {'all', 'structure'}:
                folder, work = structure(row, plan, data, dependencies, options.timeout, progress.emit,
                                         pdf_parser=pdf_parser)
            else:
                if not (folder / 'structure-receipt.json').is_file():
                    raise ValueError('저장된 추출 결과 없음. 먼저 --stage structure 실행')
                if sha(folder / 'structure-receipt.json') != selection['documents'][did]['receipt_sha256']:
                    raise ValueError('Selected structure receipt changed')
                work = verify_structure(folder)['plan']
                progress.emit('[CACHE] 저장된 추출 결과 확인 (원문 재추출 없음)')
            report['documents'][did] = {'name': row['relative'], 'structure': 'PASSED',
                                       'structure_mode': 'REUSED' if reused else 'NEW'}
            meta = json.loads((folder / 'structure' / work['files'][0]['document_id'] / 'meta.json').read_text())
            admission = meta.get('structure_admission', {})
            review = meta.get('recipe_review')
            if review is not None and review.get('status') not in {'visual_approved', 'visual_sampled', 'accepted_with_warnings'}:
                raise ValueError('PDF 구조 검수 미완료: 후속 용어 색인 차단')
            report['documents'][did]['recipe_review'] = review
            report['documents'][did]['structure_warnings'] = admission.get('warnings',[])
            prepared[did] = (folder, work)
            counts = admission.get('counts', {})
            detail = (f'본문 {counts.get("blocks", "?")}블록 · 구조 {counts.get("nodes", "?")}마디 · '
                      f'구조 점수 {meta.get("score", "미기록")} (참고용, 탈락 기준 아님)')
            if admission.get('warnings'):
                detail += f' · 경고 {len(admission["warnings"])}건 (저장 및 후속 단계 진행)'
            record(did, 'structure', 'PASSED', mode='REUSED' if reused else 'NEW',
                   output_path=str(folder), elapsed_seconds=round(time.monotonic()-started, 3),
                   detail=detail, route_record='CACHE_VERIFIED' if reused else 'EXECUTED')
            progress.finish('저장된 구조화 재사용 완료' if reused else '신규 구조화 완료')
        except Exception as exc:
            prepared.pop(did, None)
            report['documents'][did] = {'name': row['relative'], 'structure': 'FAILED', 'error': error_detail(exc)}
            record(did, 'structure', 'FAILED', error=error_detail(exc), elapsed_seconds=round(time.monotonic()-started, 3))
            for phase in requested:
                record(did, phase, 'BLOCKED', error='구조화 실패로 실행하지 않음')
            progress.error(exc)
    if stage != 'index':
        build.atomic(selection_path, {
            'schema_version': 'structure-selection-v1', 'inputs_sha256': digest(plan),
            'completed': len(prepared) == len(documents),
            'expected_document_ids': sorted(row['document_id'] for row in documents),
            'documents': {did: {'key': folder.name,
                               'receipt_sha256': sha(folder / 'structure-receipt.json')}
                          for did, (folder, _) in prepared.items()}})
    for number,row in enumerate(documents,1):
        did=row['document_id']
        if did not in prepared or not requested:continue
        progress.document(number,len(documents),row['relative'],'용어·정의·참조 색인')
        started=time.monotonic()
        output=data/'TERM'/run_id/did
        record(did,'index','RUNNING',output_path=str(output))
        try:
            from .term_generation import build_generation
            if not options.glossary_dir:raise ValueError('A selected glossary is required')
            folder,work=prepared[did]
            result=build_generation(folder/'source.sqlite',options.glossary_dir,output)
            report['documents'][did]['index']='PASSED'
            report['documents'][did]['index_result']=result
            record(did,'index','PASSED',output_path=str(output),elapsed_seconds=round(time.monotonic()-started,3))
            progress.finish('용어·정의·참조 색인 및 DRAFT 적재 완료')
        except Exception as exc:
            report['documents'][did]['index']='FAILED';report['documents'][did]['error']=error_detail(exc)
            record(did,'index','FAILED',error=error_detail(exc),elapsed_seconds=round(time.monotonic()-started,3))
            progress.error(exc)
    last='index' if stage=='all' else stage
    passed=sum(v.get(last)=='PASSED' for v in report['documents'].values())
    report.update(passed=passed,skipped=len(documents)-passed,
                  passed_percent=round(100*passed/len(documents),2),ok=passed==len(documents),llm_calls=0)
    return report
