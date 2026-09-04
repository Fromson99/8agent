from pathlib import Path

import pytest

from lawrag.core.rag import experiment_catalog, experiments


def test_experiment_registry_covers_every_isolated_module():
    module_dir = Path(experiments.__file__).parent
    found = {path.stem for path in module_dir.glob("*.py")
             if path.name != "__init__.py"}
    registered = {row["key"] for row in experiments.specs()}

    assert found == registered
    assert all(row["module"].startswith("lawrag.core.rag.experiments.")
               for row in experiments.specs())


def test_catalog_exposes_all_saved_e2e_json_without_full_rows():
    payload = experiment_catalog.catalog()
    expected = len(list(experiment_catalog.EVAL_ROOT.glob("*.json")))

    assert payload["module_count"] == len(experiments.specs())
    assert payload["artifact_count"] == expected
    assert len(payload["artifacts"]) == expected
    assert payload["experiment_count"] > 0
    assert all("rows" not in row and "results" not in row
               for row in payload["artifacts"])


def test_artifact_detail_is_bounded_and_cannot_escape_eval_root():
    payload = experiment_catalog.catalog()
    artifact = next(row for row in payload["artifacts"]
                    if row["path"].endswith(".json"))
    detail = experiment_catalog.detail(artifact["path"])

    assert detail["artifact"]["path"] == artifact["path"]
    assert len(detail["rows_preview"]) <= 12
    with pytest.raises(FileNotFoundError):
        experiment_catalog.detail("data/review/cm_core_e2e_v1.json")
