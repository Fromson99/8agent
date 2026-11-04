import os
from pathlib import Path
import test_genos_sse_startup as startup
import test_genos_sse_transport as transport
startup.ROOT=transport.ROOT=Path(os.environ['LOOP_TEST_CODE_ROOT'])
from test_genos_sse_startup import *
from test_genos_sse_transport import *
