# Dataiku LEGAL_RAG Python 노트북의 새 셀에 전체 복사 후 실행하세요.
# 기존 적재가 끝나고 Idle일 때 실행. ZIP 업로드/설치 불필요.
CONNECTION = "AIDP"
EXPECTED_USER = "PIDD2APP"
PAIRS = 4
TOTAL_SECONDS = 120       # 다음 요청 시작 제한. 진행 중 요청의 강제 timeout은 아님.
STOP_AFTER_SLOW_SECONDS = 30

import gzip
import hashlib
import inspect
import json
from pathlib import Path
import re
import statistics
import time
import uuid


IDENTITY_SQL = """SELECT 1 AS OK,
 SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER,
 SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME,
 SYS_CONTEXT('USERENV','CON_NAME') AS CON_NAME,
 SYS_CONTEXT('USERENV','INSTANCE_NAME') AS INSTANCE_NAME,
 SYS_CONTEXT('USERENV','SID') AS SID FROM DUAL"""


def synthetic_payload(run_id):
    rows = [{"id": i, "value": hashlib.sha512((run_id + str(i)).encode()).hexdigest(),
             "text": "가정 데이터; 원문을 읽지 않습니다."} for i in range(2048)]
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def make_block(payload, run_id, variant):
    """R1의 gzip/HEX->BLOB->CLOB 경로. 두 조건은 주석 8자리만 다름."""
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or not 0 <= variant < 100000000:
        raise ValueError("INVALID_PROBE_ID")
    packed = gzip.compress(payload.encode("utf-8"), compresslevel=6, mtime=0)
    writes = []
    for offset in range(0, len(packed), 1800):
        piece = packed[offset:offset + 1800]
        writes.append("DBMS_LOB.WRITEAPPEND(z,%d,HEXTORAW('%s'));" %
                      (len(piece), piece.hex().upper()))
    return """/* G19_REUSE_CHECK_%s_%08d */
DECLARE
 z BLOB; r BLOB; c CLOB;
 d INTEGER := 1; s INTEGER := 1; ctx INTEGER := 0; w INTEGER;
 PROCEDURE cleanup IS
 BEGIN
  IF DBMS_LOB.ISTEMPORARY(z)=1 THEN DBMS_LOB.FREETEMPORARY(z); END IF;
  IF DBMS_LOB.ISTEMPORARY(r)=1 THEN DBMS_LOB.FREETEMPORARY(r); END IF;
  IF DBMS_LOB.ISTEMPORARY(c)=1 THEN DBMS_LOB.FREETEMPORARY(c); END IF;
 END;
BEGIN
 DBMS_LOB.CREATETEMPORARY(z,TRUE,DBMS_LOB.CALL);
 DBMS_LOB.CREATETEMPORARY(c,TRUE,DBMS_LOB.CALL);
 %s
 r := UTL_COMPRESS.LZ_UNCOMPRESS(z);
 DBMS_LOB.CONVERTTOCLOB(c,r,DBMS_LOB.LOBMAXSIZE,d,s,NLS_CHARSET_ID('AL32UTF8'),ctx,w);
 IF w<>0 OR DBMS_LOB.GETLENGTH(c)<>%d THEN
  RAISE_APPLICATION_ERROR(-20987,'G19_CLOB_CHECK_FAILED');
 END IF;
 cleanup;
EXCEPTION WHEN OTHERS THEN
 cleanup;
 RAISE;
END;""" % (run_id, variant, "\n ".join(writes), len(payload))


