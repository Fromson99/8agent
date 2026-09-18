"""Final saved structure as offline HTML in the selected run's logs. No model calls."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import tempfile
from urllib.parse import quote

from semantic_runtime.contracts import sha


def _plain(path):
    path = Path(path).absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('보고서 경로에 링크 또는 상위 경로가 있습니다')
    return path


def _page(title, content):
    return '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>''' + html.escape(title) + '''</title><style>
body{font:16px system-ui,sans-serif;line-height:1.6;margin:24px;color:#172438;background:#f5f7fa}
a{color:#1753b8}nav{display:flex;gap:12px;flex-wrap:wrap}section,header{background:white;padding:20px;margin:18px 0;border:1px solid #ced7e3;border-radius:8px}
.pair{display:grid;grid-template-columns:1fr 1.3fr;gap:16px;align-items:start}figure{margin:0}img{width:100%;height:auto;border:1px solid #9caabd;background:white}figcaption{font-weight:bold}
.warning{color:#8c3500;background:#fff0d5;padding:12px}li{margin:6px 0}summary{cursor:pointer}code{overflow-wrap:anywhere}
@media(max-width:900px){.pair{grid-template-columns:1fr}}@media print{nav{display:none}section{break-before:page}}
</style><body>''' + content + '</body></html>'


def document_report(directory, row):
    """Validate the receipt; derive pictures from the final result, never an intermediate review."""
    from .genos_stages import verify_structure
    from lawrag.core.structure import recipe_evidence
    from .genos_build import atomic
    phase = row['phases']['structure']
    if phase['state'] != 'PASSED' or not phase.get('output_path'):
        from .genos_status import safe
        error = safe(str(phase.get('error') or ''))
        return {'status': 'unavailable', 'note': '저장된 구조화 성공 결과 없음' +
                (' · ' + error if error else '')}
    folder = _plain(phase['output_path'])
    receipt = verify_structure(folder)
    source = receipt['plan']['files'][0]
    pdf = _plain(source['path'])
    if pdf.suffix.lower() != '.pdf':
        return office_reference_report(Path(directory), folder, source)
    if sha(pdf) != source['sha256']:
        raise ValueError('저장 당시와 원본 PDF 해시가 다릅니다')
    result_path = _plain(folder / 'structure' / source['document_id'] / 'result.json')
    payload = json.loads(result_path.read_text())
    meta_path = result_path.with_name('meta.json')
    meta = json.loads(meta_path.read_text())
    binding = {'result_sha256': sha(result_path), 'source_sha256': source['sha256'],
               'meta_sha256': sha(meta_path), 'receipt_sha256': sha(folder/'structure-receipt.json'),
               'renderer_sha256': sha(Path(recipe_evidence.__file__)), 'report_sha256': sha(Path(__file__)),
               'title': row['title']}
    key = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    base = _plain(directory / 'structure-images');base.mkdir(exist_ok=True)
    destination = _plain(base / key)
    if destination.exists():
        saved = json.loads(_plain(destination/'report.json').read_text())
        if saved['binding'] != binding or any(sha(_plain(destination/name)) != value for name,value in saved['files'].items()):
            raise ValueError('이미지 보고서 해시 불일치')
        return {'status': 'ready', 'href': f'structure-images/{key}/index.html', 'pages': saved['pages'], 'reused': True}
    import fitz
    with fitz.open(pdf) as doc:
        pages = list(range(1, len(doc)+1))
    with tempfile.TemporaryDirectory(prefix='.render-', dir=base) as tmp:
        work = Path(tmp)
        _, evidence = recipe_evidence.payload_images(pdf, payload, pages, work/'images', include_data=False)
        esc = lambda value: html.escape(str(value))
        review = meta.get('recipe_review') or payload.get('recipe_review') or {}
        warnings = (meta.get('structure_admission') or {}).get('warnings', [])
        content = '<header><a href="../../doc-status.html">문서 상태표</a> · <a href="../../structure-images.html">이미지 목록</a>'
        content += '<h1>'+esc(row['title'])+'</h1><p>최종 저장된 구조화 결과 · '+str(len(pages))+'쪽</p>'
        content += '<p>검수 상태: <strong>'+esc(review.get('status', '모델 검수 기록 없음'))+'</strong></p>'
        content += '<p>실선: 구조 표제 · 점선: 소속 본문/표 · L: 계층 깊이 · parent: 상위 구조 · n: 구조 번호 · b: 본문 블록</p>'
        content += '<p>회색 또는 구조 미지정 원문은 자동으로 표제로 확정한 내용이 아닙니다. 박스가 없는 곳은 좌표 미확인일 수 있습니다.</p>'
        if warnings:
            content += '<details class="warning"><summary>구조화 경고 '+str(len(warnings))+'건</summary><pre>'+esc(json.dumps(warnings,ensure_ascii=False,indent=2))+'</pre></details>'
        if evidence['blocks_without_rectangles']:
            content += '<p class="warning">좌표 없는 블록 '+str(len(evidence['blocks_without_rectangles']))+'개: 박스를 추정하지 않았습니다.</p>'
        content += '<nav>'+''.join('<a href="#page-'+str(p)+'">'+str(p)+'쪽</a>' for p in pages)+'</nav></header>'
        nodes_by_page = {}
        for node in payload['nodes']:
            nodes_by_page.setdefault(node.get('page'), []).append(node)
        for page in pages:
            content += '<section id="page-'+str(page)+'"><h2>'+str(page)+'쪽</h2><div class="pair">'
            for kind, title in [('source','원본'),('viewer-overlay','최종 구조 박스')]:
                image = f'images/page-{page}-{kind}.png'
                content += '<figure><figcaption>'+title+'</figcaption><a href="'+image+'"><img loading="lazy" decoding="async" src="'+image+'" alt="'+str(page)+'쪽 '+title+'"></a></figure>'
            content += '</div><details><summary>이 페이지의 구조 표제</summary><ul>'
            for node in nodes_by_page.get(page, []):
                content += '<li>'+esc(f"n{node['id']} · L{node.get('level')} · {node.get('surface','')} {node.get('title','')}")+'</li>'
            content += '</ul></details></section>'
        (work/'index.html').write_text(_page(row['title'], content), encoding='utf-8')
        atomic(work/'report.json', {'binding': binding, 'pages': len(pages),
               'files': {p.relative_to(work).as_posix(): sha(p) for p in work.rglob('*') if p.is_file()}})
        work.rename(destination)
    return {'status':'ready', 'href':f'structure-images/{key}/index.html', 'pages':len(pages), 'reused':False}


def export_images(directory, report):
    """Best effort display artifacts cannot turn a saved structure success into failure."""
    from .genos_status import _atomic_text, safe
    directory = _plain(directory)
    records = {}
    items = []
    for row in report['documents']:
        try:
            record = document_report(directory, row)
        except Exception as exc:
            record = {'status':'error', 'note':'이미지 생성/검증 실패 ('+type(exc).__name__+'): '+safe(str(exc))[:600]}
        records[row['document_id']] = record
        title = html.escape(str(row['title']))
        if record['status'] == 'ready':
            suffix = '참고 PDF · 좌표 대응 미확인' if record.get('reference_only') else str(record['pages'])+'쪽'
            text = '<a href="'+quote(record['href'],safe='/')+'">'+title+'</a> · '+suffix
        else:
            text = title+' · '+html.escape(record['note'])
        items.append('<li>'+text+'</li>')
    content = '<h1>구조화 이미지</h1><p><a href="doc-status.html">문서 상태표</a></p><p>최종 저장 결과 기준입니다. 원본 이미지와 본문이 포함됩니다. 모델을 호출하지 않습니다.</p><ul>'+''.join(items)+'</ul>'
    _atomic_text(directory/'structure-images.html', _page('구조화 이미지', content))
    return records


def office_reference_report(directory, folder, source):
    """Expose paired PDFs without drawing native reflow coordinates on them."""
    import shutil
    result = folder/'structure'/source['document_id']/'result.json'
    payload=json.loads(result.read_text())
    references=payload.get('document_metadata',{}).get('pdf_references',[])
    if not references:return {'status':'not_pdf','note':'구조 정보 원본; 연결된 참고 PDF 없음'}
    key=hashlib.sha256((sha(result)+sha(folder/'structure-receipt.json')+sha(Path(__file__))).encode()).hexdigest()
    out=directory/'structure-images'/key;out.mkdir(parents=True,exist_ok=True)
    links=[]
    for r in references:
        pdf=_plain(result.parent/r['stored_path']);pdf.relative_to(result.parent)
        if sha(pdf)!=r['sha256']:raise ValueError('참고 PDF 해시 변경')
        target=out/(r['sha256']+'.pdf')
        if not target.exists():shutil.copyfile(pdf,target)
        if sha(target)!=r['sha256']:raise ValueError('참고 PDF 보고서 복사 해시 변경')
        links.append('<li><a href="'+target.name+'">'+html.escape(r['file_name'])+'</a></li>')
    title=payload.get('document_metadata',{}).get('display_name',source['name'])
    content='<h1>'+html.escape(title)+'</h1><p>HWPX/DOCX 등 구조 정보 원본으로 파싱했습니다. 아래 PDF는 화면 대조용이며, 원본 구조 좌표와 PDF 좌표의 대응은 미확인입니다. 구조 박스를 PDF에 겹쳐 그리지 않았습니다.</p><ul>'+''.join(links)+'</ul><a href="../../doc-status.html">문서 상태표</a>'
    (out/'index.html').write_text(_page(title,content),encoding='utf-8')
    return {'status':'ready','href':f'structure-images/{key}/index.html','pages':None,'reference_only':True,'reused':False}
