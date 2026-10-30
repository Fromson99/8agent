"""Dataset identity, composition, and environment-overlay helpers."""

from .catalog import (
    Artifact,
    DatasetContractError,
    DatasetPackage,
    DatasetRegistry,
    UnifiedCorpusView,
    compose_source_set,
    load_package,
    load_source_set,
    package_from_mapping,
)

__all__ = [
    "Artifact",
    "DatasetContractError",
    "DatasetPackage",
    "DatasetRegistry",
    "UnifiedCorpusView",
    "compose_source_set",
    "load_package",
    "load_source_set",
    "package_from_mapping",
]
