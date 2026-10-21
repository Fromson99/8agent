"""Build the local architecture report and its editable diagram; no runtime calls."""
from pathlib import Path
import base64
import hashlib
import html
import importlib.util
import json
import re
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageFont
from markdown_it import MarkdownIt
from docx.shared import Cm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = HERE / 'ARCHITECTURE.md'
TITLE = 'GENOS와 Oracle 기반 법률 지식 및 온톨로지 아키텍처'
FONT = Path('/mnt/c/Windows/Fonts/malgun.ttf')
BOLD = Path('/mnt/c/Windows/Fonts/malgunbd.ttf')
RENDERER = Path('/mnt/c/Users/Jin/.codex/skills/implementation-design-report/scripts/build_report_docx.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def diagram():
    width, height, scale = 1200, 1530, 2
    pic = Image.new('RGB', (width * scale, height * scale), '#ffffff')
    draw = ImageDraw.Draw(pic)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>']
    checks = []

    def text(x, y, value, size=24, color='#24354a', bold=False, max_width=None):
        font = ImageFont.truetype(str(BOLD if bold else FONT), size * scale)
        length = draw.textlength(value, font=font) / scale
        if max_width is not None:
            checks.append({'text': value, 'width': round(length, 1), 'limit': max_width})
            if length > max_width:
                raise ValueError('Diagram label overflow: ' + value)
        draw.text((x * scale, y * scale), value, fill=color, font=font, anchor='lt')
        svg.append(f'<text x="{x}" y="{y + size}" font-size="{size}" font-family="Malgun Gothic,Noto Sans CJK KR,sans-serif" font-weight="{700 if bold else 400}" fill="{color}">{html.escape(value)}</text>')

    def box(x, y, w, h, fill='#f4f7fb', stroke='#cbd5e1', radius=10):
        draw.rounded_rectangle((x * scale, y * scale, (x + w) * scale, (y + h) * scale), radius=radius * scale, fill=fill, outline=stroke, width=2 * scale)
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')

    def arrow(points, color='#667990', reverse=False):
        draw.line([(x * scale, y * scale) for x, y in points], fill=color, width=3 * scale)
        svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="3"/>')
        def head(a, b):
            x, y = b; ax, ay = a
            if x == ax:
                dy = 1 if y > ay else -1; tri = [(x, y), (x - 6, y - dy * 11), (x + 6, y - dy * 11)]
            else:
                dx = 1 if x > ax else -1; tri = [(x, y), (x - dx * 11, y - 6), (x - dx * 11, y + 6)]
            draw.polygon([(px * scale, py * scale) for px, py in tri], fill=color)
            svg.append(f'<polygon points="{" ".join(f"{px},{py}" for px,py in tri)}" fill="{color}"/>')
        head(points[-2], points[-1])
        if reverse: head(points[1], points[0])

    text(80, 24, '최종 목표 아키텍처', 35, '#123a57', True)
    text(80, 73, '수집 · 지식 구축 · 질문 처리 · 정정과 갱신의 전체 연결', 23)

    box(80, 120, 500, 105)
    box(620, 120, 500, 105)
    text(102, 138, '외규  |  법제처', 28, bold=True, max_width=450)
    text(102, 181, 'Dataiku 매일 배치 → API 중계서버', 23, max_width=455)
    text(642, 138, '내규  |  현업 데이터 포탈', 28, bold=True, max_width=450)
    text(642, 181, '파일 업로드 · 문서 정보 · 접근 범위', 23, max_width=455)
    arrow([(330, 225), (330, 265)])
    arrow([(870, 225), (870, 265)])

    box(80, 265, 1040, 210, '#edf7f6', '#8eb9b3')
    text(102, 280, 'Dataiku  |  수집과 지식 구축', 29, '#185a57', True)
    steps = [('원문 보존', '출처 · 판본 · 해시'), ('구조 복원', '구조적 파싱 · VLM'), ('연결과 검토', '용어 · 참조 · 의미 후보'), ('색인과 게시', '검증 · 새 버전 · 이행')]
    for i, (name, detail) in enumerate(steps):
        x = 101 + i * 255
        box(x, 337, 233, 105, '#ffffff', '#b5ceca')
        text(x + 13, 355, name, 27, bold=True, max_width=207)
        text(x + 13, 400, detail, 18, max_width=207)
        if i < 3: arrow([(x + 233, 388), (x + 254, 388)])
    arrow([(600, 475), (600, 535)])
    text(622, 488, '검증된 데이터와 지식 버전', 22)

    box(80, 535, 1040, 470, '#f1f5fb', '#97afc9')
    text(102, 552, 'Oracle  |  원문 · 온톨로지 · 위키 · 이력의 정본', 29, '#123a57', True, max_width=995)
    cards = [
        (105, 615, '원문 지식그래프와 용어집', '판본 · 계층 · 원문 · 정의 · 명시 참조'),
        (620, 615, '도메인 온톨로지', '개념 · 관계 · 적용 범위 · 예외 검토'),
        (105, 735, '조사 온톨로지', '목적 · 방법 · 읽기 계획 · 복귀 조건'),
        (620, 735, 'Legal Wiki', '쟁점별 지식 · 조건 · 근거 · 조사 절차'),
        (105, 855, '근거 관계와 검토 원장', '내규–외규 · 승인 · 취소 · 개정 대응'),
        (620, 855, 'Shortcut 실행 원장', '사건 · 사실 · 행동 · 판단 · 정정 이력'),
    ]
    for x, y, name, detail in cards:
        box(x, y, 475, 100, '#ffffff', '#c3d0df')
        text(x + 17, y + 15, name, 27, bold=True, max_width=441)
        text(x + 17, y + 60, detail, 21, max_width=441)
    text(105, 969, '공통 연결 키: ID · revision · 원문 근거 · 권한 · 적용 시점 · 릴리스', 22, max_width=990)
    arrow([(600, 1007), (600, 1065)], reverse=True)
    text(623, 1023, '허용 범위 조회 · 실행/검토 기록', 22)

    box(80, 1065, 1040, 275, '#f4f7fb', '#9aadc2')
    text(102, 1080, 'GENOS  |  사용자 질문과 Legal Agent 실행', 29, '#123a57', True)
    box(105, 1142, 245, 92, '#ffffff')
    text(123, 1155, '사용자 ↔ 채팅 앱', 25, bold=True, max_width=211)
    text(123, 1195, '질문 · 답변 · 정정', 22)
    arrow([(350, 1187), (397, 1187)], reverse=True)
    box(400, 1142, 695, 92, '#ffffff')
    text(419, 1155, 'Legal Agent + 내부 LLM', 27, bold=True, max_width=654)
    text(419, 1195, '목적 이해 → 근거 조사 → 의미 판단 → 인용·한계 표시', 22, max_width=654)
    text(105, 1257, '조회: 관련 부분그래프 + 현재 원문 + 위키 후보', 24, bold=True)
    text(105, 1298, '검증 캐시 활용 · 권한/판본/인용 검사 · 상태 보존 · 재개와 예산', 22)
    arrow([(600, 1340), (600, 1380)])
    box(80, 1380, 1040, 95, '#edf7f6', '#8eb9b3')
    text(105, 1394, '지식 갱신 루프', 27, '#185a57', True)
    text(105, 1436, '조사·정정 → Wiki 후보 → 개념·관계·방법 검토 → 새 버전 → 다음 질문', 23, max_width=990)
    arrow([(80, 1428), (35, 1428), (35, 375), (80, 375)], '#35877f')
    text(80, 1491, '목표 책임 배치도 · 각 영역의 현장 연결 상태는 상세 문서에서 구분', 20, '#667990')
    svg.append('</svg>')
    pic.save(HERE / 'architecture.png', optimize=True)
    (HERE / 'architecture.svg').write_text('\n'.join(svg), encoding='utf-8')
    return {'diagram_labels_fit': True, 'labels_checked': len(checks), 'canvas': [width, height]}


def evidence():
    active_path = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    active = json.loads(active_path.read_text())
    release_path = ROOT / active['manifest_path']
    release = json.loads(release_path.read_text())
    checked = [
        'service.py', '00_SYSTEM/PIPELINE.json', '00_SYSTEM/LEGAL_AGENT/domain-catalogue-v1.json',
        '02_BACKEND/semantic_runtime/oracle_dp.py', '02_BACKEND/semantic_runtime/oracle_dp_io.py',
        '02_BACKEND/semantic_runtime/oracle_dp_assets.py', '02_BACKEND/semantic_runtime/term_index.py',
        '02_BACKEND/semantic_runtime/legal_agent/domain_control.py',
        '02_BACKEND/semantic_runtime/legal_agent/shortcut_repository.py',
        '02_BACKEND/semantic_runtime/legal_agent/wiki_execution.py',
        '02_BACKEND/semantic_runtime/legal_agent/wiki_recall.py',
        '02_BACKEND/semantic_runtime/legal_agent/unified_runtime.py',
        '02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py',
        '02_BACKEND/lawrag/pipeline/wiki_proposal.py',
        '02_BACKEND/semantic_runtime/basis_links/service.py',
        '02_BACKEND/lawrag/pipeline/basis_lifecycle.py',
    ]
    rows = []
    for name in checked:
        work = ROOT / name; frozen = ROOT / release['code_root'] / name
        rows.append({'path': name, 'working_sha256': sha(work), 'selected_sha256': sha(frozen) if frozen.exists() else None,
                     'selected_manifest_sha256': release['files'].get(name),
                     'packaged_in_selected_release': frozen.exists() and name in release['files'],
                     'same': sha(work) == sha(frozen) if frozen.exists() else None,
                     'selected_hash_valid': sha(frozen) == release['files'].get(name) if frozen.exists() else None})
    docs = [
        'AGENTS.md', 'GENOS.md', '00_SYSTEM/ARCHITECTURE.md', '00_SYSTEM/DATA_MODEL.md',
        '00_SYSTEM/WORKSPACE.json', '00_SYSTEM/ONTOLOGY_PIPELINE.json',
        '07_DOCS/REFERENCE/OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md',
        '07_DOCS/REFERENCE/OPERATIONS/BASIS_LINK_LIFECYCLE_20261016.txt',
        '07_DOCS/REFERENCE/REPORTS/LEGAL_AGENT_ONTOLOGY_CONTROL_DESIGN_20261001.md',
        '07_DOCS/REFERENCE/REPORTS/SHORTCUT_LEGAL_WIKI_SYSTEM_DESIGN_20261005/README.md',
        '07_DOCS/REFERENCE/REPORTS/ONTOLOGY_RAG_LATENCY_DESIGN_20261009/README.md',
        '07_DOCS/REFERENCE/REPORTS/LEGAL_WIKI_DEDUCTIVE_COMPOSITION_20261009/README.md',
    ]
    result = {'schema_version': 'architecture-evidence-v1', 'report_date': '2026-10-17',
              'source': 'User-confirmed infrastructure on 2026-10-16; target-state request on 2026-10-17; local read-only code inspection.',
              'active_release': active, 'active_pointer_sha256': sha(active_path),
              'release_manifest_valid': sha(release_path) == active['release_manifest_sha256'],
              'code_checks': rows, 'documents': [{'path': n, 'sha256': sha(ROOT / n)} for n in docs],
              'review_type': 'self_review', 'new_model_calls': 0, 'runtime_tests_run': False,
              'genos_accessed': False, 'oracle_accessed': False, 'dataiku_accessed': False,
              'deployment_changed': False, 'active_pointer_changed': False,
              'scope_note': 'Logical target design is not a field deployment receipt or proof of existing Oracle KG schema.'}
    (HERE / 'EVIDENCE.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def html_report():
    md = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = md.parse(SOURCE.read_text())
    toc = []
    for i, token in enumerate(tokens):
        if token.type == 'heading_open':
            label = tokens[i + 1].content
            ident = 'section-' + str(len(toc) + 1)
            token.attrSet('id', ident)
            toc.append((token.tag, ident, label))
        if token.type == 'inline':
            for child in token.children or []:
                if child.type == 'image':
                    target = SOURCE.parent / child.attrGet('src')
                    child.attrSet('src', 'data:image/png;base64,' + base64.b64encode(target.read_bytes()).decode())
    content = md.renderer.render(tokens, md.options, {})
    navigation = ''.join(f'<a href="#{ident}">{html.escape(label)}</a>' for tag, ident, label in toc if tag == 'h2')
    css = '''body{margin:0;background:#f6f8fb;color:#24354a;font:16px/1.8 "Malgun Gothic","Noto Sans CJK KR",sans-serif}aside{position:fixed;inset:0 auto 0 0;width:255px;padding:28px 20px;box-sizing:border-box;overflow:auto;background:#123a57;color:white}aside strong{display:block;margin-bottom:18px;font-size:19px}aside a{display:block;color:#e5f1fb;text-decoration:none;margin:0 0 12px;font-size:14px;line-height:1.55}main{max-width:1060px;margin:0 auto 0 255px;padding:36px 45px 80px;background:white}h1{font-size:31px;line-height:1.4;color:#123a57}h2{font-size:25px;margin-top:56px;color:#185a57;border-bottom:2px solid #e1e9ef;padding-bottom:10px;scroll-margin-top:20px}h3{font-size:20px;color:#123a57;margin-top:35px}table{border-collapse:collapse;width:100%;font-size:14px;margin:22px 0;table-layout:fixed}th{background:#edf3f8;color:#123a57}td,th{border:1px solid #d7e1eb;padding:10px 12px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th:first-child{width:20%}a{color:#087b80}code{font-size:.9em;overflow-wrap:anywhere;background:#f2f5f8;padding:1px 3px}img{display:block;width:100%;max-width:850px;height:auto;margin:25px auto}p{overflow-wrap:anywhere}nav{font-size:14px;color:#667990}@media(max-width:1000px){aside{position:static;width:auto;max-height:none;padding:20px}aside a{display:inline-block;margin:5px 12px 5px 0}main{margin:0;padding:24px}table{font-size:13px}td,th{padding:7px}h1{font-size:26px}}@media print{aside{display:none}body{background:white;font-size:10pt}main{margin:0;padding:0;max-width:none}h2{break-after:avoid;margin-top:26px}h3{break-after:avoid}tr{break-inside:avoid}img{max-height:23cm;object-fit:contain}table{font-size:9pt}}'''
    result = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLE}</title><style>{css}</style></head><body><aside><strong>법률 지식 아키텍처</strong>{navigation}</aside><main>{content}</main></body></html>'
    (HERE / 'architecture.html').write_text(result, encoding='utf-8')
    return {'html_headings': len(toc), 'offline_figure_embedded': True}


def docx_report():
    spec = importlib.util.spec_from_file_location('architecture_report_renderer', RENDERER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class ImageRenderer(module.Renderer):
        def inlines(self, paragraph, children, size=10, header=False):
            for token in children or []:
                if token.type == 'image':
                    path = (self.source.parent / token.attrGet('src')).resolve()
                    run = paragraph.add_run()
                    shape = run.add_picture(str(path), width=Cm(16))
                    shape._inline.docPr.set('descr', token.content)
                    caption = self.doc.add_paragraph(token.content)
                    caption.paragraph_format.space_after = module.Pt(8)
                else:
                    # Preserve emphasis and links by handling non-image runs as a group below.
                    if not any(x.type == 'image' for x in children or []):
                        return super().inlines(paragraph, children, size=size, header=header)
                    super().inlines(paragraph, [token], size=size, header=header)

    renderer = ImageRenderer(SOURCE, TITLE, '최종 목표 체계 · 역할과 데이터 계약 · 현실적인 구현 순서 · 2026-10-17', author='8-AGENT')
    document = renderer.render()
    output = HERE / '법률지식_온톨로지_상세아키텍처.docx'
    document.save(output)
    checks = renderer.verify(output)
    with ZipFile(output) as archive:
        checks['embedded_images'] = len([n for n in archive.namelist() if n.startswith('word/media/')])
    checks['source_sha256'] = sha(SOURCE)
    checks['output_sha256'] = sha(output)
    checks['renderer_sha256'] = sha(RENDERER)
    return checks


def main():
    image_checks = diagram()
    from draw_knowledge_graph import build_graph
    graph_checks = build_graph(HERE)
    record = evidence()
    html_checks = html_report()
    doc_checks = docx_report()
    files = ['ARCHITECTURE.md', 'architecture.png', 'architecture.svg', 'architecture.html',
             'knowledge-graph.png', 'knowledge-graph.svg', 'draw_knowledge_graph.py',
             '법률지식_온톨로지_상세아키텍처.docx', 'EVIDENCE.json', 'build_artifacts.py']
    result = {'date': '2026-10-17', 'checks': {**image_checks, **graph_checks, **html_checks, 'docx': doc_checks},
              'inspected_code_files': len(record['code_checks']),
              'selected_code_checks': sum(x['packaged_in_selected_release'] for x in record['code_checks']),
              'all_selected_hashes_valid': all(x['selected_hash_valid'] for x in record['code_checks'] if x['packaged_in_selected_release']),
              'all_packaged_working_code_matches': all(x['same'] for x in record['code_checks'] if x['packaged_in_selected_release']),
              'files': {n: {'sha256': sha(HERE / n), 'bytes': (HERE / n).stat().st_size} for n in files}}
    (HERE / 'VALIDATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
