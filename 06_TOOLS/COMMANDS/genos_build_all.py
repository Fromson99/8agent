#!/usr/bin/env python3
"""Compatibility command name for the maintained term/source data stages."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from genos_data_stages import main
if __name__=='__main__':raise SystemExit(main())
