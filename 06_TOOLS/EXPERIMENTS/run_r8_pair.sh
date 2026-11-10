#!/bin/bash
# ADR-1481 then ADR-1482 (same frozen r8 code), one after the other.
/home/jin/8-AGENT/06_TOOLS/EXPERIMENTS/adr_1481/run_all.sh > $(ls -d /home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1481-*)/artifacts/run_all.log 2>&1
echo "1481 done $?"
/home/jin/8-AGENT/06_TOOLS/EXPERIMENTS/adr_1482/run_all.sh > $(ls -d /home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1482-*)/artifacts/run_all.log 2>&1
echo "1482 done $?"
