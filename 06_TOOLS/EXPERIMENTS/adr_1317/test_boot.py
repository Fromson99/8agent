"""Existing boot contracts bound to the same isolated code as workflow loading."""
import os
from pathlib import Path
import test_genos_compact_service_boot as original
original.ROOT = Path(os.environ['LOOP_TEST_CODE_ROOT'])
from test_genos_compact_service_boot import *
