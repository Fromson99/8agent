"""pytest plugin for ADR candidate arms: frozen snapshot modules first, production for the rest.

The frozen revision copies only the files it changes. Importing its `semantic_runtime`
package alone would hide every other production module (work_navigation, genos_backend, ...),
so the package search path is the frozen directory followed by the production directory.
"""
import os
import sys
from pathlib import Path

FROZEN = Path(os.environ['ADR_FROZEN_ROOT']).resolve()
PRODUCTION = Path(os.environ['ADR_PRODUCTION_ROOT']).resolve()
sys.path.insert(0, str(FROZEN))
import semantic_runtime  # noqa: E402

assert Path(semantic_runtime.__file__).resolve().is_relative_to(FROZEN), semantic_runtime.__file__
semantic_runtime.__path__.append(str(PRODUCTION / 'semantic_runtime'))
