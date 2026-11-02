"""Dataiku 새 Python notebook: 전체를 한 셀에 붙여 실행. ADR1236/run-001.
원문3건 -> KURE -> 실제 Oracle INSERT/조회/거리 검사 -> 항상 ROLLBACK.
전체 적재 notebook은 중단하지 않는다. 이 셀은 운영 게시·활성화를 하지 않는다.
"""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import time
import uuid

MODEL_ID = "openai:genos-embedding:embedding-kure-v1"
OWNER = "SIDDS"
DIMENSIONS = 1024
CODE_VERSION = "ADR1236-dataiku-kure-smoke-r2"
RUN_ID = "run-001"


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def literal(value):
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("INVALID_SQL_STRING")
    if len(value.encode("utf-8")) > 3600:
        raise ValueError("SQL_STRING_TOO_LONG")
    return "'" + value.replace("'", "''") + "'"


def clob(value):
    return " || ".join("TO_CLOB(" + literal(value[i:i+800]) + ")"
                       for i in range(0, len(value), 800)) or "TO_CLOB('{}')"


def checked_vectors(raw):
    if len(raw) != 3:
        raise ValueError("EMBEDDING_COUNT_EXPECTED_3")
    result = []
    for values in raw:
        if len(values) != DIMENSIONS:
            raise ValueError("EMBEDDING_DIMENSIONS_EXPECTED_1024")
        if any(isinstance(v, (bool, str)) for v in values):
            raise ValueError("EMBEDDING_NOT_NUMERIC")
        values = [float(v) for v in values]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("EMBEDDING_NONFINITE")
        norm = math.hypot(*values)
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError("EMBEDDING_ZERO_OR_INVALID_NORM")
        result.append([struct.unpack("<f", struct.pack("<f", v/norm))[0]
                       for v in values])
    return result


def cosine(a, b):
    return 1 - math.fsum(x*y for x, y in zip(a, b)) / (math.hypot(*a)*math.hypot(*b))


def roundtrip_sql(owner, pub, samples, vectors):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", owner):
        raise ValueError("INVALID_OWNER")
    if not re.fullmatch(r"[0-9a-f]{64}", pub):
        raise ValueError("INVALID_TEST_ID")
    if len(samples) != 3 or len(vectors) != 3:
        raise ValueError("EXPECTED_3_ROWS")
    parent, child = owner + ".LGL_VCTR_SET_S", owner + ".LGL_VCTR_ITEM_S"
    payload = packed({"schema_version": "legal-embedding-smoke-v1",
                      "manifest": {"test_only": True, "model_id": MODEL_ID},
                      "status": "TEST_ONLY", "active_revision": None})
    # Deliberately NOT a valid/READY RAG publication. Invisible outside this
    # autonomous transaction and rolled back before JDBC returns, even on error.
    body = [f"INSERT INTO {parent}(PUB_ID,PAYLOAD_JSON) VALUES({literal(pub)},{clob(payload)});"]
    for i, (row, vector) in enumerate(zip(samples, vectors)):
        meta = dict(row)
        meta.pop("SAMPLE_TEXT")
        meta.update(test_only=True, document_id=row["DOC_ID"],
                    source_id="smoke-only-" + str(i), model_id=MODEL_ID)
        meta_text = packed(meta)
        vector_text = "[" + ",".join(format(v, ".9g") for v in vector) + "]"
        if not all(math.isfinite(v) for v in vector) or len(vector) != DIMENSIONS:
            raise ValueError("INVALID_VECTOR_SQL_INPUT")
        vector_expr = f"TO_VECTOR({clob(vector_text)},{DIMENSIONS},FLOAT32)"
        body += [
            f"INSERT INTO {child}(PUB_ID,SEG_ID,META_JSON,EMBEDDING) VALUES"
            f"({literal(pub)},{literal(str(i))},{clob(meta_text)},{vector_expr});",
            f"SELECT VECTOR_DIMENSION_COUNT(EMBEDDING),"
            f"VECTOR_DISTANCE(EMBEDDING,{vector_expr},EUCLIDEAN),"
            f"DBMS_LOB.COMPARE(META_JSON,{clob(meta_text)}) INTO n,d,m FROM {child} "
            f"WHERE PUB_ID={literal(pub)} AND SEG_ID={literal(str(i))};",
            "IF n IS NULL OR n<>1024 OR d IS NULL OR ABS(d)>0.000001 OR m IS NULL OR m<>0 "
            "THEN RAISE_APPLICATION_ERROR(-20031,'SMOKE_ROUNDTRIP_FAILED'); END IF;",
        ]
    for i in range(3):
        for j in range(3):
            expected = format(cosine(vectors[i], vectors[j]), ".17g")
            body += [
                f"SELECT VECTOR_DISTANCE(a.EMBEDDING,b.EMBEDDING,COSINE) INTO d "
                f"FROM {child} a JOIN {child} b ON a.PUB_ID=b.PUB_ID "
                f"WHERE a.PUB_ID={literal(pub)} AND a.SEG_ID={literal(str(i))} "
                f"AND b.SEG_ID={literal(str(j))};",
                f"IF d IS NULL OR ABS(d-({expected}))>0.00001 THEN "
                "RAISE_APPLICATION_ERROR(-20032,'SMOKE_COSINE_FAILED'); END IF;",
            ]
    body += [
        f"SELECT COUNT(*) INTO n FROM {child} WHERE PUB_ID={literal(pub)};",
        "IF n<>3 THEN RAISE_APPLICATION_ERROR(-20033,'SMOKE_ROW_COUNT'); END IF;",
        f"SELECT DBMS_LOB.COMPARE(PAYLOAD_JSON,{clob(payload)}) INTO m "
        f"FROM {parent} WHERE PUB_ID={literal(pub)};",
        "IF m IS NULL OR m<>0 THEN RAISE_APPLICATION_ERROR(-20034,'SMOKE_PARENT'); END IF;",
        "ROLLBACK;",
    ]
    return ("DECLARE PRAGMA AUTONOMOUS_TRANSACTION; n PLS_INTEGER; m PLS_INTEGER; "
            "d BINARY_DOUBLE; BEGIN\n" + "\n".join(body) +
            "\nEXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;")


