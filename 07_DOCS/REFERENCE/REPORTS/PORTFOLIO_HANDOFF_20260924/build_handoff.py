#!/usr/bin/env python3
"""Build a read-only portfolio inventory and documents from existing records."""
from __future__ import annotations

import collections
import csv
import hashlib
import importlib.util
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RENDERER_PATH = Path('/mnt/c/Users/Jin/.codex/skills/implementation-design-report/scripts/build_report_docx.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')


def plain(text):
    text = re.sub(r'```.*?```', ' [코드·JSON 블록은 원본 참조] ', text, flags=re.S)
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'(?m)^\s*#{1,6}\s*', '', text)
    text = re.sub(r'[`*]', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def cut(text, size):
    return text if len(text) <= size else text[:size].rstrip() + ' … [발췌 생략]'


def metadata(text):
    result = {}
    match = re.match(r'\A---\s*\n(.*?)\n---\s*\n', text, re.S)
    if match:
        for key in ('adr_id', 'title', 'status', 'decision_date', 'phase', 'in_sample',
                    'decision_eligible', 'main_wiring', 'work_status'):
            found = re.search(r'^' + re.escape(key) + r':\s*(.*?)\s*$', match.group(1), re.M)
            if found:
                result[key] = found.group(1).strip('\"\'')
        body = text[match.end():]
    else:
        body = text
    if not result.get('title'):
        found = re.search(r'^#\s+(.+)', body, re.M)
        if found:
            result['title'] = found.group(1).strip()
    if not result.get('status'):
        found = re.search(r'(?im)^\s*[-*]?\s*(?:상태|status)\s*[:：]\s*\**\s*(Accepted|Rejected|Proposed|Superseded|Deprecated|Withdrawn)', body)
        if found:
            result['status'] = found.group(1)
    return result, body


def excerpts(body):
    starts = list(re.finditer(r'(?m)^#{2,3}\s+(.+)$', body))
    sections = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(body)
        heading = m.group(1).strip()
        value = body[m.end():end].strip()
        if re.search(r'결정 요약|결론|결과|해석|한계|판정|문제|가설|설계|운영 결정|요약|decision|result|limitation', heading, re.I):
            sections.append({'heading': heading, 'excerpt': cut(value, 5000), 'clipped': len(value) > 5000})
    priority = next((s['excerpt'] for s in sections if re.search(r'결정 요약|decision summary', s['heading'], re.I)), '')
    if not priority:
        priority = next((s['excerpt'] for s in sections if re.search(r'결론|결과|요약|result|decision', s['heading'], re.I)), '')
    if not priority:
        priority = re.sub(r'^#.*?\n', '', body, count=1).strip()
    return cut(plain(priority), 420), sections


def csv_write(name, rows, fields):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def catalog():
    records = []
    for base in ('04_EXPERIMENTS/LEGACY_ADR', '04_EXPERIMENTS/ADR'):
        for folder in sorted((ROOT / base).iterdir()):
            match = re.match(r'ADR-(\d+)', folder.name) if folder.is_dir() else re.match(r'(\d{4})-.*\.md$', folder.name)
            if not match:
                continue
            is_directory = folder.is_dir()
            path = folder / 'README.md' if is_directory else folder
            item = {'adr_id': f'ADR-{int(match.group(1)):04d}', 'directory': str(folder.relative_to(ROOT)),
                    'record_kind': 'directory' if is_directory else 'standalone_markdown',
                    'readme_present': path.is_file(), 'source_path': str(path.relative_to(ROOT)),
                    'status': '미확인', 'phase': '미기재', 'in_sample': '미기재',
                    'decision_eligible': '미기재', 'main_wiring': '미기재', 'work_status': '미기재'}
            if path.is_file():
                text = path.read_text(encoding='utf-8')
                meta, body = metadata(text)
                item.update(meta)
                item['summary_excerpt'], item['detail_excerpts'] = excerpts(body)
                item['sha256'] = digest(path)
                item['characters'] = len(text)
            else:
                item.update(title=folder.name, summary_excerpt='README 결정문이 없는 디렉터리. artifacts와 실험 자료의 존재만 확인했으며 판정·성과를 추정하지 않는다.', detail_excerpts=[], sha256=None, characters=0)
            records.append(item)
    records.sort(key=lambda r: (r['adr_id'], r['directory']))
    ids = collections.Counter(r['adr_id'] for r in records)
    stats = {'records': len(records), 'directories': sum(r['record_kind']=='directory' for r in records),
             'standalone_markdown_files': sum(r['record_kind']=='standalone_markdown' for r in records), 'unique_adr_ids': len(ids),
             'readmes': sum(r['readme_present'] for r in records),
             'duplicate_ids': {k: v for k, v in ids.items() if v > 1},
             'missing_readmes': [r['directory'] for r in records if not r['readme_present']],
             'status_counts_by_directory_not_unique_experiment': dict(collections.Counter(r['status'] for r in records))}
    write_json(OUT / 'adr_catalog.json', {'scope': 'Metadata and bounded extracts; not a new evaluation or final-status adjudication.', 'stats': stats, 'records': records})
    csv_write('adr_catalog.csv', records, ['adr_id', 'title', 'status', 'phase', 'in_sample', 'decision_eligible', 'main_wiring', 'work_status', 'decision_date', 'record_kind', 'directory', 'readme_present', 'summary_excerpt', 'sha256'])
    lines = ['# 부록 A. ADR 전수 기록 목록', '',
             f"수집 범위: 두 ADR 루트의 {stats['records']}개 기록 경로(디렉터리 {stats['directories']}개 + 초기 단일 Markdown {stats['standalone_markdown_files']}개), 고유 ADR 번호 {stats['unique_adr_ids']}개, 결정문 파일 {stats['readmes']}개.", '',
             '이 숫자는 성공 실험 수가 아니다. 정책·배선·마이그레이션·중단·기각·제안 기록을 포함한다. 중복 번호는 경로별로 보존했다. 판정은 결정문 메타데이터의 값이며 현재 배포 상태를 대신하지 않는다.', '',
             '아래 요약은 원본의 결정·결과 섹션에서 최대 420자를 발췌했다. 일부 표가 선형 텍스트로 표시될 수 있다. 더 긴 문제·설계·결과·한계 발췌는 adr_catalog.json에 수록했다. 원시 모델 입출력을 전수 복사한 자료는 아니다.', '',
             '중복 번호: ' + ', '.join(f'{k}({v}개 경로)' for k, v in stats['duplicate_ids'].items()) + '.', '',
             'README 없음: ' + '; '.join(stats['missing_readmes']) + '.', '']
    bucket = None
    for row in records:
        number = int(row['adr_id'].split('-')[1])
        current = (number // 50) * 50
        if current != bucket:
            bucket = current
            lines.extend([f'## ADR {current:04d}–{current+49:04d} 구간', ''])
        title = plain(row.get('title', row['adr_id']))
        lines.extend([f"### {row['adr_id']} · {title}", '',
                      f"상태: {row['status']} · phase: {row['phase']} · in_sample: {row['in_sample']} · decision_eligible: {row['decision_eligible']} · MAIN 기록: {row['main_wiring']}.", '',
                      row['summary_excerpt'], '', f"원본: `{row['source_path']}`", ''])
    appendix = '\n'.join(lines)
    (OUT / 'adr_appendix.md').write_text(appendix, encoding='utf-8')
    return records, stats, appendix


def document_inventory():
    records = []
    for path in sorted((ROOT / '07_DOCS').rglob('*.md')):
        if path.is_relative_to(OUT):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        title = re.search(r'^#\s+(.+)', text, re.M)
        records.append({'path': str(path.relative_to(ROOT)), 'title': plain(title.group(1)) if title else path.stem,
                        'sha256': digest(path), 'characters': len(text)})
    csv_write('document_inventory.csv', records, ['path', 'title', 'characters', 'sha256'])
    write_json(OUT / 'document_inventory.json', records)
    lines = ['# 부록 B. 저장소 문서 탐색 지도', '',
             f"기존 07_DOCS Markdown {len(records)}개를 경로·제목·hash로 목록화했다. 제목은 탐색용이며 현행 기능 판정이 아니다. 본 인계서 생성 파일은 집계에서 제외했다.", '']
    for row in records:
        lines.extend([f"- **{row['title']}** — `{row['path']}`", ''])
    return records, '\n'.join(lines)


def source_manifest():
    selected = [
        'AGENTS.md', 'README.md', 'GENOS.md', 'service.py', 'pyproject.toml',
        '00_SYSTEM/ARCHITECTURE.md', '00_SYSTEM/DATA_MODEL.md', '00_SYSTEM/PIPELINE.json',
        '00_SYSTEM/WORKSPACE.json', '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
        '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',
        '04_EXPERIMENTS/LEGACY_ADR/STANDARD.md', '04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md',
        '02_BACKEND/semantic_runtime/app.py', '02_BACKEND/semantic_runtime/pipeline.py',
        '02_BACKEND/semantic_runtime/legal_agent_adapter.py',
        '02_BACKEND/semantic_runtime/legal_agent/coordinator.py',
        '02_BACKEND/semantic_runtime/legal_agent/numbered_references.py',
        '02_BACKEND/semantic_runtime/legal_agent/question_obligations.py',
        '02_BACKEND/semantic_runtime/legal_agent/publication.py',
        '02_BACKEND/lawrag/agents/agent6/README.md',
        '03_FRONTEND/APPS/experiment-studio/README.md',
        '03_FRONTEND/APPS/experiment-studio/package.json',
    ]
    active = json.loads((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    selected.append(active['manifest_path'])
    return [{'path': p, 'sha256': digest(ROOT / p), 'bytes': (ROOT / p).stat().st_size} for p in selected]


def render(source, target, title, subtitle):
    from docx.shared import Pt
    spec = importlib.util.spec_from_file_location('portfolio_docx_renderer', RENDERER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class PortfolioRenderer(module.Renderer):
        def cover(self):
            p = self.doc.add_paragraph()
            p.paragraph_format.space_before = Pt(48)
            module.font(p.add_run('8-AGENT  /  PORTFOLIO KNOWLEDGE DOSSIER'), 10, module.TEAL, True)
            p = self.doc.add_paragraph()
            p.paragraph_format.space_before = Pt(18)
            module.font(p.add_run(self.title), 27, module.NAVY, True)
            p = self.doc.add_paragraph(self.subtitle)
            for run in p.runs:
                module.font(run, 11, '617585')
            self.doc.add_paragraph('아키텍처 · 도메인 지식 · AI 활용 · 실험 · 실패 분석 · 운영 · 포트폴리오 제작 지침')
            self.doc.add_paragraph('2026-09-24 기준. 프로젝트의 구현·실험·설계·현장 미확인을 구분한 인계 자료입니다.')
            self.doc.add_page_break()
            self.doc.add_heading('목차', level=1)
            for i, token in enumerate(self.tokens):
                if token.type == 'heading_open' and token.tag == 'h2':
                    p = self.doc.add_paragraph(module.plain(self.tokens[i+1]))
                    p.paragraph_format.space_after = Pt(2)
                    for run in p.runs:
                        module.font(run, 9, module.NAVY)
            self.doc.add_page_break()

    renderer = PortfolioRenderer(source, title, subtitle, author='8-AGENT Portfolio Handoff')
    doc = renderer.render()
    doc.save(target)
    return renderer.verify(target)


def main():
    records, stats, appendix = catalog()
    docs, docmap = document_inventory()
    master = (OUT / 'portfolio_master.md').read_text(encoding='utf-8')
    corpus_note = '\n\n## 40. 전수 목록화 결과\n\n'
    corpus_note += f"확인한 ADR 기록 경로는 {stats['records']}개(디렉터리 {stats['directories']}개, 초기 단일 Markdown {stats['standalone_markdown_files']}개), 고유 ADR 번호는 {stats['unique_adr_ids']}개, 결정문 파일은 {stats['readmes']}개다. 같은 번호의 중복 경로 {len(stats['duplicate_ids'])}종과 README 없는 경로 {len(stats['missing_readmes'])}개를 부록에 명시했다. 기존 문서 지도는 {len(docs)}개 Markdown을 포함한다. 이 수치는 실행·성공 횟수나 테스트 통과 수가 아니다.\n"
    combined = master + corpus_note + '\n\n' + appendix + '\n\n' + docmap + '\n'
    combined_path = OUT / '8-AGENT_AI_포트폴리오_통합인계서.md'
    combined_path.write_text(combined, encoding='utf-8')
    core_checks = render(OUT / 'portfolio_master.md', OUT / '8-AGENT_포트폴리오_핵심해설.docx',
                         '8-AGENT 포트폴리오 핵심 해설', '39개 주제 · 기술 사례 · 실험 근거 · 다른 AI용 제작 지침')
    all_checks = render(combined_path, OUT / '8-AGENT_AI_포트폴리오_통합인계서.docx',
                        '8-AGENT 프로젝트 종합 인계서',
                        f"핵심 해설 + ADR {stats['records']}개 경로 + 기존 문서 {len(docs)}개 지도")
    counts = {'test_python_files': len(list((ROOT/'05_TESTS').rglob('test_*.py'))),
              'semantic_runtime_python_files': len(list((ROOT/'02_BACKEND/semantic_runtime').rglob('*.py'))),
              'note': 'File counts only; not executed test count, passing tests, coverage, or engineering productivity.'}
    active = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    verification = {'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                    'work_type': 'read-only repository synthesis plus new documentation artifacts',
                    'adr_catalog': stats, 'existing_document_count': len(docs), 'file_counts': counts,
                    'active_pointer_snapshot': active, 'sources': source_manifest(),
                    'git_head_for_context_not_clean_release': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    'workspace_has_preexisting_uncommitted_changes': True,
                    'core_docx_checks': core_checks, 'full_docx_checks': all_checks,
                    'renderer_sha256': digest(RENDERER_PATH),
                    'product_tests_run': False, 'new_model_experiment_run': False,
                    'genos_connected': False, 'visual_page_render_checked': False,
                    'combined_markdown_characters': len(combined)}
    write_json(OUT / 'verification.json', verification)
    readme = f'''# 8-AGENT 포트폴리오 AI 인계 패키지

다른 AI에는 `8-AGENT_AI_포트폴리오_통합인계서.md` 또는 같은 이름의 DOCX 하나를 먼저 전달하세요.
핵심 설명만 빨리 읽으려면 `8-AGENT_포트폴리오_핵심해설.docx`를 사용하세요.

## 포함 파일

- 통합 Markdown/DOCX: 39개 본문 주제, 전수 목록 집계, ADR {stats['records']}개 경로의 요약, 기존 문서 {len(docs)}개 지도.
- portfolio_master.md / 핵심해설 DOCX: 사람이 종합한 본문. 주요 문제·설계·코드 경로·실험·한계·포트폴리오 문구.
- adr_appendix.md: 전수 ADR 목록만 별도 제공.
- adr_catalog.json: 상태·계보 필드와 더 긴 문제/설계/결과/한계 원문 발췌. 섹션별 5,000자 상한과 생략 표시.
- adr_catalog.csv: 정렬·검색용 평면 목록.
- document_inventory.json/csv: 기존 07_DOCS 문서 제목·경로·hash.
- verification.json: 생성 시점·출처 hash·DOCX 내용 보존 검사·미검증 범위.
- build_handoff.py: 생성 방식. 원본 프로젝트와 명시된 렌더러가 있어야 재생성 가능.

## 읽기 순서

1. 통합 문서 01~03으로 상태·사용 규칙을 이해합니다.
2. 04~30에서 기술·도메인·실험·운영을 읽습니다.
3. 31~37로 포트폴리오 구조와 프롬프트를 사용합니다.
4. 부록에서 빠진 소재를 찾아보고, 필요하면 adr_catalog.json의 긴 발췌를 읽습니다.

## 범위와 주의

ADR 기록 경로 {stats['records']}개(디렉터리 {stats['directories']}개와 초기 단일 Markdown {stats['standalone_markdown_files']}개)는 고유 번호 {stats['unique_adr_ids']}개이며 성공 실험 수가 아닙니다.
중복 번호와 결정문 누락은 그대로 표시했습니다. 과거 Accepted도 현행 배포·품질 인증과 다를 수 있습니다.
현재 로컬 포인터의 quality_certified=false를 보존했습니다. 실제 GENOS 확인이나 신규 모델 실험은 하지 않았습니다.
개인 기여·팀 규모·사업 성과·실제 운영 도입은 추가 확인이 필요합니다.
원 저장소의 내부 링크는 외부 AI가 열 수 없으므로 본문 설명과 내장 발췌를 우선 사용하세요.
원시 고객 데이터·키·전체 모델 프롬프트는 패키지에 넣지 않았습니다.
DOCX ZIP/XML·본문·표 보존을 검사했으며 페이지 렌더링을 통한 시각 검수는 수행하지 못했습니다.
'''
    (OUT / 'README.md').write_text(readme, encoding='utf-8')
    packaged = [p for p in OUT.iterdir() if p.is_file() and p.suffix in ('.md','.docx','.json','.csv','.py') and p.name != 'package_manifest.json']
    write_json(OUT / 'package_manifest.json', [{'file': p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(packaged)])
    with ZipFile(OUT/'8-AGENT_포트폴리오_AI_인계패키지.zip','w',ZIP_DEFLATED) as z:
        for path in sorted(packaged + [OUT/'package_manifest.json']):
            z.write(path, arcname=path.name)
    print(json.dumps({'stats':stats,'documents':len(docs),'combined_characters':len(combined),
                      'core_checks':core_checks,'full_checks':all_checks,
                      'files':[{ 'name':p.name,'bytes':p.stat().st_size} for p in sorted(OUT.iterdir()) if p.is_file()]},ensure_ascii=False))


if __name__ == '__main__':
    main()
