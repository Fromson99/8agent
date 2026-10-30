from pathlib import Path
import sys
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE/'payload/02_BACKEND'),str(HERE/'payload'),'/tmp/a8-vector-sdk/dataiku_api_client-15.2.0']
