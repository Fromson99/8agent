#!/usr/bin/env python3
"""Build the exact 19-document financial external repair handoff."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "01_DATA"
OUT = Path.home() / "GENOS_HANDOFF/GENOS_FINANCIAL_EXTERNAL_19_20260930_R3.zip"
SCOPE = DATA / "CATALOG/SCOPES/photo-required-80-hwpx-20260917.json"
RECEIPT = ROOT / "09_ARTIFACTS/AUDITS/20260930-financial-photo61-share/receipt.json"
SOURCE_MANIFEST = next((DATA / "PACKAGES/EXTERNAL").glob(
    "source-forms-e95be5b5f8bc3d36/gen-*/ARTIFACTS/SOURCE_MANIFEST.json"))


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))["documents"][:61]
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    provenance = {item["body_sha256"]: item for item in source_manifest["items"]}
    rows: list[dict] = []
    originals: dict[str, Path] = {}
    public_names = set()
    for item in receipt["shared_files"]:
        if item["security_class"] != "public":
            continue
        source, target = item["source"], item["target"]
        if not source.startswith("RAW/external/risk_team/") or target != source.replace(
                "/risk_team/", "/financial_team/", 1):
            raise ValueError("wrong risk source or financial target")
        public_names.add(item["document"])
    if len(public_names) != 9:
        raise ValueError("expected nine risk-shared document names")
    forms = scope[51:61]
    form_files = 0
    for doc in forms:
        for item in doc["files"]:
            origin = DATA / item["path"]
            raw = origin.read_bytes()
            if sha(raw) != item["sha256"]:
                raise ValueError("form original hash differs: " + item["path"])
            record = provenance.get(item["sha256"])
            if record is None:
                record = next((p for p in provenance.values() for attachment in p.get("attachments", [])
                               if attachment["sha256"] == item["sha256"]), None)
            if record is None:
                raise ValueError("form source provenance absent: " + doc["name"])
            category = "klca" if record["kind"] == "klca-model" else "krx"
            if record["kind"] not in {"klca-model", "krx-form"}:
                raise ValueError("unreviewed source category")
            target = "RAW/external/financial_team/" + category + "/" + doc["name"] + "/" + origin.name
            rows.append({"document": doc["name"], "role": "financial_external_form",
                         "source_path": item["path"], "target_path": target,
                         "external_source": category, "kind": record["kind"],
                         "source_origin": record["origin"], "raw_role": item["role"],
                         "security_class": item["security_class"],
                         "export_allowed": item["export_allowed"],
                         "sha256": item["sha256"], "bytes": len(raw)})
            originals["DATA/" + target] = origin
            form_files += 1
    if len(forms) != 10 or form_files != 11 or len(rows) != 11 or len(originals) != 11:
        raise ValueError("bundle must carry only eleven absent originals")
    manifest = {"schema_version": "financial-external-19-r3",
                "scope_sha256": sha(SCOPE.read_bytes()),
                "document_counts": {"risk_shared": 9, "financial_external_forms": 10},
                "shared_document_names": sorted(public_names),
                "file_counts": {"financial_external_forms": 11},
                "payload_policy": "only eleven absent form files; discover shared files in GENOS risk_team",
                "records": sorted(rows, key=lambda row: row["target_path"])}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         strict_timestamps=True) as archive:
        archive.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False,
                                                      sort_keys=True, indent=2) + "\n")
        for member, origin in sorted(originals.items()):
            archive.write(origin, member)
    with zipfile.ZipFile(OUT) as archive:
        if set(archive.namelist()) != {"MANIFEST.json", *originals}:
            raise ValueError("archive inventory differs")
        if any(sha(archive.read("DATA/" + r["target_path"])) != r["sha256"]
               for r in rows if r["role"] == "financial_external_form"):
            raise ValueError("archive member hash differs")
    print(OUT)
    print("bytes=" + str(OUT.stat().st_size) + " sha256=" + sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
