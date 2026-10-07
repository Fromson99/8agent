"""Dictionary-first authoring: package import, incremental grounding, lexical promotion.

The state directory owns one complete document snapshot. Absence means removal.
No LLM calls; no canonical Concept approval or mutation of the legacy glossary.
"""
from __future__ import annotations

import argparse
import fcntl
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid
import xml.etree.ElementTree as ET

from lawrag.datasets.catalog import load_package
from lawrag.platform.paths import data_path
from lawrag.pipeline.collect_moleg_knowledge import _atomic_json
from lawrag.sources.moleg_knowledge import catalog_identity

MATCHER = "literal-boundary-josa-v2"
PARSER = "body-fields-v1"
JOSA = frozenset("로부터 로부터는 로부터도 으로부터 으로부터는 으로부터도 은 는 이 가 을 를 의 에 에서 에게 에게서 께 께서 와 과 로 으로 도 만 부터 까지 보다 처럼 란 이란 이라 라 이라는 라는 에는 에서는 에도 에서도 으로는 로는 과는 와는 과도 와도 으로서 로서 으로써 로써 이다 입니다 이며 이고 이나 나 이든 든 이라면 라면 이라고 라고 이라고는 라고는".split())
CATALOGS = {"legal_terms", "knowledge_terms", "everyday_terms"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def compact(text):
    return re.sub(r"\s+", "", text)


def connect(state: Path):
    state.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(state / "alignment.sqlite", timeout=1)
    db.row_factory = sqlite3.Row
    db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS terms (
          id TEXT PRIMARY KEY, dataset TEXT NOT NULL, key TEXT NOT NULL,
          revision INTEGER NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, checked_revision INTEGER NOT NULL,
          rules TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence (
          term_id TEXT NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
          doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          block TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
          surface TEXT NOT NULL, definition_hint INTEGER NOT NULL,
          PRIMARY KEY(term_id,doc_id,block,start,end));
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value INTEGER NOT NULL);
        INSERT OR IGNORE INTO meta VALUES ('revision',0);
        CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, receipt TEXT NOT NULL);
    """)
    return db


def import_package(db, manifest: Path):
    package = load_package(manifest, verify_files=True)
    if not package.dataset_id.startswith("moleg-knowledge-"):
        raise ValueError("법제처 용어 DatasetPackage가 필요합니다")
    artifacts = [a for a in package.artifacts if a.path.endswith("/records.jsonl")]
    if len(artifacts) != 1:
        raise ValueError("패키지에 records.jsonl이 정확히 하나 있어야 합니다")
    plans = [a for a in package.artifacts if a.path.endswith('/request-plan.json')]
    if len(plans) != 1:
        raise ValueError('전체 수집 영수증이 필요합니다')
    plan = json.loads(plans[0].resolved_path().read_text('utf-8'))
    checkpoint = plan.get('checkpoint', {})
    if not checkpoint.get('completed') or plan.get('parameters'):
        raise ValueError('필터 없는 전체 목록의 완료 패키지만 적재할 수 있습니다')
    seen, changed = set(), 0
    revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0] + 1
    for line in artifacts[0].resolved_path().read_text("utf-8").splitlines():
        row = json.loads(line)
        kind, source_id = row.get("entity_type"), row.get("source_id")
        if kind not in CATALOGS or not source_id or not row.get("label", "").strip():
            raise ValueError("목록형 API의 식별자와 표제어가 있는 행만 적재할 수 있습니다")
        identity = catalog_identity(row)
        if identity in seen:
            raise ValueError("중복 원천 ID: " + identity)
        seen.add(identity)
        fingerprint = digest(row)
        old = db.execute("SELECT fingerprint FROM terms WHERE id=?", (identity,)).fetchone()
        if old and old[0] == fingerprint:
            continue
        if old:
            db.execute("DELETE FROM evidence WHERE term_id=?", (identity,))
        # Source content identity drives delta; package identity remains in provenance.
        payload = dict(row, package_id=package.package_id,
                       package_manifest=str(manifest.resolve()), artifact_sha256=artifacts[0].sha256)
        db.execute("""INSERT INTO terms VALUES (?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET dataset=excluded.dataset,key=excluded.key,
          revision=excluded.revision,fingerprint=excluded.fingerprint,payload=excluded.payload""",
                   (identity, package.dataset_id, compact(row["label"]), revision,
                    fingerprint, json.dumps(payload, ensure_ascii=False)))
        changed += 1
    normalization = plan.get('normalization', {})
    expected = normalization.get('normalized_record_count', checkpoint.get('record_count'))
    duplicates = normalization.get('exact_same_page_duplicates', [])
    if (len(seen) != expected or expected + len(duplicates) != checkpoint.get('record_count')
            or checkpoint.get('record_count') != checkpoint.get('total_count')):
        raise ValueError('완료 영수증과 실제 용어 수가 다릅니다')
    # Each package replaces only its own source catalog; other catalogs survive.
    deleted = 0
    for old in db.execute("SELECT id FROM terms WHERE dataset=?", (package.dataset_id,)).fetchall():
        if old[0] not in seen:
            db.execute("DELETE FROM terms WHERE id=?", (old[0],))
            deleted += 1
    if changed or deleted:
        db.execute("UPDATE meta SET value=? WHERE key='revision'", (revision,))
    return {"dataset": package.dataset_id, "received": len(seen), "changed": changed,
            "removed": deleted, "package_id": package.package_id}


def documents(root: Path):
    """Hash exact files, extract only body fields, retain per-field offsets."""
    if not root.is_dir():
        raise ValueError("문서 snapshot 디렉터리가 없습니다")
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("문서 snapshot에 symlink가 있습니다: " + str(path))
        if not path.is_file() or not (path.suffix.lower() in {".xml", ".txt", ".md"}
                                     or path.name == "result.json"):
            continue
        raw = path.read_bytes()
        blocks = []
        if path.suffix.lower() == ".xml":
            tree = ET.fromstring(raw)
            if tree.tag not in {"법령", "행정규칙", "AdmRulService"}:
                raise ValueError("지원되지 않는 XML 문서: " + str(path))
            # Leaf text avoids double counting parent article + child paragraphs.
            for i, node in enumerate(tree.iter()):
                if not list(node) and node.tag in {
                    "조문내용", "항내용", "호내용", "목내용", "전문", "부칙내용", "별표내용"
                } and node.text:
                    blocks.append((f"xml:{node.tag}:{i}", node.text))
        elif path.name == "result.json":
            blob = json.loads(raw)
            if not isinstance(blob.get("blocks"), list):
                raise ValueError("result.json에 blocks가 없습니다: " + str(path))
            for i, block in enumerate(blob["blocks"]):
                if isinstance(block.get("text"), str):
                    blocks.append((f"block:{i}", block["text"]))
        else:
            blocks = [("text", raw.decode("utf-8"))]
        if not blocks:
            raise ValueError("본문 추출 결과가 비어 있습니다: " + str(path))
        identity = str(root.resolve()) + "/" + path.relative_to(root).as_posix()
        out[identity] = (hashlib.sha256(raw).hexdigest(), blocks)
    return out


class Matcher:
    """Whitespace-tolerant literal trie with original offsets and lexical boundaries."""
    def __init__(self, terms):
        self.trie = {}
        for identity, key in terms:
            node = self.trie
            for char in key:
                node = node.setdefault(char, {})
            node.setdefault(None, []).append(identity)

    _suffix = re.compile(r"[^\Wㆍ·]+")
    _definition = re.compile(r'[\"”」]\s*(?:이란|란|이라 함은|라 함은)')

    def find(self, text):
        positions = [i for i, c in enumerate(text) if not c.isspace()]
        value = "".join(text[i] for i in positions)
        for start, original in enumerate(positions):
            if original and (text[original - 1].isalnum() or text[original - 1] == "_") and text[original - 1] not in "ㆍ·":
                continue
            node, stop = self.trie, start
            while stop < len(value) and value[stop] in node:
                node = node[value[stop]]
                stop += 1
                if None not in node:
                    continue
                end = positions[stop - 1] + 1
                suffix = self._suffix.match(text, end)
                if suffix and suffix.group() not in JOSA:
                    continue
                # Exact quoted target followed by a definition marker, not merely
                # another word appearing inside an article entitled '정의'.
                is_definition = bool(
                    original and text[original - 1] in '\"“「'
                    and self._definition.match(text, end)
                )
                for identity in node[None]:
                    yield identity, original, end, is_definition


def align(db, inventory):
    revision = db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
    rules = digest({"matcher": MATCHER, "parser": PARSER, "josa": sorted(JOSA),
                    "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    previous = {r["id"]: dict(r) for r in db.execute("SELECT * FROM documents")}
    removed = set(previous) - set(inventory)
    for identity in removed:
        db.execute("DELETE FROM documents WHERE id=?", (identity,))
    terms = db.execute("SELECT id,key,revision FROM terms ORDER BY id").fetchall()
    groups = defaultdict(list)
    skipped = checks = hits = 0
    for identity, (fingerprint, blocks) in inventory.items():
        old = previous.get(identity)
        if old and old["fingerprint"] == fingerprint and old["rules"] == rules:
            watermark = old["checked_revision"]
        else:
            watermark = -1
            db.execute("DELETE FROM evidence WHERE doc_id=?", (identity,))
        pending = sum(r["revision"] > watermark for r in terms)
        skipped += len(terms) - pending
        if pending:
            groups[watermark].append((identity, fingerprint, blocks))
        else:
            db.execute("""INSERT INTO documents VALUES (?,?,?,?) ON CONFLICT(id)
              DO UPDATE SET fingerprint=excluded.fingerprint,
              checked_revision=excluded.checked_revision,rules=excluded.rules""",
                       (identity, fingerprint, revision, rules))
    for watermark, docs in groups.items():
        subset = [(r["id"], r["key"]) for r in terms if r["revision"] > watermark]
        matcher = Matcher(subset)
        for identity, fingerprint, blocks in docs:
            # UPSERT avoids REPLACE's cascading deletion of prior positive matches.
            db.execute("""INSERT INTO documents VALUES (?,?,?,?) ON CONFLICT(id)
              DO UPDATE SET fingerprint=excluded.fingerprint,
              checked_revision=excluded.checked_revision,rules=excluded.rules""",
                       (identity, fingerprint, revision, rules))
            for block_id, text in blocks:
                for term_id, start, end, definition in matcher.find(text):
                    db.execute("INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?)",
                               (term_id, identity, block_id, start, end, text[start:end], int(definition)))
                    hits += 1
            checks += len(subset)
    return {"terms": len(terms), "documents": len(inventory), "checked_pairs": checks,
            "skipped_pairs": skipped, "new_occurrences": hits, "removed_documents": len(removed),
            "promoted_terms": db.execute("SELECT COUNT(DISTINCT term_id) FROM evidence").fetchone()[0],
            "revision": revision, "matcher": MATCHER}


def export(db, state):
    terms = []
    evidence = defaultdict(list)
    for row in db.execute("SELECT * FROM evidence ORDER BY term_id,doc_id,block,start"):
        evidence[row["term_id"]].append({k: row[k] for k in row.keys() if k != "term_id"})
    for row in db.execute("SELECT * FROM terms ORDER BY id"):
        source = json.loads(row["payload"])
        occurrences = evidence[row["id"]]
        definition = any(x["definition_hint"] for x in occurrences)
        terms.append({"id": row["id"], "term": source["label"], "key": row["key"],
                      "surfaces": [source["label"]], "status": "활성" if occurrences else "잠정",
                      # 본문용어/참고용어는 본문 출현 기준이다. 법제처 목록 구분은 source.entity_type에 남는다.
                      "classification": "정의" if definition else ("본문용어" if occurrences else "참고용어"),
                      "source_definition": source.get("fields", {}).get("사전구분코드") == "011402",
                      "definition_hint": definition,
                      "occurrences": occurrences, "source": source})
    projection = {"schema_version": "glossary-alignment-projection-v1", "terms": terms,
                  "promotion_scope": "document-grounded-lexical-surface", "canonical_approval": False}
    generation = digest(projection)
    target = state / "generations" / generation / "glossary.json"
    if target.exists():
        if json.loads(target.read_text()) != projection:
            raise ValueError("용어집 세대 내용 불일치")
    else:
        _atomic_json(target, projection)
    return target


def _start(state: Path, packages: list[Path], document_root: Path):
    inventory = documents(document_root)
    db = connect(state)
    try:
        db.execute("BEGIN IMMEDIATE")
        imported = [import_package(db, p) for p in packages]
        if not db.execute("SELECT 1 FROM terms LIMIT 1").fetchone():
            raise ValueError("먼저 완성된 법제처 용어 패키지를 적재해야 합니다")
        receipt = {"run_id": uuid.uuid4().hex, "imports": imported, **align(db, inventory), "llm_calls": 0}
        db.execute("INSERT INTO runs VALUES (?,?)", (receipt["run_id"], json.dumps(receipt, ensure_ascii=False)))
        target = export(db, state)
        db.commit()
        _atomic_json(state / "CURRENT.json", {"generation": target.parent.name,
                     "path": str(target.resolve()), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        _atomic_json(state / "runs" / (receipt["run_id"] + ".json"), receipt)
        return dict(receipt, glossary=str(target))
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def start(state: Path, packages: list[Path], document_root: Path):
    state.mkdir(parents=True, exist_ok=True)
    with (state / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _start(state, packages, document_root)


def import_catalog(state, packages):
    state.mkdir(parents=True, exist_ok=True)
    with (state / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = connect(state)
        try:
            db.execute('BEGIN IMMEDIATE')
            imported = [import_package(db, p) for p in packages]
            target = export(db, state)
            db.commit()
            _atomic_json(state / 'CURRENT.json', {'generation': target.parent.name,
                         'path': str(target.resolve()), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
            return {'imports': imported, 'glossary': str(target)}
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="용어집 수집 → 문서 증분 정합성 → 용어집 확장")
    parser.add_argument("action", choices=["collect", "import", "start", "status", "complete", "collect-external", "v1-build", "v1-match", "v1-status"])
    parser.add_argument("--state-dir", type=Path, default=data_path("LEXICON", "moleg-alignment"))
    parser.add_argument("--package", action="append", type=Path, default=[])
    parser.add_argument("--documents", type=Path)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument('--snapshot', default='initial')
    parser.add_argument("--include-everyday", action="store_true")
    parser.add_argument('--plan-only', action='store_true', help='완성 수집의 전체 요청 계획만 준비')
    parser.add_argument('--max-requests', type=int, default=0, help='완성 수집 호출 한도(0=전체); 같은 snapshot으로 재개')
    parser.add_argument('--corpus-generation', type=Path, help='이 문서 세대에 출현하는 법령용어만 수집하고 연결 조문도 해당 세대로 제한')
    parser.add_argument('--completion-endpoint', action='append',
                        choices=['legal_term_detail', 'legal_term_relations', 'everyday_term_relations', 'term_articles'],
                        help='complete 전용: 문서 범위에서 지정 API만 수집; 완성 사전으로 자동 발행하지 않음')
    parser.add_argument('--reuse-snapshot', type=Path, help='중지된 기존 수집의 collection.sqlite에서 완료 응답 재사용')
    parser.add_argument("--source", action="append", choices=["bok", "econedu", "kofia", "nts", "krx"], help="외부 공개 용어집 원천; collect-external 전용")
    parser.add_argument("--external", action="store_true", help="status에서 외부 사전 수집 기록 조회")
    parser.add_argument('--v1-dir', type=Path, help='용어집 v1 출력/조회 디렉터리; 활성 RAG와 별도')
    parser.add_argument('--external-dir', type=Path, help='econedu/nts entries.jsonl을 포함한 수집 snapshot')
    parser.add_argument('--definitions-db', type=Path, help='완료 응답만 읽을 기존 collection.sqlite')
    parser.add_argument('--review-file', type=Path, help='명시적으로 검토한 의미 묶음·별칭 JSON')
    parser.add_argument('--question', help='v1-match에서 처리할 원문 질문')
    parser.add_argument('--selections', type=Path, help='query_id에 결속된 의미/원천 후보 선택 JSON')
    parser.add_argument('--choice-limit', type=int, default=20)
    parser.add_argument('--hit-limit', type=int, default=20)
    parser.add_argument('--document', action='append', help='v1-match의 문서 ID 필터')
    args = parser.parse_args(argv)
    if args.completion_endpoint and (args.action != 'complete' or args.corpus_generation is None):
        parser.error('--completion-endpoint는 complete와 --corpus-generation이 필요합니다')
    if args.action.startswith('v1-'):
        from .glossary_v1 import build, Glossary
        if args.v1_dir is None:
            parser.error('--v1-dir에 버전 디렉터리를 명시하십시오')
        if args.action == 'v1-build':
            if args.corpus_generation is None or args.external_dir is None:
                parser.error('v1-build에는 --corpus-generation과 --external-dir가 필요합니다')
            import sys
            result = build(args.state_dir/'alignment.sqlite', args.external_dir, args.corpus_generation,
                           args.v1_dir, completion=args.definitions_db, review=args.review_file,
                           emit=lambda *a, **kw: print(*a, file=sys.stderr, **kw))
        elif args.action == 'v1-status':
            from .glossary_v1 import sha, VERSION
            result = json.loads((args.v1_dir/'report.json').read_text())
            if result.get('schema_version') != VERSION or sha(args.v1_dir/'dictionary.sqlite') != result['dictionary_sha256']:
                raise ValueError('Glossary version/hash mismatch')
        else:
            if not args.question:
                parser.error('v1-match에는 --question이 필요합니다')
            glossary = Glossary(args.v1_dir)
            try:
                choices = json.loads(args.selections.read_text()) if args.selections else None
                result = glossary.query(args.question, selections=choices, choice_limit=args.choice_limit)
                result = glossary.articles(result, documents=args.document, limit=args.hit_limit)
            finally:
                glossary.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.external and args.action != "status":
        parser.error("--external은 status에서 사용합니다")
    if args.source and args.action != "collect-external":
        parser.error("--source는 collect-external에서 사용합니다")
    if args.action == "status" and args.external:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", args.snapshot):
            parser.error("invalid snapshot")
        receipt = data_path("LOGS", "glossaries", args.snapshot, "collection.json")
        result = json.loads(receipt.read_text()) if receipt.is_file() else {"status": "not_collected", "snapshot": args.snapshot}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.action == "collect-external":
        from .collect_public_glossaries import run
        result = run(args.snapshot, args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["collection_complete"] else 2
    if args.max_requests < 0:
        parser.error('--max-requests must be nonnegative')
    if args.action == 'complete':
        from .glossary_enrichment import run
        result = run(args.state_dir, args.snapshot, plan_only=args.plan_only, max_requests=args.max_requests,
                     corpus_generation=args.corpus_generation, reuse_snapshot=args.reuse_snapshot,
                     endpoints=args.completion_endpoint)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.plan_only or result['collection_complete'] else 2
    if args.action == "collect":
        from lawrag.pipeline.collect_moleg_knowledge import main as collect
        options = ["--endpoint", "legal_terms", "--endpoint", "knowledge_terms",
                   "--max-pages", str(args.max_pages), '--snapshot', args.snapshot,
                   '--receipt-output', str(args.state_dir / 'collection.json')]
        if args.include_everyday:
            options += ["--endpoint", "everyday_terms"]
        code = collect(options)
        if code == 0:
            receipt = json.loads((args.state_dir / 'collection.json').read_text())
            print(json.dumps(import_catalog(args.state_dir, [Path(p) for p in receipt['packages']]),
                             ensure_ascii=False, indent=2))
        return code
    if args.action == 'import':
        if not args.package:
            parser.error('--package가 필요합니다')
        print(json.dumps(import_catalog(args.state_dir, args.package), ensure_ascii=False, indent=2))
        return 0
    if args.action == "start":
        if not args.documents:
            parser.error("--documents에 전체 문서 snapshot 디렉터리를 지정하십시오")
        print(json.dumps(start(args.state_dir, args.package, args.documents), ensure_ascii=False, indent=2))
    else:
        current = args.state_dir / "CURRENT.json"
        result = {'alignment': json.loads(current.read_text()) if current.exists() else None}
        if not re.fullmatch(r'[A-Za-z0-9_-]+', args.snapshot):
            parser.error('invalid snapshot')
        completion_db = args.state_dir / 'completion' / args.snapshot / 'collection.sqlite'
        if completion_db.is_file():
            from .glossary_enrichment import status
            db = sqlite3.connect(completion_db.resolve().as_uri() + '?mode=ro', uri=True)
            db.row_factory = sqlite3.Row
            try:
                db.execute('BEGIN')  # All progress counters describe one read snapshot.
                result['completion'] = status(db)
            finally:
                db.close()
        completed = args.state_dir / 'COMPLETED.json'
        result['completed_glossary'] = json.loads(completed.read_text()) if completed.exists() else None
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
