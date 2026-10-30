"""Dataiku Streamlit entrypoint. Explicit demo switch; configured mode fails closed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ontology_dashboard import main

main()