def summarize(samples, pairs):
    result = []
    for pair in range(1, pairs + 1):
        group = {x["label"]: x for x in samples
                 if x["pair"] == pair and x["status"] == "OK"}
        if not {"PING", "SAME", "NEW"} <= set(group):
            continue
        a, b = group["SAME"]["request_s"], group["NEW"]["request_s"]
        result.append({"pair": pair, "same_s": a, "new_s": b,
                       "difference_s": b - a, "ping_s": group["PING"]["request_s"]})
    output = {"complete_pairs": len(result), "pairs": result}
    if len(result) == pairs:
        a = statistics.median(x["same_s"] for x in result)
        b = statistics.median(x["new_s"] for x in result)
        output.update(same_median_s=a, new_median_s=b,
                      new_over_same=b / a if a else None,
                      new_slower_pairs=sum(x["difference_s"] > 0 for x in result))
    return output


def run_check(executor, output_dir=None, pairs=PAIRS, expected_user=EXPECTED_USER,
              clock=time.perf_counter):
    if type(pairs) is not int or not 2 <= pairs <= 8:
        raise ValueError("PAIRS_MUST_BE_2_TO_8")
    run_id = uuid.uuid4().hex
    directory = Path(output_dir or "gold-plsql-checks") / run_id
    directory.mkdir(parents=True, exist_ok=False)
    report_path = directory / "REPORT.json"
    payload = synthetic_payload(run_id)
    fixed = make_block(payload, run_id, 0)
    blocks = {0: fixed, **{i: make_block(payload, run_id, i) for i in range(1, pairs + 1)}}
    if len(fixed.encode()) > 1024 * 1024:
        raise ValueError("SYNTHETIC_SQL_TOO_LARGE")
    try:
        parameters = list(inspect.signature(executor.query_to_df).parameters)
    except (TypeError, ValueError):
        parameters = []
    report = {"version": "g19-plsql-reuse-check-r1", "run_id": run_id,
              "status": "RUNNING", "connection": CONNECTION,
              "query_to_df_parameters": parameters,
              "bind_support": "NOT_TESTED; signature/kwargs do not prove JDBC binding",
              "sql_bytes": len(fixed.encode()), "payload_bytes": len(payload.encode()),
              "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
              "planned_pairs": pairs, "samples": [],
              "scope": "synthetic gzip HEX CLOB; no table DML/DDL/COMMIT; no parse timer",
              "order": "PING then SAME/NEW on odd pairs; PING then NEW/SAME on even pairs",
              "timeout": "checked before calls and after slow calls; no remote cancel guarantee"}

    def save():
        temp = directory / "REPORT.tmp"
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(report_path)

    start = clock()
    identity = None

    def call(label, block=None, pair=0, expected_marker=None):
        nonlocal identity
        if clock() - start >= TOTAL_SECONDS:
            raise RuntimeError("G19_TOTAL_TIME_LIMIT")
        sample = {"label": label, "pair": pair, "status": "SENT",
                  "sql_sha256": hashlib.sha256((block or IDENTITY_SQL).encode()).hexdigest()}
        report["samples"].append(sample)
        save()
        before = clock()
        try:
            kwargs = {"pre_queries": [block]} if block else {}
            frame = executor.query_to_df(IDENTITY_SQL, **kwargs)
            if expected_marker:
                raise RuntimeError("G19_PREQUERY_NOT_EXECUTED")
            rows = frame.to_dict(orient="records")
            if len(rows) != 1:
                raise RuntimeError("G19_RESPONSE_SHAPE")
            row = {str(k).upper(): str(v) for k, v in rows[0].items()}
            if float(row["OK"]) != 1 or row["LOGIN_USER"].upper() != expected_user.upper():
                raise RuntimeError("G19_CONNECTION_IDENTITY_MISMATCH")
            key = tuple(row[x] for x in ("LOGIN_USER", "DB_NAME", "CON_NAME"))
            if identity is not None and key != identity:
                raise RuntimeError("G19_DATABASE_CHANGED")
            identity = key
            sample.update(status="OK", identity=row)
        except BaseException as exc:
            # 원본 오류에 SQL/연결 정보가 포함될 수 있어 전체 문자열을 저장하지 않음.
            message = str(exc)
            codes = sorted(set(re.findall(r"ORA-\d{5}", message)))
            # marker가 에러에 인용된 SQL에만 나타나는 경우를 성공으로 오인하지 않음.
            expected_error = (expected_marker and
                re.search(r"ORA-20986:\s*" + re.escape(expected_marker) + r"\b", message) and
                set(codes) <= {"ORA-20986", "ORA-06512"})
            if expected_error:
                sample.update(status="EXPECTED_ERROR", oracle_codes=codes)
            else:
                sample.update(status="INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED",
                              error_type=type(exc).__name__, oracle_codes=codes,
                              diagnostic_codes=re.findall(r"\bG19_[A-Z_]+\b", message)[:5])
                raise
        finally:
            sample["request_s"] = clock() - before
            save()
        print("%-14s %7.3f 초" % (label, sample["request_s"]), flush=True)
        if sample["request_s"] >= STOP_AFTER_SLOW_SECONDS:
            raise RuntimeError("G19_SLOW_CALL_STOP")

    print("연결:", CONNECTION, "| SQL: %.1f KiB" % (len(fixed.encode()) / 1024), flush=True)
    print("결과 저장:", report_path.resolve(), flush=True)
    try:
        call("IDENTITY")
        marker = "G19_PREQUERY_OK_" + run_id
        call("PREQUERY_CHECK", "BEGIN RAISE_APPLICATION_ERROR(-20986,'%s'); END;" % marker,
             expected_marker=marker)
        call("SAME_FIRST", fixed)  # 최초 요청 별도 보존. DB 전체 cold 상태라는 뜻은 아님.
        for pair in range(1, pairs + 1):
            call("PING", pair=pair)
            order = ("SAME", "NEW") if pair % 2 else ("NEW", "SAME")
            for label in order:
                call(label, blocks[0 if label == "SAME" else pair], pair)
        report["status"] = "COMPLETE"
    except BaseException as exc:
        report["status"] = "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "STOPPED"
        report["stop"] = {"error_type": type(exc).__name__,
                          "oracle_codes": sorted(set(re.findall(r"ORA-\d{5}", str(exc)))),
                          "diagnostic_codes": re.findall(r"\bG19_[A-Z_]+\b", str(exc))[:5]}
        print("중단:", report["stop"], "추가 요청을 실행하지 않습니다.", flush=True)
    finally:
        report["elapsed_s"] = clock() - start
        report["summary"] = summarize(report["samples"], pairs)
        instances = {s["identity"]["INSTANCE_NAME"] for s in report["samples"] if "identity" in s}
        report["multiple_instances_observed"] = len(instances) > 1
        save()

    print("\n결과:", report["status"])
    print("회차   같은 SQL(초)   새 SQL(초)   차이(초)   PING(초)")
    for item in report["summary"]["pairs"]:
        print("%3d    %10.3f   %9.3f   %8.3f   %8.3f" %
              (item["pair"], item["same_s"], item["new_s"], item["difference_s"], item["ping_s"]))
    summary = report["summary"]
    if report["status"] == "COMPLETE" and "new_over_same" in summary:
        print("중앙값: 같은 SQL %.3f초 / 새 SQL %.3f초 / 새 SQL이 느린 회차 %d/%d" %
              (summary["same_median_s"], summary["new_median_s"], summary["new_slower_pairs"], pairs))
    if report["multiple_instances_observed"]:
        print("여러 Oracle 인스턴스가 관측됐습니다. cursor 재사용 비교에 영향을 줄 수 있습니다.")
    print("주석만 변경한 합성 시험입니다. 차이는 순수 파싱 시간/실제 적재 개선율이 아닙니다.")
    print("실제 bind 전송은 미시험입니다. 결과 파일:", report_path.resolve())
    return report


if __name__ == "__main__":
    from dataiku import SQLExecutor2
    G19_PLSQL_REPORT = run_check(SQLExecutor2(connection=CONNECTION))
