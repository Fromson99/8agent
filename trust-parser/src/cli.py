#!/usr/bin/env python3
"""진입점 — Part A(파싱·태깅) / Part B(정합성) 공용 CLI.

    python src/cli.py parse <pdf> -o out.chunks.json
    python src/cli.py reconcile <contract.chunks.json> <summary.pdf|md> -o out.reconcile.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ontology  # noqa: E402


def cmd_parse(args) -> int:
    import emit
    onto = ontology.load(args.ontology or ontology.default_path())
    doc, violations, meta = emit.run(args.pdf, onto, args.name)

    print(f"파서      {meta['parser']}  (born-digital={meta['born_digital']})")
    print(f"파트      {meta['parts']}")
    print(f"조        {meta['articles']}개")
    print(f"청크      {meta['chunks']}개")
    for key in ("parse_warnings", "structure_warnings", "tag_warnings"):
        for w in meta[key]:
            print(f"  ! {w}")
    v = meta["violations"]
    print(f"검증      위반 {v['total']}건 (error {v['error']} / warning {v['warning']})")
    for x in violations[:15]:
        print(f"  [{x.severity}] {x.shape}: {x.message}" + (f"  ({x.chunk_id})" if x.chunk_id else ""))
    if len(violations) > 15:
        print(f"  … 외 {len(violations)-15}건")

    # --- T6 / T17 — 기본 off, 플래그 뒤에서만 --------------------------------
    if args.llm_roles or args.llm_axioms:
        import llm_client
        llm = llm_client.LLM()
        print(f"\nLLM      {llm.model}")

        if args.llm_roles:
            import tag_llm
            roles, warns = tag_llm.enrich(doc.chunks, onto, llm, args.llm_limit)
            print(f"T6 의미역 {len(roles)}개 부여")
            from collections import Counter
            dist = Counter(r["semantic_role"] for r in roles.values())
            print("  분포   " + ", ".join(f"{k} {n}" for k, n in dist.most_common()))
            for c in doc.chunks[:10]:
                if c.chunk_id in roles:
                    r = roles[c.chunk_id]
                    print(f"    {c.chunk_id:16s} {r['semantic_role']:4s} "
                          f"{r['confidence']:.2f}  {r['rationale'][:52]}")
            for w in warns[:5]:
                print(f"  ! {w}")

        if args.llm_axioms:
            import axiom_extract
            axioms, warns = axiom_extract.extract(doc.chunks, onto, llm, args.llm_limit)
            print(f"T17 공리 후보 {len(axioms)}건 (전부 approved=false)")
            for a in sorted(axioms, key=lambda x: -x["confidence"])[:12]:
                dup = " [이미 온톨로지에 있음]" if a["already_in_ontology"] else ""
                print(f"    {a['confidence']:.2f} {a['kind']:13s} {a['rule'][:56]}{dup}")
                print(f"         근거: {a['quote'][:70]}")
            for w in warns[:5]:
                print(f"  ! {w}")
            if args.out:
                cand = Path(args.out).with_suffix(".axioms.yaml")
                cand.write_text(axiom_extract.to_yaml_block(axioms), encoding="utf-8")
                print(f"  후보 저장 {cand}")

        t = llm.totals()
        print(f"LLM 합계 호출 {t['calls']}  입력 {t['input_tokens']:,} 출력 "
              f"{t['output_tokens']:,} 토큰  오류 {t['errors']}")
        if args.llm_log:
            print(f"  기록    {llm.dump_log(args.llm_log)}")

    if args.out:
        p = emit.write(doc, args.out)
        print(f"저장      {p}")
    return 1 if v["error"] else 0


def cmd_reconcile(args) -> int:
    import reconcile, reconcile_emit
    onto = ontology.load(args.ontology or ontology.default_path())
    report = reconcile.run(args.contract, args.summary, onto)
    print(reconcile_emit.to_text(report))
    if args.out:
        p = reconcile_emit.write(report, args.out)
        print(f"저장      {p}")
    return 1 if report.stats.get("value_mismatch", 0) or report.stats.get("missing", 0) else 0


def cmd_query(args) -> int:
    """Part D — 결정론 라우터. 임베딩 없음(§D1), 매 단계가 설명 가능하다."""
    import chunk_search, fact_query, query_router
    from schema import ChunkDocument

    onto = ontology.load(args.ontology or ontology.default_path())
    doc = ChunkDocument.model_validate(
        json.loads(Path(args.chunks).read_text(encoding="utf-8")))

    llm = None
    if args.llm:
        import llm_client
        llm = llm_client.Client()

    topics = sorted({c.topic for c in doc.chunks if c.topic})
    route = query_router.classify(args.question, onto, topics, llm=llm)
    print(f"질의      {args.question}")
    print(f"분류      intent={route.intent}  field={route.field}  role={route.role}"
          f"  conf={route.confidence:.2f}")
    print(f"경로      {' → '.join(route.path) or '(규칙 미적중)'}")

    # 1) 값 질문은 fact 에서 끝난다 (§D2-2)
    if route.intent == "value" and route.field:
        ans = fact_query.FactStore(doc, onto).get(route.field)
        if ans.found:
            print(f"\n답변      {ans.field_name} = {ans.value}")
            print(f"원문      {ans.raw}")
            if ans.derived_from:
                print(f"계산      {ans.derived_from}")
            if ans.source:
                print(f"근거      {ans.source.get('doc')} p.{ans.source.get('page')}")
            return 0
        print(f"\n답변      찾지 못했습니다 — {ans.note}")
        print("          청크 검색으로 넘어갑니다\n")

    # 2) 해석 질문·fact 미스는 청크 검색 (§D2-3~5)
    cand = chunk_search.facet_filter(doc, topic=route.topic, role=route.role)
    if not cand:
        cand = None
    idx = chunk_search.ChunkIndex(doc)
    hits = idx.search(route.keywords, candidates=cand, top=args.top)
    if not hits:
        print("\n검색      일치하는 청크가 없습니다")
        return 1

    print(f"\n검색      {len(hits)}건 (facet 후보 {len(cand) if cand else len(doc.chunks)})")
    for h in hits:
        c = h.chunk
        print(f"  [{h.score:>6}] {c.chunk_id}  {c.topic}  ({'·'.join(h.why)})")
        print(f"           {c.text.strip().splitlines()[0][:70]}")

    extra = chunk_search.expand_refs(doc, hits, onto)
    if extra:
        print(f"참조확장  {len(extra)}건: {', '.join(c.chunk_id for c in extra[:6])}")

    ctx = chunk_search.serve_small_to_big(doc, hits[0].chunk)
    print(f"컨텍스트  {hits[0].chunk.article or hits[0].chunk.chunk_id} 전체 {len(ctx)}청크 서빙")
    return 0


# ---------------------------------------------------------------------------
# 뷰어 — 빌드 도구 없이 브라우저에서 결과를 본다
# ---------------------------------------------------------------------------

def _viewer_payload(onto, root: Path) -> dict:
    """out/ 과 골든 쌍을 훑어 뷰어가 읽을 번들 하나로 만든다.

    대사 리포트는 **읽지 않고 다시 돌린다** — 결정론이라 재현되고,
    발화 통계 같은 새 필드가 옛 파일에 없어도 화면이 최신을 보여준다.
    """
    from datetime import datetime

    import reconcile

    docs, reports, seen = [], [], set()

    for pair in sorted((root / "data" / "golden_pairs").glob("*")):
        contract, summary = pair / "contract.chunks.json", pair / "summary.md"
        if not (contract.exists() and summary.exists()):
            continue
        rep = reconcile.run(contract, summary, onto)
        d = rep.model_dump(mode="json")
        d["name"] = pair.name
        reports.append(d)
        seen.add(pair.name)

    for f in sorted((root / "out").glob("*.reconcile.json")):
        name = f.stem.replace(".reconcile", "")
        if name in seen:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        d["name"] = name
        reports.append(d)

    for f in sorted((root / "out").glob("*.chunks.json")) + sorted(
            (root / "data" / "golden_pairs").glob("*/*.chunks.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        d["path"] = str(f.relative_to(root))
        docs.append(d)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ontology": onto.model_dump(mode="json", exclude_none=True),
        "docs": docs,
        "reports": reports,
    }


def cmd_serve(args) -> int:
    import http.server
    import socketserver
    import urllib.parse
    import webbrowser

    root = Path(__file__).resolve().parent.parent
    onto = ontology.load(args.ontology or ontology.default_path())

    payload = _viewer_payload(onto, root)
    (root / "out").mkdir(exist_ok=True)
    (root / "out" / "viewer.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"번들      out/viewer.json  (문서 {len(payload['docs'])} · 대사 {len(payload['reports'])})")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def log_message(self, *a):        # 요청 로그로 콘솔을 채우지 않는다
            pass

        def do_GET(self):
            if self.path.startswith("/api/query"):
                return self._query()
            if self.path in ("/", "/index.html"):
                self.path = "/viewer/index.html"
            return super().do_GET()

        def _query(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            question = (qs.get("q") or [""])[0]
            idx = int((qs.get("doc") or ["0"])[0])
            try:
                body = _run_query(payload["docs"][idx], question, onto)
            except Exception as exc:                     # 뷰어가 죽지 않게 한다
                body = {"error": f"{type(exc).__name__}: {exc}"}
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    # WSL·컨테이너에서 바깥(Windows) 브라우저가 닿아야 하므로 기본이 0.0.0.0 이다.
    # 127.0.0.1 로만 열면 WSL2 의 localhost 포워딩이 꺼진 환경에서 접속이 안 된다.
    with socketserver.ThreadingTCPServer((args.host, args.port), Handler) as srv:
        url = f"http://localhost:{args.port}/"
        print(f"뷰어      {url}   (Ctrl-C 로 종료)")
        for ip in _local_ips():
            print(f"          http://{ip}:{args.port}/   ← localhost 로 안 되면 이쪽")
        if not args.no_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass                      # WSL 등 브라우저가 없는 환경 — 주소만 찍고 넘어간다
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n종료")
    return 0


def _local_ips() -> list[str]:
    """바깥에서 접속할 때 쓸 IP. WSL 은 eth0 주소로 들어와야 하는 경우가 있다."""
    import socket
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))          # 패킷을 보내진 않는다 — 라우팅만 물어본다
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return out


def _run_query(doc_json: dict, question: str, onto) -> dict:
    """Part D 라우터를 뷰어용 JSON 으로. CLI 의 cmd_query 와 같은 경로를 탄다."""
    import chunk_search, fact_query, query_router
    from schema import ChunkDocument

    doc = ChunkDocument.model_validate(doc_json)
    topics = sorted({c.topic for c in doc.chunks if c.topic})
    route = query_router.classify(question, onto, topics)
    out: dict = {"route": {"intent": route.intent, "field": route.field,
                           "topic": route.topic, "role": route.role,
                           "confidence": route.confidence, "path": route.path},
                 "answer": None, "hits": [], "expanded": [], "context": [],
                 "candidates": len(doc.chunks)}

    if route.intent == "value" and route.field:
        a = fact_query.FactStore(doc, onto).get(route.field)
        out["answer"] = {"field_name": a.field_name, "value": str(a.value),
                         "raw": a.raw, "source": a.source,
                         "derived_from": a.derived_from, "found": a.found,
                         "note": a.note}
        if a.found:
            return out

    cand = chunk_search.facet_filter(doc, topic=route.topic, role=route.role) or None
    out["candidates"] = len(cand) if cand else len(doc.chunks)
    hits = chunk_search.ChunkIndex(doc).search(route.keywords, candidates=cand, top=8)
    out["hits"] = [{"score": h.score, "chunk_id": h.chunk.chunk_id,
                    "topic": h.chunk.topic, "why": h.why, "text": h.chunk.text}
                   for h in hits]
    if hits:
        out["expanded"] = [c.chunk_id for c in chunk_search.expand_refs(doc, hits, onto)]
        out["context"] = [c.chunk_id for c in
                          chunk_search.serve_small_to_big(doc, hits[0].chunk)]
    return out


def cmd_bootstrap(args) -> int:
    """VLM 1차 스캔 → 온톨로지 초안 제안 (자동 적용 안 함)."""
    import bootstrap, llm_client, parse_stage
    onto = ontology.load(args.ontology or ontology.default_path())
    parsed = parse_stage.parse(args.pdf)
    llm = llm_client.LLM()
    print(f"VLM      {llm.model}")

    proposal, warns = bootstrap.scan(args.pdf, parsed, llm, onto, args.max_pages)
    if not proposal:
        for w in warns:
            print(f"  ! {w}")
        if args.llm_log:
            llm.dump_log(args.llm_log)
        return 1

    pm = proposal.get("part_marker") or {}
    print(f"스캔      p{proposal.get('scanned_pages')}")
    print(f"파트 마커  {pm.get('text', '—')}  (confidence {pm.get('confidence', 0)})")
    print(f"필드      {len(proposal.get('fields', []))}개 제안")
    for f in sorted(proposal.get("fields", []), key=lambda x: -x.get("confidence", 0)):
        art = f.get("article") or "—"
        print(f"    {f['confidence']:.2f} {f['name'][:18]:18s} {f['value_type']:11s} "
              f"{art:7s} {str(f.get('template',''))[:36]}")

    d = bootstrap.diff_against(proposal, onto)
    print(f"\n기존 온톨로지 대비")
    print(f"  새로 제안   {d['new_fields'] or '없음'}")
    print(f"  못 본 필드   {d['not_seen'] or '없음'}")
    print(f"  변경 제안   {d['changed'] or '없음'}")
    for n in proposal.get("notes") or []:
        print(f"  확인 필요   {n}")
    for w in warns:
        print(f"  ! {w}")

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(bootstrap.to_yaml(proposal, onto), encoding="utf-8")
        print(f"\n초안 저장  {p}  (검토 후 직접 반영하세요 — 자동 적용 안 함)")
    t = llm.totals()
    print(f"LLM 합계  호출 {t['calls']}  입력 {t['input_tokens']:,} 출력 {t['output_tokens']:,}")
    if args.llm_log:
        print(f"  기록     {llm.dump_log(args.llm_log)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trust-parser")
    ap.add_argument("--ontology", help="온톨로지 YAML 경로 (기본: ontology/trust_contract.ontology.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("parse", help="PDF → chunks.json (Part A)")
    p.add_argument("pdf")
    p.add_argument("-o", "--out")
    p.add_argument("--name", help="document 필드에 쓸 이름")
    p.add_argument("--llm-roles", action="store_true",
                   help="T6: LLM 세부 의미역 태깅 (기본 off)")
    p.add_argument("--llm-axioms", action="store_true",
                   help="T17: 본문에서 온톨로지 공리 후보 추출 (기본 off)")
    p.add_argument("--llm-limit", type=int, help="LLM 에 넘길 청크 수 상한 (비용 통제)")
    p.add_argument("--llm-log", help="요청·응답 원문을 남길 JSON 경로")
    p.set_defaults(fn=cmd_parse)

    r = sub.add_parser("reconcile", help="chunks.json + 요약서 → reconcile.json (Part B)")
    r.add_argument("contract", help="체결 계약서의 chunks.json")
    r.add_argument("summary", help="투자요약서 (pdf/md)")
    r.add_argument("-o", "--out")
    r.set_defaults(fn=cmd_reconcile)

    q = sub.add_parser("query", help="질의 → fact 조회 또는 청크 검색 (Part D)")
    q.add_argument("chunks", help="chunks.json")
    q.add_argument("question")
    q.add_argument("--top", type=int, default=5)
    q.add_argument("--llm", action="store_true",
                   help="규칙으로 분류가 안 될 때만 LLM 분류 사용 (기본 off)")
    q.set_defaults(fn=cmd_query)

    s = sub.add_parser("serve", help="뷰어 — 파싱·온톨로지·대사·질의를 브라우저에서 본다")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="0.0.0.0", help="기본 0.0.0.0 (WSL 밖에서 접속)")
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_serve)

    b = sub.add_parser("bootstrap", help="VLM 1차 스캔 → 온톨로지 초안 제안")
    b.add_argument("pdf")
    b.add_argument("-o", "--out", help="초안 YAML 경로")
    b.add_argument("--max-pages", type=int, default=3, help="스캔할 별지 페이지 수")
    b.add_argument("--llm-log", help="요청·응답 기록 경로")
    b.set_defaults(fn=cmd_bootstrap)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