def run():
    import dataiku
    root = Path.cwd() / "legal_embedding_smoke_ADR1236" / RUN_ID
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    lock = root / "STARTED.json"
    # Persistent single-run guard: rerunning this cell never sends a second batch.
    try:
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print("ALREADY_STARTED: 같은 시험을 다시 호출하지 않았습니다.", str(root))
        summary = root / "summary.json"
        if summary.exists():
            print(summary.read_text(encoding="utf-8"))
        return
    pub = sha(CODE_VERSION + ":" + str(uuid.uuid4()))
    report = {"code_version": CODE_VERSION, "run_id": RUN_ID, "test_pub_id": pub,
              "status": "STARTED", "sdk_embedding_attempts": 0,
              "provider_physical_calls": None, "model_id": MODEL_ID,
              "model_weight_revision": "UNVERIFIED", "persistent_publication": False,
              "full_rag_e2e": "NOT_TESTED", "artifacts": {}}
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(packed(report))

    def save():
        tmp = root / "summary.tmp"
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(str(tmp), str(root / "summary.json"))

    def artifact(name, value):
        content = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        path = root / name
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as archive:
                archive.write(content)
        report["artifacts"][name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "content_sha256": hashlib.sha256(content).hexdigest()}

    started = time.monotonic()
    stage = "PREFLIGHT"
    try:
        connection = str(dataiku.get_custom_variables().get("LEGAL_ORACLE_CONNECTION", "AIDP"))
        executor = dataiku.SQLExecutor2(connection=connection)
        report["connection"] = connection

        def query(sql, **kwargs):
            frame = executor.query_to_df(sql, infer_from_schema=True, parse_dates=False, **kwargs)
            frame.columns = [str(c).upper() for c in frame.columns]
            return frame

        cols = query(f"SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM ALL_TAB_COLUMNS "
                     f"WHERE OWNER='{OWNER}' AND TABLE_NAME IN ('LGL_VCTR_SET_S','LGL_VCTR_ITEM_S')")
        actual = {(str(r.TABLE_NAME), str(r.COLUMN_NAME)): str(r.DATA_TYPE) for r in cols.itertuples()}
        expected = {(t, c): d for t, columns in {
            "LGL_VCTR_SET_S": {"PUB_ID": "VARCHAR2", "PAYLOAD_JSON": "CLOB"},
            "LGL_VCTR_ITEM_S": {"PUB_ID": "VARCHAR2", "SEG_ID": "VARCHAR2", "META_JSON": "CLOB", "EMBEDDING": "VECTOR"},
        }.items() for c, d in columns.items()}
        if actual != expected:
            raise ValueError("VECTOR_2_TABLE_6_COLUMN_MISMATCH")
        project = dataiku.api_client().get_default_project()
        if MODEL_ID not in [m.id for m in project.list_llms(purpose="TEXT_EMBEDDING_EXTRACTION")]:
            raise ValueError("KURE_MODEL_NOT_VISIBLE")
        rows = query(f"SELECT DATA_VER_ID,DOC_ID,UNIT_ID,BLK_ID,SRC_DATA_HASH_VAL,"
                     f"DBMS_LOB.SUBSTR(BLK_TXT_CN,800,1) AS SAMPLE_TEXT FROM {OWNER}.LGL_DOC_BLK_S "
                     "WHERE BLK_TXT_CN IS NOT NULL AND DBMS_LOB.GETLENGTH(BLK_TXT_CN)>0 AND ROWNUM<=3")
        samples = []
        for row in rows.to_dict(orient="records"):
            text = row["SAMPLE_TEXT"]
            if not isinstance(text, str) or not text.strip() or len(text) > 800:
                raise ValueError("INVALID_SOURCE_TEXT")
            if any(not isinstance(row[k], str) or not row[k] for k in row if k != "SAMPLE_TEXT"):
                raise ValueError("SOURCE_COORDINATE_NOT_STRING_OR_MISSING")
            row["INPUT_SHA256"] = sha(text)
            samples.append(row)
        coords = {(r['DATA_VER_ID'], r['DOC_ID'], r['BLK_ID']) for r in samples}
        if len(samples) != 3 or len(coords) != 3:
            raise ValueError("EXPECTED_3_DISTINCT_SOURCE_ROWS")
        artifact("source_samples.json.gz", samples)
        report["source_summary"] = [{**{k: v for k, v in r.items() if k != "SAMPLE_TEXT"},
                                      "input_chars": len(r["SAMPLE_TEXT"])} for r in samples]
        report["status"] = "INPUT_FROZEN"
        save()
        print("SOURCE_SAMPLES_OK 3; MODEL", MODEL_ID, flush=True)
        batch = project.get_llm(MODEL_ID).new_embeddings()
        for row in samples:
            batch.add_text(row["SAMPLE_TEXT"])
        stage = "EMBEDDING_EXECUTE"
        report.update(status="EMBEDDING_IN_FLIGHT", sdk_embedding_attempts=1)
        save()
        t = time.monotonic()
        response = batch.execute()  # exactly one SDK attempt; no retry/fallback
        stage = "EMBEDDING_RESPONSE"
        raw = [list(values) for values in response.get_embeddings()]
        if any(isinstance(v, (bool, str)) for values in raw for v in values):
            raise ValueError("EMBEDDING_NOT_NUMERIC")
        raw = [[float(v) for v in values] for values in raw]
        report["embedding_seconds"] = time.monotonic() - t
        artifact("embedding_values.json.gz", raw)  # SDK-visible output, not hidden provider wire
        vectors = checked_vectors(raw)
        report.update(status="EMBEDDING_OK", vectors=3, dimensions=DIMENSIONS)
        save()
        print("EMBEDDING_OK 3 x 1024", flush=True)
        stage = "ORACLE_ROUNDTRIP"
        sql = roundtrip_sql(OWNER, pub, samples, vectors)
        report["oracle_block_sha256"] = sha(sql)
        t = time.monotonic()
        result = query("SELECT 1 AS OK FROM DUAL", pre_queries=[sql])
        if len(result) != 1 or int(result.iloc[0]["OK"]) != 1:
            raise ValueError("ORACLE_RESULT_NOT_CONFIRMED")
        report["oracle_roundtrip_seconds"] = time.monotonic() - t
        report.update(oracle_inserted_and_rechecked=3, oracle_cosine_pairs_checked=9)
        stage = "ROLLBACK_VERIFY"
        counts = query(f"SELECT (SELECT COUNT(*) FROM {OWNER}.LGL_VCTR_SET_S WHERE PUB_ID={literal(pub)}) AS SET_N,"
                       f"(SELECT COUNT(*) FROM {OWNER}.LGL_VCTR_ITEM_S WHERE PUB_ID={literal(pub)}) AS ITEM_N FROM DUAL")
        if len(counts) != 1 or int(counts.iloc[0]["SET_N"]) != 0 or int(counts.iloc[0]["ITEM_N"]) != 0:
            raise ValueError("ROLLBACK_NOT_CONFIRMED")
        report.update(status="PASS", remaining_test_rows=0)
        print("ORACLE_ROUNDTRIP_OK 3; COSINE_PAIRS_OK 9; ROLLBACK_OK remaining=0", flush=True)
    except BaseException as exc:
        report.update(status="UNKNOWN" if stage in ("EMBEDDING_EXECUTE", "ORACLE_ROUNDTRIP") else "FAILED",
                      failed_stage=stage, error_type=type(exc).__name__,
                      oracle_codes=sorted(set(re.findall(r"(?:ORA|PLS)-\d{5}", str(exc)))))
        if isinstance(exc, ValueError):
            report["check_error"] = str(exc)[:100]
        print("TEST_NOT_PASSED", report["status"], stage, report["error_type"], report["oracle_codes"], flush=True)
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        save()
        print("SUMMARY_FILE", str(root / "summary.json"), flush=True)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if report["status"] == "PASS":
        print("EMBEDDING_ORACLE_SMOKE_PASS — 임시 삽입·재조회 성공, 시험 행 롤백 완료. 전체 RAG 검증은 별도.")
    return report


if __name__ == "__main__":
    run()
