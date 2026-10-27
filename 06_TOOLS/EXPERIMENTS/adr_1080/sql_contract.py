"""Prospectively fixed ADR1080 SQLite relation-visibility census.

Importing this module performs no product call. The owner freezes the matrix,
both code roots and this harness before calling run(base, cand, matrix, out).
Only tiny in-memory databases and synthetic selection sidecars are created.
No prior ADR fixture is imported. Query counts exclude fixture setup, schema
inspection, serialization and denied-write guard probes, which are recorded
separately from the declared consumer/error/EXPLAIN observations.
"""
from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import importlib
from itertools import product
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import traceback
from types import ModuleType, SimpleNamespace


SCHEMA = "adr1080-prospective-reference-visibility-v1"
ROLES = ("reference_end", "reference_target", "reference_candidate", "reference_candidate_end")
COLUMNS = {
    "source": ("id", "document_id", "article", "json"),
    "reference": ("id", "document_id", "json"),
    "reference_end": ("source_id", "reference_id"),
    "reference_target": ("reference_id", "ordinal", "source_id", "unit_id", "unit_path", "block_ids", "target_level"),
    "reference_candidate": ("reference_id", "candidate_id", "ordinal", "source_id", "unit_id", "unit_path", "block_ids", "target_level", "basis", "json"),
    "reference_candidate_end": ("source_id", "reference_id", "candidate_id"),
}
BASE_DDL = """
CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
CREATE INDEX source_document ON source(document_id);
CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));
CREATE TABLE reference_target(reference_id TEXT,ordinal INTEGER,source_id TEXT,unit_id TEXT,
 unit_path TEXT,block_ids TEXT,target_level TEXT,PRIMARY KEY(reference_id,ordinal));
CREATE INDEX reference_target_source ON reference_target(source_id,reference_id);
CREATE TABLE reference_candidate(reference_id TEXT,candidate_id TEXT,ordinal INTEGER,source_id TEXT,
 unit_id TEXT,unit_path TEXT,block_ids TEXT,target_level TEXT,basis TEXT,json TEXT,
 PRIMARY KEY(reference_id,candidate_id));
CREATE TABLE reference_candidate_end(source_id TEXT,reference_id TEXT,candidate_id TEXT,
 PRIMARY KEY(source_id,reference_id,candidate_id));
"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def typed(value):
    kind = type(value)
    if kind is dict:
        return ["dict", [[typed(k), typed(v)] for k, v in value.items()]]
    if kind in (tuple, list):
        return [kind.__name__, [typed(v) for v in value]]
    if kind in (str, int, float, bool, type(None)):
        return [kind.__name__, value]
    if kind is bytes:
        return ["bytes", value.hex()]
    raise TypeError("unplanned diagnostic value: " + kind.__name__)


def _runtime(root, role):
    root = Path(root).resolve()
    name = "_adr1080_" + role + "_" + _sha(str(root).encode())[:12]
    if name in sys.modules:
        raise RuntimeError("use a fresh process for a new ADR1080 run")
    package = ModuleType(name)
    package.__package__ = name
    package.__path__ = [str(root / "02_BACKEND/semantic_runtime")]
    sys.modules[name] = package
    sys.path.insert(0, str(root / "02_BACKEND"))
    return SimpleNamespace(
        selection=importlib.import_module(name + ".search_selection"),
        build=importlib.import_module(name + ".reference_build"),
        readonly=importlib.import_module(name + ".resident_data")._readonly)


def _selection(runtime, root, mode, matrix):
    generation = root / mode / "generation"
    generation.mkdir(parents=True)
    manifest = {"generation_id": "adr1080-synthetic", "store_sha256": "synthetic-only"}
    manifest_path = generation / "manifest.json"
    manifest_path.write_text(_json(manifest), encoding="utf-8")
    spec = matrix["bind_modes"][mode]
    if spec["excluded"] or spec["latest"]:
        value = {"schema_version": runtime.selection.LATEST_VERSION if spec["latest"] else runtime.selection.VERSION,
                 **manifest, "manifest_sha256": _sha(manifest_path.read_bytes()),
                 "excluded": [{"document_id": did, "source_artifact_sha256": "synthetic-only"}
                              for did in spec["excluded"]]}
        if spec["latest"]:
            value["latest_documents"] = [{"document_id": did, "is_latest": True} for did in spec["latest"]]
        sidecar = runtime.selection.selection_path(generation)
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text(_json(value), encoding="utf-8")
    selection = runtime.selection.Selection(generation, manifest)
    assert set(selection.excluded) == set(spec["excluded"])
    assert set(selection.latest) == set(spec["latest"])
    return selection


def _reference(ident, document):
    witness = "합성 인용 원문 " + str(ident)
    # Source text is last so the compact schema's remove/reinsert projection
    # has the same canonical JSON representation as this independent row oracle.
    payload = {"id": ident, "document_id": document, "ordinal": 1, "flag": True,
               "extra": None, "source_text_sha256": _sha(witness.encode()), "source_text": witness}
    return ident, document, _json(payload)


def _fixture_rows(case):
    rows = {name: [] for name in COLUMNS}
    for kind, document in (("visible", "visible"), ("hidden", "hidden")):
        for index in range(3):
            rows["source"].append((f"s-{kind}-{index}", document, "제1조", _json({"kind": kind, "n": index})))
    state = case.get("reference_state", "visible")
    subject = None if state == "null_id" else "" if state == "empty_id" else "R10"
    if state != "empty_reference_set":
        rows["reference"] += [_reference("R00", "visible"), _reference("R20", "hidden")]
        if state != "orphan":
            document = "hidden" if state == "hidden_owner" else None if state == "null_document" else "visible"
            rows["reference"].append(_reference(subject, document))
    focus = "s-visible-0"
    special = None
    if case["category"] == "source_boundary":
        source_state = case["source_state"]
        special = {"missing": "missing-source", "null_id": None,
                   "null_document": "null-document-source", "empty_id": ""}[source_state]
        focus = special
        if source_state != "missing":
            rows["source"].append((special, None if source_state == "null_document" else "visible",
                                   "제2조", _json({"source_state": source_state})))
    multiplicity = case.get("multiplicity", 3)
    mask = case.get("hidden_mask", 0)
    for ident, repeats in (("R00", 1), ("R20", 1), (subject, multiplicity)):
        for index in range(repeats):
            for bit, role in enumerate(ROLES):
                source = f"s-{'hidden' if mask & (1 << bit) and ident == subject else 'visible'}-{index}"
                if case["category"] == "source_boundary" and ident == subject and role == case["role"]:
                    source = special
                if role == "reference_end":
                    row = source, ident
                elif role == "reference_target":
                    row = ident, index, source, "0", '["제1조"]', '["0"]', "article"
                elif role == "reference_candidate":
                    row = (ident, "C" + str(index), index, source, "0", '["제1조"]', '["0"]',
                           "article", "EXPLICIT", _json({"rank": index, "note": "합성 후보", "nullable": None}))
                else:
                    row = source, ident, "C" + str(index)
                rows[role].append(row)
    if case["category"] == "point_plans":
        rows["reference"].extend(_reference(f"R-background-{i:03d}", "visible") for i in range(64))
    if case.get("order") == "reverse":
        rows = {name: list(reversed(values)) for name, values in rows.items()}
    return rows, subject, focus


def _database(runtime, case):
    rows, subject, focus = _fixture_rows(case)
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA cache_size=-1024")
    db.execute("PRAGMA temp_store=MEMORY")
    db.executescript(BASE_DDL)
    if case["layout"] == "compact":
        runtime.build.shared_reference_schema(db)
    for name, values in rows.items():
        placeholders = ",".join("?" for _ in COLUMNS[name])
        db.executemany(f'INSERT INTO "{name}" VALUES ({placeholders})', values)
    if case["category"] == "requested_failures":
        fault = case["fault"]
        if fault == "requested_malformed_json":
            table = "reference_payload" if case["layout"] == "compact" else "reference"
            db.execute(f"UPDATE {table} SET json=? WHERE id=?", ("{malformed", subject))
        elif fault == "missing_reference_relation":
            db.execute(("DROP VIEW" if case["layout"] == "compact" else "DROP TABLE") + " reference")
        elif fault == "missing_source_relation":
            db.execute("DROP TABLE source")
        else:
            raise ValueError(fault)
    db.commit()
    db.execute("PRAGMA query_only=ON")
    db.set_authorizer(runtime.readonly)
    return db, rows, subject, focus


def _sql_in(value, values):
    if not values:
        return False
    if value is None:
        return None
    if any(other is not None and value == other for other in values):
        return True
    return None if None in values else False


def _sql_not_in(value, values):
    found = _sql_in(value, values)
    return None if found is None else not found


def _eq(left, right):
    return left is not None and right is not None and left == right


def _gt(left, right):
    return left is not None and right is not None and left > right


def _order(value):
    if value is None:
        return 0, ""
    if type(value) in (int, float):
        return 1, value
    if isinstance(value, str):
        return 2, value.encode("utf-8")
    if isinstance(value, bytes):
        return 3, value
    raise TypeError(type(value).__name__)


def _sorted(rows, columns, order):
    indices = [columns.index(column) for column in order]
    return sorted(rows, key=lambda row: tuple(_order(row[index]) for index in indices))


def _visible(rows, mode, matrix):
    if mode == "early_return":
        return deepcopy(rows)
    excluded = matrix["bind_modes"][mode]["excluded"]
    result = deepcopy(rows)
    result["source"] = [row for row in rows["source"] if _sql_not_in(row[1], excluded) is True]
    hidden_source_ids = [row[0] for row in rows["source"] if _sql_in(row[1], excluded) is True]
    hidden_reference_lists = []
    for role in ROLES[:3]:
        columns = COLUMNS[role]
        hidden_reference_lists.append([row[columns.index("reference_id")] for row in rows[role]
            if _sql_in(row[columns.index("source_id")], hidden_source_ids) is True])
    result["reference"] = [row for row in rows["reference"]
        if _sql_not_in(row[1], excluded) is True
        and all(_sql_not_in(row[0], hidden) is True for hidden in hidden_reference_lists)]
    ids = [row[0] for row in result["reference"]]
    for role in ROLES:
        index = COLUMNS[role].index("reference_id")
        result[role] = [row for row in rows[role] if _sql_in(row[index], ids) is True]
    return result


def _success(columns, rows):
    return {"status": "success", "columns": list(columns), "rows": typed(rows)}


def _query(db, label, sql, params, expected=None):
    try:
        cursor = db.execute(sql, params)
        actual = _success([column[0] for column in cursor.description], cursor.fetchall())
    except Exception as exc:
        actual = {"status": "error", "type": type(exc).__name__, "message": str(exc)}
    return {"label": label, "sql": sql, "params": typed(tuple(params)), "actual": actual,
            "expected": expected, "oracle_matches": expected is None or actual == expected}


def _queries(db, visible, subject, focus, matrix):
    spec = matrix["consumer_queries"]
    observations = []
    for name in COLUMNS:
        columns = COLUMNS[name]
        sql = 'SELECT * FROM "' + name + '" ORDER BY ' + ",".join('"' + c + '"' for c in columns)
        observations.append(_query(db, "projection/" + name, sql, (),
            _success(columns, _sorted(visible[name], columns, columns))))
    sources = {"focus": focus, "hidden": "s-hidden-0", "null": None, "absent": "absent-query-source"}
    for role, source_label, cursor, limit in product(ROLES, spec["source_labels"], spec["cursor"], spec["limit"]):
        source = sources[source_label]
        columns = COLUMNS[role]
        order = ("reference_id",) + tuple(c for c in columns if c != "reference_id")
        chosen = [row for row in visible[role] if _eq(row[columns.index("source_id")], source)
                  and _gt(row[columns.index("reference_id")], cursor)]
        expected = _success(columns, _sorted(chosen, columns, order)[:limit])
        sql = ('SELECT * FROM "' + role + '" WHERE source_id=? AND reference_id>? ORDER BY '
               + ",".join('"' + c + '"' for c in order) + ' LIMIT ?')
        label = _json(["relation_page", role, source_label, cursor, limit])
        observations.append(_query(db, label, sql, (source, cursor, limit), expected))
    for source_label, cursor, limit, restriction in product(spec["source_labels"], spec["cursor"], spec["limit"], spec["only_references"]):
        source = sources[source_label]
        allow = None if restriction == "unrestricted" else [] if restriction == "empty" else [subject]
        matches = [row for row in visible["reference"] if _gt(row[0], cursor)
                   and (allow is None or _sql_in(row[0], allow) is True)
                   and any(_eq(edge[0], source) and _eq(edge[1], row[0]) for edge in visible["reference_end"])]
        matches = _sorted(matches, COLUMNS["reference"], ("id",))
        seen, distinct = set(), []
        for row in matches:
            if row[2] not in seen:
                distinct.append((row[2],)); seen.add(row[2])
        clause = '' if allow is None else ' AND r.id IN (SELECT value FROM json_each(?))'
        params = (source, cursor, *([] if allow is None else [_json(allow)]), limit)
        sql = ('SELECT DISTINCT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id '
               'WHERE e.source_id=? AND r.id>?' + clause + ' ORDER BY r.id LIMIT ?')
        label = _json(["catalog", source_label, cursor, limit, restriction])
        observations.append(_query(db, label, sql, params, _success(("json",), distinct[:limit])))
    columns = COLUMNS["reference_candidate"]
    projection = tuple(c for c in columns if c != "reference_id")
    for label in spec["candidate_reference_labels"]:
        ident = subject if label == "subject" else "R-ABSENT" if label == "orphan" else None
        chosen = [row for row in visible["reference_candidate"] if _eq(row[0], ident)]
        chosen = _sorted(chosen, columns, ("ordinal", "candidate_id"))
        expected = _success(projection, [tuple(row[columns.index(c)] for c in projection) for row in chosen])
        sql = ('SELECT ' + ','.join(projection) + ' FROM reference_candidate WHERE reference_id=? ORDER BY ordinal,candidate_id')
        observations.append(_query(db, "candidate/" + label, sql, (ident,), expected))
    return observations


def _guard(db):
    outcomes = []
    for sql in ("DELETE FROM main.reference_end", "PRAGMA query_only=OFF"):
        try:
            db.execute(sql)
            outcomes.append({"sql": sql, "denied": False})
        except sqlite3.DatabaseError as exc:
            outcomes.append({"sql": sql, "denied": True, "type": type(exc).__name__, "message": str(exc)})
    return {"query_only": db.execute("PRAGMA query_only").fetchone()[0], "attempts": outcomes}


def _point_plan(db, case, subject):
    role = case["view"]
    sql = 'SELECT * FROM "' + role + '" WHERE source_id=? AND reference_id=?'
    rows = db.execute("EXPLAIN QUERY PLAN " + sql, ("s-visible-0", subject)).fetchall()
    details = [row[3] for row in rows]
    reference_index = "sqlite_autoindex_reference_payload_1" if case["layout"] == "compact" else "sqlite_autoindex_reference_1"
    alias = "r" if case["layout"] == "compact" else "original"
    return {"label": "point_plan/" + role, "sql": sql, "params": typed(("s-visible-0", subject)),
            "query_plan": rows, "categories": {
                "membership_reference_full_scan": any(re.match(r"^SCAN " + alias + r"(?:$| )", line) for line in details),
                "reference_id_index_point": any(line.startswith("SEARCH ") and reference_index in line and "(id=?)" in line for line in details),
                "list_subquery": any("LIST SUBQUERY" in line for line in details),
                "correlated_subquery": any("CORRELATED" in line and "SUBQUERY" in line for line in details),
                "other_scans": [line for line in details if line.startswith("SCAN ") and not re.match(r"^SCAN " + alias + r"(?:$| )", line)],
            }}


def _arm(runtime, selection, case, matrix, arm):
    db = None
    observations = []
    try:
        db, rows, subject, focus = _database(runtime, case)
        before = _sha(db.serialize(name="main"))
        selection_before = typed((selection.excluded and sorted(selection.excluded) or [], selection.latest, selection.fingerprint))
        selection.bind(db, navigation=True)
        temp_views = dict(db.execute("SELECT name,sql FROM temp.sqlite_master WHERE type='view'"))
        expected_predicate = matrix["target"]["baseline_predicate" if arm == "baseline" else "optimized_predicate"]
        if case["bind_mode"] == "early_return":
            binding_valid = not temp_views
        else:
            binding_valid = all(name in temp_views and temp_views[name].endswith(" WHERE " + expected_predicate) for name in ROLES)
        if case["category"] == "point_plans":
            observations.append(_point_plan(db, case, subject))
        elif case["category"] == "requested_failures":
            fault = case["fault"]
            if fault == "requested_malformed_json":
                sql, params = "SELECT json_extract(r.json,'$.source_text') AS witness FROM reference r WHERE r.id=?", (subject,)
            elif fault == "missing_reference_relation":
                sql, params = "SELECT json FROM reference WHERE id=?", (subject,)
            else:
                sql, params = "SELECT id FROM source WHERE id=?", ("s-visible-0",)
            observations.append(_query(db, fault, sql, params))
        else:
            visible = _visible(rows, case["bind_mode"], matrix)
            observations = _queries(db, visible, subject, focus, matrix)
        guard = _guard(db)
        after = _sha(db.serialize(name="main"))
        selection_after = typed((selection.excluded and sorted(selection.excluded) or [], selection.latest, selection.fingerprint))
        return {"status": "COMPLETE", "observations": observations,
                "main_before_sha256": before, "main_after_sha256": after,
                "selection_unchanged": selection_before == selection_after,
                "binding_valid": binding_valid, "temp_views": temp_views, "guard": guard}
    except BaseException as exc:
        return {"status": "HARNESS_ERROR", "observations": observations,
                "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc()}
    finally:
        if db is not None:
            db.close()


def _problems(case, left, right, matrix):
    errors = []
    if left["status"] != "COMPLETE" or right["status"] != "COMPLETE":
        return ["fixture arm did not complete"]
    expected_count = 1 if case["category"] in ("point_plans", "requested_failures") else matrix["consumer_queries"]["queries_per_regular_fixture_per_arm"]
    if len(left["observations"]) != expected_count or len(right["observations"]) != expected_count:
        errors.append("declared observation count differs")
    for name, result in (("baseline", left), ("optimized", right)):
        if result["main_before_sha256"] != result["main_after_sha256"]:
            errors.append(name + " mutated main database bytes")
        if not result["selection_unchanged"] or not result["binding_valid"]:
            errors.append(name + " selection/binding contract changed")
        if result["guard"]["query_only"] != 1 or not all(r["denied"] for r in result["guard"]["attempts"]):
            errors.append(name + " failed the read-only guard")
    if left["main_before_sha256"] != right["main_before_sha256"]:
        errors.append("paired fixture database bytes differ")
    if left["guard"] != right["guard"]:
        errors.append("paired read-only failure outcomes differ")
    for index, (a, b) in enumerate(zip(left["observations"], right["observations"])):
        if case["category"] == "point_plans":
            base, opt = a["categories"], b["categories"]
            if not base["list_subquery"] or not base["membership_reference_full_scan"]:
                errors.append("baseline point plan lacks the declared membership list/reference scan")
            if not opt["correlated_subquery"] or not opt["reference_id_index_point"] or opt["membership_reference_full_scan"]:
                errors.append("optimized point plan lacks reference-ID correlation/point lookup or retains full reference scan")
            continue
        if a != b:
            errors.append(f"query {index} has unequal typed result/error/metadata")
        if not a["oracle_matches"] or not b["oracle_matches"]:
            errors.append(f"query {index} violates the independent SQL-row oracle")
        if case["category"] == "requested_failures" and (a["actual"]["status"] != "error" or b["actual"]["status"] != "error"):
            errors.append("requested malformed/missing relation did not raise")
    return errors


def _cases(matrix):
    axes = {
        "visibility": ("layout", "reference_state", "hidden_mask", "bind_mode", "multiplicity"),
        "source_boundary": ("layout", "source_state", "role", "bind_mode", "multiplicity"),
        "insertion_order": ("layout", "bind_mode", "order"),
        "requested_failures": ("layout", "fault", "bind_mode"),
        "point_plans": ("layout", "bind_mode", "view"),
    }
    for category, keys in axes.items():
        for number, values in enumerate(product(*(matrix["categories"][category][key] for key in keys)), 1):
            yield {"id": category + "/" + f"{number:04d}", "category": category, **dict(zip(keys, values))}


def run(base, cand, matrix, out):
    """Run once after owner freeze, in a bounded network-disabled process."""
    if matrix["schema_version"] != SCHEMA or tuple(matrix["target"]["views"]) != ROLES:
        raise ValueError("unexpected ADR1080 matrix schema/views")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "sql-pairs.jsonl.gz"
    failure_path = out / "sql-first-failure.json"
    counts = {category: 0 for category in matrix["categories"]}
    query_counts = {"consumer": 0, "requested_failure": 0, "explain": 0}
    current = None
    with gzip.open(raw, "xt", encoding="utf-8") as stream:
        def emit(row):
            stream.write(_json(row) + "\n")
            stream.flush()

        try:
            emit({"kind": "manifest", "schema": SCHEMA, "sqlite_version": sqlite3.sqlite_version,
                  "matrix_canonical_sha256": _sha(_json(matrix).encode()),
                  "baseline_root": str(Path(base).resolve()), "optimized_root": str(Path(cand).resolve()),
                  "counts_definition": "consumer/error/EXPLAIN only; fixture and guard SQL excluded"})
            runtimes = {"baseline": _runtime(base, "baseline"), "optimized": _runtime(cand, "optimized")}
            with tempfile.TemporaryDirectory(prefix="adr1080-synthetic-selection-") as temporary:
                selections = {arm: {mode: _selection(runtime, Path(temporary) / arm, mode, matrix)
                                   for mode in matrix["bind_modes"]} for arm, runtime in runtimes.items()}
                for case in _cases(matrix):
                    left = _arm(runtimes["baseline"], selections["baseline"][case["bind_mode"]], case, matrix, "baseline")
                    right = _arm(runtimes["optimized"], selections["optimized"][case["bind_mode"]], case, matrix, "optimized")
                    problems = _problems(case, left, right, matrix)
                    current = {"kind": "pair", "case": case, "baseline": left, "optimized": right, "problems": problems}
                    emit(current)
                    counts[case["category"]] += 1
                    query_kind = "explain" if case["category"] == "point_plans" else "requested_failure" if case["category"] == "requested_failures" else "consumer"
                    query_counts[query_kind] += len(left["observations"])
                    if problems:
                        raise AssertionError(case["id"] + ": " + problems[0])
            for category, count in counts.items():
                if count != matrix["counts"][category] or count != matrix["categories"][category]["paired_cases"]:
                    raise AssertionError("category fixture census mismatch: " + category)
            if sum(counts.values()) != matrix["counts"]["total_pairs"]:
                raise AssertionError("total fixture census mismatch")
            for kind, field in (("consumer", "consumer_queries_per_arm"),
                                ("requested_failure", "requested_failure_queries_per_arm"),
                                ("explain", "explain_queries_per_arm")):
                if query_counts[kind] != matrix["counts"][field]:
                    raise AssertionError("query census mismatch: " + kind)
            if sum(query_counts.values()) != matrix["counts"]["total_query_observations_per_arm"]:
                raise AssertionError("total query observation census mismatch")
            result = {"status": "PASS", "paired_cases": sum(counts.values()), "counts": counts,
                      "failures": 0, "query_counts_per_arm": query_counts,
                      "sql_result_queries_per_arm": query_counts["consumer"] + query_counts["requested_failure"],
                      "query_observations_per_arm": sum(query_counts.values()),
                      "total_query_observations": 2 * sum(query_counts.values()),
                      "guard_attempts_per_arm": 2 * sum(counts.values()), "raw_path": str(raw),
                      "plan_pairs": counts["point_plans"], "real_data_loads": 0,
                      "external_model_calls": 0, "legal_quality_certified": False,
                      "end_to_end_speed_certified": False}
            emit({"kind": "summary", "result": result})
            return result
        except BaseException as exc:
            failure = {"status": "FAIL", "paired_cases": sum(counts.values()), "counts": counts,
                       "failures": 1, "query_counts_per_arm": query_counts, "raw_path": str(raw),
                       "error_type": type(exc).__name__, "error": str(exc),
                       "traceback": traceback.format_exc(), "first_failed_pair": current}
            emit({"kind": "failure", "failure": failure})
            with failure_path.open("x", encoding="utf-8") as output:
                json.dump(failure, output, ensure_ascii=False, indent=2)
                output.write("\n")
            raise
