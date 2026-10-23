"""Validate design artifacts only. No database connection or runtime mutation."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import sqlglot
from sqlglot import exp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
REPORT = HERE.parent

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()

def normalized(text):
    return re.sub(r"\s+", "", text).upper()

spec = json.loads((HERE / "SCHEMA_DRAFT.json").read_text())
ddl = (HERE / "ORACLE_DDL_DRAFT.sql").read_text()
queries = (HERE / "READ_QUERIES.sql").read_text()
tables = {t["name"]: t for t in spec["tables"]}
assert len(tables) == len(spec["tables"]) == 18
constraint_names = set()
index_names = set()
foreign_keys = 0
checks = 0
indexes = 0
ddl_compact = normalized(ddl)

for name, table in tables.items():
    assert re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", name)
    columns = {c["name"]: c for c in table["columns"]}
    assert len(columns) == len(table["columns"])
    assert set(table["pk"]) <= columns.keys()
    for column in columns.values():
        assert len(column["name"]) <= 30
        expected = normalized(column["name"] + " " + column["type"] + " " + column["extra"])
        assert expected in ddl_compact, (name, column["name"])
    keys = [table["pk"]] + [u["columns"] for u in table["uniques"]]
    for key in keys:
        assert set(key) <= columns.keys()
    all_constraints = [name + "_PK"]
    all_constraints += [name + "_C" + str(i + 1) for i in range(len(table["checks"]))]
    all_constraints += [u["name"] for u in table["uniques"]]
    all_constraints += [f["name"] for f in table["fks"]]
    for con in all_constraints:
        assert len(con) <= 30 and con not in constraint_names, con
        constraint_names.add(con)
        assert "CONSTRAINT" + con in ddl_compact, con
    for check in table["checks"]:
        assert "CHECK(" + normalized(check) + ")" in ddl_compact
        checks += 1
    for f in table["fks"]:
        assert set(f["columns"]) <= columns.keys(), f
        assert len(f["columns"]) == len(f["target_columns"]), f
        parent = tables.get(f["target"]) or spec["existing_tables"].get(f["target"])
        assert parent is not None, f
        parent_keys = [parent["pk"]] + [u["columns"] for u in parent.get("uniques", [])]
        assert f["target_columns"] in parent_keys, f
        if f["target"] in tables:
            pc = {c["name"]: c for c in parent["columns"]}
            for left, right in zip(f["columns"], f["target_columns"]):
                assert columns[left]["type"] == pc[right]["type"], (name, left, f)
        expected = "FOREIGNKEY(" + ",".join(f["columns"]) + ")REFERENCES" + f["target"] + "(" + ",".join(f["target_columns"]) + ")"
        assert expected in ddl_compact, f
        foreign_keys += 1
    for ix in table["indexes"]:
        assert len(ix["name"]) <= 30 and ix["name"] not in index_names
        assert set(ix["columns"]) <= columns.keys()
        assert normalized("CREATE INDEX " + ix["name"] + " ON " + name + " (" + ", ".join(ix["columns"]) + ")") in ddl_compact
        index_names.add(ix["name"])
        indexes += 1

parsed_ddl = [s for s in sqlglot.parse(ddl, read="oracle") if s is not None]
parsed_queries = [s for s in sqlglot.parse(queries, read="oracle")
                  if s is not None and not isinstance(s, exp.Semicolon)]
assert all(isinstance(s, (exp.Create, exp.Alter)) for s in parsed_ddl)
assert all(isinstance(s, exp.Select) for s in parsed_queries)
assert len(parsed_queries) == 6
assert len(re.findall(r"^CREATE TABLE ", ddl, re.M)) == len(tables)
assert not re.search(r"^CREATE TABLE LK_(RECORD|HEAD|LOOKUP)\b", ddl, re.M)
assert not re.search(r"^\s*(DROP|TRUNCATE|GRANT|DELETE|UPDATE|INSERT)\b", ddl, re.M | re.I)

# Preserve completed validation records when rerunning after document reorganization.
validation_path = HERE / "VALIDATION_CURRENT.json"
if not validation_path.exists():
    validation_path.write_text('{"status":"VALIDATING"}\n')
layout_path = ROOT / "07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V3/DOCUMENT_MAP.json"
layout = json.loads(layout_path.read_text()) if layout_path.exists() else None
documents = [
    REPORT / "DATABASE_ARCHITECTURE.md", REPORT / "IMPLEMENTATION_NAMES.md",
    REPORT / "REVIEW.md", ROOT / "07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V3.md",
]
if layout:
    documents += [ROOT / part["path"] for part in layout["parts"]]
local_links = 0
for path in documents:
    text = path.read_text()
    assert sum(line.startswith("```") for line in text.splitlines()) % 2 == 0, path
    assert not any(line.rstrip() != line for line in text.splitlines()), path
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if "://" in target or target.startswith("#"):
            continue
        target = re.sub(r":\d+$", "", target.split("#")[0])
        assert (path.parent / target).exists(), (path.name, target)
        local_links += 1
    for block in re.findall(r"```json\n(.*?)```", text, re.S):
        json.loads(block)
if layout:
    source = "07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V3.md"
    mapped = {int(row["section"]) for row in layout["sections"]
              if row["source"] == source and row["section"].isdigit()}
    assert mapped == set(range(1, 25))
else:
    v3 = (ROOT / "07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V3.md").read_text()
    assert [int(n) for n in re.findall(r"^## (\d+)\.", v3, re.M)] == list(range(1, 25))

evidence = json.loads((HERE / "EVIDENCE.json").read_text())
assert sha(ROOT / evidence["active"]["path"]) == evidence["active"]["sha256"]
assert sha(REPORT / "EVIDENCE.json") == evidence["prior_review_evidence_sha256"]
for file in evidence["files"]:
    assert sha(ROOT / file["path"]) == file["working_sha256"], file["path"]
    if file.get("selected_path"):
        assert sha(ROOT / file["selected_path"]) == file["selected_sha256"]
        assert file["selected_matches_manifest"] is True

outputs = documents + [
    HERE / "SCHEMA_DRAFT.json", HERE / "ORACLE_DDL_DRAFT.sql",
    HERE / "READ_QUERIES.sql", HERE / "EVIDENCE.json", Path(__file__).resolve(),
]
result = {
    "schema_version": "legal-knowledge-db-design-validation-v1",
    "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "status": "STATIC_DESIGN_CHECKS_PASSED",
    "checks": {
        "new_tables": len(tables), "foreign_keys": foreign_keys,
        "check_constraints": checks, "proposed_indexes": indexes,
        "oracle_dialect_parsed_ddl_statements": len(parsed_ddl),
        "oracle_dialect_parsed_select_queries": len(parsed_queries),
        "unsupported_parser_commands": 0, "local_document_links": local_links,
        "v3_numbered_sections_mapped": 24, "split_topic_documents": len(layout["parts"]) if layout else 0,
        "evidence_source_files_unchanged": len(evidence["files"]),
        "active_pointer_unchanged": True, "prior_review_evidence_unchanged": True,
        "spec_ddl_column_key_constraint_consistency": True
    },
    "limits": [
        "SQLGlot Oracle-dialect parsing is not Oracle server execution or certification.",
        "No Oracle connection, DDL execution, query plan or performance measurement.",
        "No source dataset load, model call, runtime implementation, MAIN promotion or GENOS deployment.",
        "DDL checks do not enforce all cross-tenant, source, review-scope or payload invariants; services must implement them.",
        "This is author self-check, not independent review or legal quality evaluation."
    ],
    "validation_repair": "Initial query-count check rejected SQLGlot's empty Semicolon node for the final trailing comment. The checker now excludes that non-executable node; SQL statements and safety assertions are unchanged.",
    "artifacts": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in outputs],
}
validation_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": result["status"], **result["checks"]}, ensure_ascii=False))
