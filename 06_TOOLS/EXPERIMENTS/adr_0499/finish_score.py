"""Score once after the separate five-case product batch finishes."""
import subprocess,time,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0499-qwen-interrupted-five-retry'
while not (A/'artifacts/run-001/results.json').exists():time.sleep(3)
raise SystemExit(subprocess.call([sys.executable,str(Path(__file__).with_name('score.py'))],cwd=R))
