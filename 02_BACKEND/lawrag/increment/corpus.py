"""전체 세대 조립 — 지난 원문 ZIP에서 승인된 문서만 새 파일로 바꿔 새 전체 원문 ZIP을 만든다.

Gold는 세대 전체 스냅샷이다. 떨어진 폴더에는 바뀐 문서만 있으므로 그것만 구조화·게시하면
새 세대에서 나머지 문서가 사라진다. 그래서 다음 Gold 게시는 '지난 세대의 원문 + 승인된
교체 파일'로 만든 전체 원문 ZIP으로 R6(GENOS 구조화 → Agent → Gold)를 다시 돌린다.
보류·변경 없음 문서는 지난 파일을 그대로 둔다.

ZIP 형식은 R6 raw_zip_input과 같다. 실제 원문은 `external/<팀>/law/<문서명>/<문서명> 본문.xml`,
`internal/<팀>/…`처럼 출처 경로를 유지하고 `01_DATA/RAW/` 접두가 있어도 된다.

문서 식별 (떨어진 파일과 지난 원문에 같은 규칙)
- 법제처 본문 XML: 머리말의 법령ID·행정규칙ID → LAW:<ID> / ADMRUL:<ID>
- 그 밖(docx·pdf·hwp 등): 파일명에서 끝의 _YYYYMMDD와 ' 본문'을 뗀 이름 → INTERNAL:<해시>
같은 문서가 여러 팀 폴더에 있으면(실측: 재무팀·리스크팀 공통 법령 8개) 모두 같은 새 파일로 바꾼다.

출처 manifest.json(예전 `law/manifest.json` 형식)이 있으면 그 항목(본문 해시·시행일)도 고치고
정본 세대 계약을 다시 계산한다 (lawrag.core.legal_generation). 실제 external 형식은 manifest가 없다.

Gold 문서ID는 원문 파일 sha256 앞 16자리다 (실측: 로컬 Gold 상법·증권발행공시규정).
`verify_base`로 지난 원문 ZIP이 지금 서빙 세대의 문서 목록과 같은지 먼저 확인한다.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .structured import Header, name_code

RAW_PREFIX = "01_DATA/RAW/"
SOURCES = {"internal", "external", "law", "krx", "kofia", "expc", "fsc", "moleg", "prec"}
DOCUMENTS = {".xml", ".html", ".htm", ".pdf", ".hwp", ".hwpx", ".docx", ".doc"}
_DATE_TAIL = re.compile(r"[_\-\s]*\(?(?:19|20)\d{6}\)?$")
_BODY_TAIL = re.compile(r"\s*본문$")
_FIXED_TIME = (2026, 1, 1, 0, 0, 0)


class CorpusError(ValueError):
    pass


@dataclass(frozen=True)
class Replacement:
    """승인된 문서 하나를 새 파일로 바꾼다."""
    doc_cd: str
    file_name: str                      # 떨어진 폴더의 원래 파일명
    data: bytes
    header: Header
    load_id: str = ""
    source: str = ""                    # 지난 원문에 없는 새 문서일 때만: external/<팀>/law 등
    attachments: tuple[tuple[str, bytes], ...] = ()   # (별표 제목, HWP 바이트) — manifest 형식만


@dataclass
class Assembly:
    base_sha256: str
    out_sha256: str = ""
    members: int = 0
    replaced: list[dict] = field(default_factory=list)
    added: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generation_ids: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LazyZip(MutableMapping):
    """디스크의 ZIP을 멤버 이름 → 바이트로 다룬다. 읽을 때만 그 멤버를 풀고, 바꾼 것만 메모리에 둔다.
    원문 수천 개 ZIP을 통째로 메모리에 올리지 않기 위해서다."""

    def __init__(self, path, *, _shared=None, _over=None, _removed=None):
        self.path = Path(path)
        self.z = _shared or zipfile.ZipFile(self.path)
        if _shared is None:
            names = [e.filename for e in self.z.infolist() if not e.is_dir()]
            if len(names) != len(set(names)):
                raise CorpusError("ZIP 안에 같은 이름이 둘 이상")
            self.base = set(names)
        else:
            self.base = {e.filename for e in self.z.infolist() if not e.is_dir()}
        self.over = dict(_over or {})
        self.removed = set(_removed or ())

    def __getitem__(self, key):
        if key in self.over:
            return self.over[key]
        if key in self.base and key not in self.removed:
            return self.z.read(key)
        raise KeyError(key)

    def __setitem__(self, key, value):
        self.over[key] = value
        self.removed.discard(key)

    def __delitem__(self, key):
        if key not in self:
            raise KeyError(key)
        self.over.pop(key, None)
        if key in self.base:
            self.removed.add(key)

    def __contains__(self, key):
        return key in self.over or (key in self.base and key not in self.removed)

    def __iter__(self):
        return iter(sorted((self.base - self.removed) | set(self.over)))

    def __len__(self):
        return len((self.base - self.removed) | set(self.over))

    def copy(self):
        return LazyZip(self.path, _shared=self.z, _over=self.over, _removed=self.removed)

    def close(self):
        self.z.close()


def doc_name(file_name: str) -> str:
    stem = PurePosixPath(file_name).stem
    stem = _DATE_TAIL.sub("", stem).strip() or stem
    return _BODY_TAIL.sub("", stem).strip() or stem


def identify(file_name: str, data: bytes) -> str:
    """파일 → 문서코드. 법제처 본문 XML은 법령ID, 그 밖은 정식 문서명."""
    if PurePosixPath(file_name).suffix.lower() == ".xml" and data[:4000].lstrip().startswith(b"<"):
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            root = None
        if root is not None and root.tag == "법령":
            official = (root.findtext("기본정보/법령ID") or "").strip()
            if official:
                return f"LAW:{official}"
        if root is not None and root.tag == "AdmRulService":
            official = (root.findtext("행정규칙기본정보/행정규칙ID") or "").strip()
            if official:
                return f"ADMRUL:{official}"
    return name_code(doc_name(file_name))


def _split(name: str) -> tuple[str, str]:
    prefix = RAW_PREFIX if name.startswith(RAW_PREFIX) else ""
    return prefix, name[len(prefix):]


def _is_document(name: str) -> bool:
    rel = _split(name)[1]
    parts = PurePosixPath(rel).parts
    return (bool(parts) and parts[0] in SOURCES and not rel.endswith(".genos.json")
            and PurePosixPath(rel).suffix.lower() in DOCUMENTS)


def read_zip(path: Path) -> tuple[bytes, dict[str, bytes]]:
    raw = Path(path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [e.filename for e in z.infolist() if not e.is_dir()]
        if len(names) != len(set(names)):
            raise CorpusError("ZIP 안에 같은 이름이 둘 이상")
        files = {n: z.read(n) for n in names}
    prefixes = {_split(n)[0] for n in files}
    if len(prefixes) > 1:
        raise CorpusError("01_DATA/RAW/ 접두가 섞여 있음")
    return raw, files


def inventory(files: dict[str, bytes]) -> list[dict]:
    """원문 문서 목록: 멤버·sha·Gold 문서ID(sha 앞 16)·문서코드."""
    out = []
    for name in sorted(files):
        if _is_document(name):
            data = files[name]
            digest = sha256(data)
            out.append({"member": name, "sha256": digest, "doc_id": digest[:16],
                        "doc_cd": identify(PurePosixPath(name).name, data)})
    return out


def verify_base(files: dict[str, bytes], current_doc_ids: set[str]) -> dict:
    """지난 원문 ZIP이 지금 서빙 세대를 만든 원문인지 — 문서ID 집합이 같아야 한다."""
    ids = {row["doc_id"] for row in inventory(files)}
    missing, extra = sorted(current_doc_ids - ids), sorted(ids - current_doc_ids)
    return {"ok": not missing and not extra, "zip_documents": len(ids),
            "current_documents": len(current_doc_ids), "missing_in_zip": missing[:50],
            "not_in_current": extra[:50], "missing_count": len(missing), "extra_count": len(extra)}


def _manifest_doc_cd(item: dict) -> str:
    kind, official = str(item.get("kind") or ""), str(item.get("law_id") or "")
    if kind == "law" and official:
        return f"LAW:{official}"
    if kind == "admrul" and official:
        return f"ADMRUL:{official}"
    return ""


def _xml_extra(data: bytes) -> dict:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {}
    if root.tag == "법령":
        return {"doc_no": (root.findtext(".//법령일련번호") or "").strip(),
                "dept": (root.findtext(".//소관부처") or root.findtext(".//소관부처명") or "").strip()}
    return {"doc_no": (root.findtext(".//행정규칙일련번호") or "").strip(),
            "dept": (root.findtext(".//소관부처명") or "").strip()}


def assemble(base_zip: Path, out_zip: Path, replacements: list[Replacement], *, as_of: str) -> Assembly:
    raw, files = read_zip(base_zip)
    out_files, result = assemble_files(files, replacements, as_of=as_of, base_sha256=sha256(raw))
    data = write_zip(out_files)
    out_zip = Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_zip.with_suffix(out_zip.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(out_zip)
    result.out_sha256 = sha256(data)
    return result


def assemble_files(files: dict[str, bytes], replacements: list[Replacement], *, as_of: str,
                   base_sha256: str = "") -> tuple[dict[str, bytes], Assembly]:
    """조립 — 원본은 바꾸지 않는다 (LazyZip이면 바꾼 멤버만 메모리)."""
    files = files.copy() if isinstance(files, LazyZip) else dict(files)
    result = Assembly(base_sha256=base_sha256 or (file_sha256(files.path) if isinstance(files, LazyZip)
                                                   else sha256(write_zip(files))))
    if len({_split(n)[0] for n in files}) > 1:
        raise CorpusError("01_DATA/RAW/ 접두가 섞여 있음")
    if len({r.doc_cd for r in replacements}) != len(replacements):
        raise CorpusError("같은 문서의 교체가 둘 이상")
    prefix = next(iter({_split(n)[0] for n in files}), "")

    manifests: dict[str, dict] = {}                  # manifest 형식 출처 → manifest
    for name, data in files.items():
        parts = PurePosixPath(_split(name)[1]).parts
        if len(parts) == 2 and parts[0] in SOURCES and parts[0] != "internal" and parts[1] == "manifest.json":
            manifests[parts[0]] = json.loads(data.decode("utf-8"))
    tracked: dict[str, tuple[dict, str]] = {}        # manifest가 가리키는 본문 멤버 → (항목, 출처)
    for source, manifest in manifests.items():
        for item in manifest.get("items") or ():
            if _manifest_doc_cd(item) and item.get("body_file"):
                tracked[f"{prefix}{source}/{item['body_file']}"] = (item, source)

    by_doc: dict[str, list[str]] = {}
    for row in inventory(files):
        code = _manifest_doc_cd(tracked[row["member"]][0]) if row["member"] in tracked else row["doc_cd"]
        by_doc.setdefault(code, []).append(row["member"])

    for rep in sorted(replacements, key=lambda r: r.doc_cd):
        members = by_doc.get(rep.doc_cd, [])
        new_sha = sha256(rep.data)
        if members:
            for member in members:
                old_sha = sha256(files[member])
                if member in tracked:                 # manifest 형식: 같은 경로, 항목·별표 갱신
                    item, source = tracked[member]
                    for att in item.get("attachments") or ():
                        files.pop(f"{prefix}{source}/{att.get('file')}", None)
                    dropped = len(item.get("attachments") or ())
                    files[member] = rep.data
                    folder = PurePosixPath(item["body_file"]).parent
                    new_atts = []
                    for title, blob in rep.attachments:
                        rel = str(folder / "별표서식" / (re.sub(r'[\\/:*?"<>|]', "_", title)[:120] + ".hwp"))
                        files[f"{prefix}{source}/{rel}"] = blob
                        new_atts.append({"title": title, "role": "attachment", "file": rel,
                                         "sha256": sha256(blob), "size": len(blob)})
                    if dropped and not new_atts:
                        result.warnings.append(f"{rep.doc_cd}: 지난 판본 별표 파일 {dropped}개를 빼고 새 별표 파일 "
                                               f"없이 교체 (별표는 XML 별표내용만 남음)")
                    h = rep.header
                    item.update({"name": h.name, "label": h.name, "enforce": h.effective, "revised": h.promulgated,
                                 "promul_no": h.promulgation_no, "rev_kind": h.revision_kind,
                                 "body_sha256": new_sha, "body_format": "xml", "attachments": new_atts,
                                 "authority_mode": "increment-replacement", "authority_as_of": as_of,
                                 "increment_load_id": rep.load_id,
                                 **{k: v for k, v in _xml_extra(rep.data).items() if v}})
                    new_member = member
                elif PurePosixPath(member).suffix.lower() == ".xml" and rep.doc_cd.split(":")[0] in ("LAW", "ADMRUL"):
                    files[member] = rep.data           # 법제처 본문: 같은 경로에 새 본문
                    new_member = member
                else:                                  # 그 밖: 같은 폴더, 새 파일명
                    del files[member]
                    files.pop(member + ".genos.json", None)
                    new_member = str(PurePosixPath(member).parent / PurePosixPath(rep.file_name).name)
                    if new_member in files and new_member not in members:
                        raise CorpusError(f"{rep.doc_cd}: 새 파일 경로가 다른 파일과 겹침 {new_member}")
                    files[new_member] = rep.data
                result.replaced.append({"doc_cd": rep.doc_cd, "load_id": rep.load_id, "member": new_member,
                                        "old_member": member, "old_sha256": old_sha, "new_sha256": new_sha})
        else:                                         # 새 문서
            source = rep.source.strip("/")
            if not source or source.split("/")[0] not in SOURCES or len(source.split("/")) < 2:
                raise CorpusError(f"{rep.doc_cd}: 새 문서는 출처 경로(예: external/financial_team/law)가 필요")
            if rep.header.source_kind in ("LAW", "ADMRUL"):
                member = f"{prefix}{source}/{rep.header.name}/{rep.header.name} 본문.xml"
            else:
                member = f"{prefix}{source}/{PurePosixPath(rep.file_name).name}"
            if member in files:
                raise CorpusError(f"{rep.doc_cd}: 새 파일 경로가 다른 문서와 겹침 {member}")
            files[member] = rep.data
            result.added.append({"doc_cd": rep.doc_cd, "load_id": rep.load_id, "member": member,
                                 "new_sha256": new_sha})

    if manifests:
        from lawrag.core.legal_generation import GenerationError, build_contract
        for source, manifest in manifests.items():
            if any(i.get("kind") in ("law", "admrul") for i in manifest.get("items") or ()):
                try:
                    contract = build_contract(manifest, as_of=as_of)
                except GenerationError as exc:
                    raise CorpusError(f"{source}/manifest.json 세대 계약 실패: {exc}") from exc
                manifest.update({"authority_as_of": contract["as_of"], "generation_id": contract["generation_id"],
                                 "canonical_document_ids": contract["canonical_document_ids"],
                                 "increment_assembled_from": result.base_sha256})
                result.generation_ids[source] = contract["generation_id"]
            files[f"{prefix}{source}/manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")

    result.members = len(files)
    return files, result


def write_zip(files) -> bytes:
    """같은 입력이면 같은 바이트 (이름 순서·시각 고정)."""
    buffer = io.BytesIO()
    _write(buffer, files)
    return buffer.getvalue()


def write_zip_file(files, path) -> str:
    """큰 ZIP은 디스크에 바로 쓴다 (멤버를 하나씩 읽어 쓴다). sha256을 돌려준다."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        _write(f, files)
    tmp.replace(path)
    return file_sha256(path)


def _write(stream, files) -> None:
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, _FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[name])


