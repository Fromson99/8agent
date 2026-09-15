#!/usr/bin/env python3
"""Latest semantic LOAD / release management; no legacy code bootstrap."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'02_BACKEND'))
from semantic_runtime.control import main
if __name__=='__main__':main()
