"""Read the delivered predecessor's runtime for a diagnostic regression check."""
import os
from pathlib import Path
import semantic_runtime
import semantic_runtime.legal_agent
import lawrag.pipeline

root = Path(os.environ['BASELINE_SQL_TEST_CODE'])
semantic_runtime.__path__.insert(0, str(root / '02_BACKEND/semantic_runtime'))
semantic_runtime.legal_agent.__path__.insert(0, str(root / '02_BACKEND/semantic_runtime/legal_agent'))
lawrag.pipeline.__path__.insert(0, str(root / '02_BACKEND/lawrag/pipeline'))
