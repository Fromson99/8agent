from pathlib import Path

from lawrag.platform.active_data import active_runtime_paths, active_structure_path


ROOT = Path(__file__).resolve().parents[3]


def test_active_data_paths_are_release_bound() -> None:
    paths = active_runtime_paths(ROOT)
    structure = active_structure_path(ROOT)

    assert structure == paths["STRUCTURE_STORE"]
    assert structure.is_dir()
    assert "01_DATA/ACTIVE/local/RUNTIMES/" in structure.as_posix()
    assert not structure.is_symlink()
    assert not any(
        (ROOT / "01_DATA" / name).exists()
        for name in ("corpus", "structure", "frames", "rag")
    )
