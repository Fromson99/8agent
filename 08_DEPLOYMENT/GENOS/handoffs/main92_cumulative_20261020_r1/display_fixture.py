"""Point legacy display fixtures at the same frozen code being verified."""
import os
from pathlib import Path


def pytest_configure(config):
    import test_rag_flow_svg
    test_rag_flow_svg.ROOT = Path(os.environ["TASK_TEST_CODE_ROOT"])
