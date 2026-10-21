"""MAIN92 code-only gate; keep legacy corpus bytes outside its code inventory."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

SPEC_PIN = "b340cff395a775a350c59569b86eec2f4946fd9d8868e91e9656c7c22e17e19c"
RUNNER_PIN = "7ec8917f064e8bb153f80cd0096437ab2512e04e28051bd5330873a2169a0b99"
INVENTORY_PIN = "b911e3106e3d3db4a72e24b21bd73a46c302f863a36e593dbe50b20762216a8f"
EXCLUDED_DATA = {
    "02_BACKEND/lawrag/agents/agent6/corpus/manifest.json": "e09936dd0c4388e04fe9ff63d07b2f30cbec4202a99bb163aff9898fe746bf44",
    "02_BACKEND/lawrag/agents/agent6/corpus/raw/KOFIA-R.meta.yaml": "190fbb50d3b45e8cbdd9645bde8f13fab9eab2baa860e66b0c30b221011da951",
    "02_BACKEND/lawrag/agents/agent6/corpus/raw/KSB-D-2021.meta.yaml": "18e42559a1fe6eedd2c8f76930681ea4a30362c646d6e3873c0df030a95b7338",
    "02_BACKEND/lawrag/agents/agent6/corpus/raw/KSB.meta.yaml": "c7782cb82f5d5c5837d7d0a61d3fb620315f95cf34272cabeacdc6b15c0019e6",
    "02_BACKEND/lawrag/agents/agent6/corpus/structured/KOFIA-R.doc.json": "b8127ad0f83490e7b5ad88379507d3e847c74339522f5fe0e4dc2aa14751a38e",
    "02_BACKEND/lawrag/agents/agent6/corpus/structured/KSB.doc.json": "b5357853a99b5debbd6abd22603ed36cb0eb25d10eb6e538692377261115dd09",
}


def pin(path, digest):
    path = Path(path)
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("심볼릭 링크 경로: " + str(path))
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("반입 파일 해시 불일치: " + path.name)
    return raw


def main():
    root = Path(os.environ["GENOS_NEXT_CODE_ROOT"]).resolve(strict=True)
    package = Path(os.environ["GENOS_NEXT_PACKAGE"]).resolve(strict=True)
    spec = json.loads(pin(package / "PATCH_SPEC.json", SPEC_PIN))
    pin(package / "apply_ignore.py", RUNNER_PIN)
    for name, digest in spec["payload_hashes"].items():
        pin(package / name, digest)
    loader = importlib.util.spec_from_file_location("sealed_ignore_helpers", package / "apply_ignore.py")
    helper = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(helper)
    git = lambda *args: helper.git(root, *args)
    if Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        raise ValueError("확인한 Git 루트와 실행 대상이 다릅니다")
    state = json.loads(helper.plain(package / "STATE.json").read_bytes())
    if state["root"] != str(root) or state["spec_sha256"] != SPEC_PIN or state["phase"] != "APPLIED":
        raise ValueError("적용 상태·코드 루트가 일치하지 않습니다")
    if ".gitignore" not in state["files"]:
        raise ValueError("적용된 .gitignore 기록이 없습니다")
    for name, row in state["files"].items():
        if name not in spec["profiles"]:
            raise ValueError("알 수 없는 ignore 적용 경로")
        for side in ("before", "after"):
            if helper.sha(base64.b64decode(row[side], validate=True)) != row[side + "_sha256"]:
                raise ValueError("ignore 백업 기록이 손상됐습니다")
        pin(root / name, row["after_sha256"])
        helper.validate_rules((root / name).read_bytes(), spec)
    tracked = {p for p in git("ls-files", "-z").decode().split("\0") if p}
    bad = sorted(p for p in tracked if helper.forbidden(p))
    if bad:
        raise ValueError("Git에 남은 휴지통/이관 파일 " + str(len(bad)) + "개: " + ", ".join(bad[:3]))
    if git("status", "--porcelain=v1", "--untracked-files=no").strip():
        raise ValueError("아직 커밋되지 않은 변경이 있습니다")
    inventory = json.loads(pin(package / "MAIN92_BASE_INVENTORY.json", INVENTORY_PIN))
    expected = {row["path"]: row["sha256"] for row in inventory["files"]}
    if len(expected) != 1306:
        raise ValueError("기준 코드 목록이 달라졌습니다")
    for name, digest in EXCLUDED_DATA.items():
        if expected.pop(name, None) != digest:
            raise ValueError("검토한 과거 데이터 목록과 다릅니다")
    for row in inventory["required_files"]:
        if row["path"] in EXCLUDED_DATA:
            raise ValueError("필수 코드 의존성을 데이터로 제외할 수 없습니다")
        expected[row["path"]] = row["sha256"]
    expected.update({name: row["after_sha256"] for name, row in state["files"].items()})
    config = helper.plain(root / helper.CONFIG)
    actual_config = helper.sha(config.read_bytes()) if config.exists() else None
    if actual_config != state["config_sha256"]:
        raise ValueError("현장 데이터/서빙 설정이 적용 시점과 다릅니다")
    if actual_config is not None:
        expected[helper.CONFIG] = actual_config
    mismatches = []
    for name, digest in expected.items():
        path = helper.plain(root / name)
        if name not in tracked or not path.is_file() or helper.sha(path.read_bytes()) != digest:
            mismatches.append(name)
    if mismatches:
        raise ValueError("필수 코드 불일치 " + str(len(mismatches)) + "개: " + ", ".join(mismatches[:5]))
    result = {
        "status": "MAIN92_CODE_ONLY_GATE_R2_PASS",
        "commit": git("rev-parse", "HEAD").decode().strip(),
        "base_code_zip_sha256": inventory["base_code_zip_sha256"],
        "parent_inventory_sha256": INVENTORY_PIN,
        "corrected_base_code_files": 1300,
        "verified_code_and_field_bindings": len(expected),
        "excluded_legacy_data": EXCLUDED_DATA,
        "data_files_changed": False,
        "history_and_remote": "CHECKED_BY_FOLLOWING_PUSH_STEPS",
        "genos_revision_and_model": "NOT_CHECKED",
    }
    helper.json_write(Path(os.environ["GENOS_NEXT_GATE_RECORD"]), result)
    print("코드 검증 통과: MAIN92 코드·의존성·현장 설정·ignore 일치. 원격 확인 후 일반 push를 진행합니다.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("코드 검증 중단: " + str(exc), file=sys.stderr)
        sys.exit(1)
