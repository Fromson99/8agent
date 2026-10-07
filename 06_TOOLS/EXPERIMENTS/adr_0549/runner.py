"""Explicit research entrypoint for the pinned, offline GENOS handoff runner."""
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.platform.workspace import load_layout
PACKAGE=load_layout(ROOT).path('deployment')/'GENOS/patches/fulltext_location_20260929_r1'
sys.path.insert(0,str(PACKAGE))
runpy.run_path(str(PACKAGE/'benchmark.py'),run_name='__main__')
