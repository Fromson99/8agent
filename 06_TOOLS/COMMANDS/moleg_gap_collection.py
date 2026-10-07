"""Collect the official MOLEG glossary gaps into a new, resumable snapshot.

Targets the whole frozen catalogue, not just the earlier corpus seeds:
- legal_term_detail for every 법제처 법령용어목록 ID (정의·영어·설명)
- legal_term_relations for every 법제처 지식용어목록 term (→ 일상용어 관계)

Completed responses from earlier snapshots are reused by request ID (same
endpoint + parameters digest), so nothing already fetched is fetched again.
Terms linked to the given navigation generation are collected first.
Earlier snapshots are read-only; the output folder is new and resumable.

usage: moleg_gap_collection.py --output DIR --generation GEN_DIR [--reuse DIR ...] [--workers 4]
"""
import argparse, collections, gzip, hashlib, json, logging, os, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.pipeline.glossary_enrichment import connect, requests_for, validate_response  # noqa: E402
from lawrag.pipeline.collect_moleg_knowledge import _digest  # noqa: E402
from lawrag.sources.common import HttpClient, make_session  # noqa: E402
from lawrag.sources.moleg_knowledge import MolegKnowledgeClient  # noqa: E402

ENDPOINTS = ('legal_term_detail', 'legal_term_relations')


def plan(db, catalogue_db, linked):
    db.execute('CREATE TABLE IF NOT EXISTS priority(request_id TEXT PRIMARY KEY,rank INTEGER NOT NULL)')
    if db.execute('SELECT count(*) FROM request').fetchone()[0]:
        return
    src = sqlite3.connect(catalogue_db)
    with db:
        for ident, payload in src.execute('SELECT id,payload FROM catalogue'):
            row = json.loads(payload)
            db.execute('INSERT OR IGNORE INTO catalogue VALUES (?,?)', (ident, payload))
            if row['entity_type'] == 'everyday_terms':
                continue
            for endpoint, parameters in requests_for(row):
                if endpoint not in ENDPOINTS:
                    continue
                rid = _digest([endpoint, parameters])
                db.execute('INSERT OR IGNORE INTO request(id,endpoint,parameters) VALUES (?,?,?)',
                           (rid, endpoint, json.dumps(parameters, sort_keys=True)))
                db.execute('INSERT OR IGNORE INTO request_term VALUES (?,?)', (rid, ident))
                rank = 0 if ident in linked else 1
                db.execute('INSERT INTO priority VALUES (?,?) ON CONFLICT(request_id) DO UPDATE SET rank=min(rank,excluded.rank)',
                           (rid, rank))


def reuse(db, folders):
    reused = 0
    for folder in folders:
        old = sqlite3.connect(Path(folder) / 'collection.sqlite')
        for row in old.execute("SELECT id,response,response_sha256,records FROM request WHERE status='complete'"):
            n = db.execute("UPDATE request SET status='complete',response=?,response_sha256=?,records=?,error=NULL "
                           "WHERE id=? AND status!='complete'", row[1:] + (row[0],)).rowcount
            reused += n
        db.commit()
    return reused


def linked_terms(generation):
    nav = sqlite3.connect(Path(generation) / 'navigation/navigation.sqlite')
    return {r[0] for r in nav.execute("SELECT DISTINCT term_id FROM occurrence WHERE term_id LIKE 'moleg:%'")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--catalogue', type=Path,
                    default=ROOT / '01_DATA/LEXICON/moleg-alignment/completion/complete-20260911/collection.sqlite')
    ap.add_argument('--generation', type=Path, required=True)
    ap.add_argument('--reuse', type=Path, nargs='*', default=[])
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    db = connect(a.output / 'collection.sqlite')
    db.execute('PRAGMA journal_mode=WAL')
    if not db.execute('SELECT count(*) FROM request').fetchone()[0]:
        plan(db, a.catalogue, linked_terms(a.generation))
        print('reused', reuse(db, a.reuse), flush=True)
        db.execute("INSERT OR REPLACE INTO meta VALUES ('identity',?)", (json.dumps({
            'profile': 'moleg-gap-collection-v1', 'catalogue': str(a.catalogue),
            'generation': str(a.generation), 'reuse': [str(r) for r in a.reuse],
            'endpoints': ENDPOINTS}, ensure_ascii=False),))
        db.commit()
    from dotenv import dotenv_values
    oc = os.environ.get('LAW_OC') or dotenv_values(ROOT / '.env').get('LAW_OC')
    local = threading.local()

    def client():
        if not hasattr(local, 'c'):
            local.c = MolegKnowledgeClient(HttpClient(make_session(), logging.getLogger('gap')), oc)
        return local.c

    def fetch(job):
        rid, endpoint, raw_params = job
        parameters = json.loads(raw_params)
        for attempt in range(5):
            try:
                xml, parsed = client().fetch(endpoint, parameters)
                validate_response(endpoint, parameters, xml, parsed.records)
                records = [dict(r, _request=parameters, _request_id=rid) for r in parsed.records]
                return rid, xml.encode('utf-8'), records, None
            except Exception as exc:  # credentials never logged; only the type
                err = type(exc).__name__
                time.sleep(2 ** attempt)
        return rid, None, None, err

    started, done, failed = time.time(), 0, 0
    with ThreadPoolExecutor(a.workers) as pool:
        while True:
            jobs = db.execute("SELECT r.id,r.endpoint,r.parameters FROM request r JOIN priority p ON p.request_id=r.id "
                              "WHERE r.status!='complete' AND r.attempts<3 ORDER BY p.rank,r.endpoint,r.id LIMIT 400").fetchall()
            if not jobs:
                break
            for rid, raw, records, err in pool.map(fetch, [tuple(j) for j in jobs]):
                if raw is None:
                    failed += 1
                    db.execute("UPDATE request SET status='failed',attempts=attempts+1,error=? WHERE id=?", (err, rid))
                else:
                    done += 1
                    db.execute("UPDATE request SET status='complete',attempts=attempts+1,response=?,response_sha256=?,records=?,error=NULL WHERE id=?",
                               (gzip.compress(raw, mtime=0), hashlib.sha256(raw).hexdigest(),
                                json.dumps(records, ensure_ascii=False), rid))
            db.commit()
            left = db.execute("SELECT p.rank,count(*) FROM request r JOIN priority p ON p.request_id=r.id "
                              "WHERE r.status!='complete' GROUP BY 1").fetchall()
            print(f'{time.strftime("%H:%M:%S")} fetched {done} failed {failed} remaining {dict(left)} '
                  f'{done / max(1, time.time() - started):.1f}/s', flush=True)
            if failed > 200 and done < failed:
                raise SystemExit('too many failures; resumable')
    summary = {e: dict(db.execute('SELECT status,count(*) FROM request WHERE endpoint=? GROUP BY 1', (e,)).fetchall())
               for e in ENDPOINTS}
    (a.output / 'status.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print('DONE', summary, flush=True)


if __name__ == '__main__':
    main()
