#!/usr/bin/env python3
"""뷰어 빌드 — React 앱과 데이터를 단일 HTML 로 인라인한다.

    .venv/bin/python build_viewer.py out/case_a/bundle.json out/case_a/viewer.html

node/npm 없이 동작한다. React·ReactDOM 은 vendor/ 의 UMD 번들을,
JSX 대신 htm(태그드 템플릿)을 쓴다. 외부 요청이 하나도 없어 오프라인·CSP 환경에서 그대로 열린다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
VENDOR = ROOT / "vendor"
FRONT = ROOT / "frontend"

TEMPLATE = """<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>{css}</style>
<div id="root"></div>
<script>{react}</script>
<script>{reactdom}</script>
<script>{htm}</script>
<script>window.__BUNDLE__ = {bundle};</script>
<script>{app}</script>
"""


def build(bundle_path: str, out_path: str) -> Path:
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    docs = bundle["report"]["documents"]
    title = f"신탁 대사 — {docs['contract'].get('title', '계약서')} ↔ {docs['statement'].get('title', '설명서')}"
    html = TEMPLATE.format(
        title=title,
        css=(FRONT / "styles.css").read_text(encoding="utf-8"),
        react=(VENDOR / "react.production.min.js").read_text(encoding="utf-8"),
        reactdom=(VENDOR / "react-dom.production.min.js").read_text(encoding="utf-8"),
        htm=(VENDOR / "htm.umd.js").read_text(encoding="utf-8"),
        # </script> 가 데이터에 들어가면 스크립트가 조기 종료된다
        bundle=json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/"),
        app=(FRONT / "app.js").read_text(encoding="utf-8"),
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    p = build(sys.argv[1], sys.argv[2])
    print(f"생성됨: {p}  ({p.stat().st_size / 1024:.0f} KB)")
