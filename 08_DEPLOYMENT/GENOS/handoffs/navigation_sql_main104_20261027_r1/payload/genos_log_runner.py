"""Run any deployment/build/server command with original stdout/stderr on NFS."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import traceback

from genos_diagnostics import Session, transfer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="command")
    parser.add_argument("--recover", type=Path, help="Retry retained spool directory; do not rerun its command")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.recover:
        transfer(args.recover)
        while list(args.recover.glob("*.stream/*.pending")):
            transfer(args.recover)
        print("GENOS_SYSTEM_LOG_RECOVERED", args.recover, flush=True)
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("A command is required after --")
    session = Session(args.phase)
    print("GENOS_SYSTEM_LOG_RUN", session.run_id, "NFS", session.target, "SPOOL", session.spool, flush=True)
    session.event("command.started", phase=args.phase, executable=command[0], argument_count=len(command) - 1)
    result = 127
    previous_signals = {}
    threads = []
    try:
        # Keep caller stdin, cwd and exit status. Children share a correlation ID,
        # while separate per-process output files prevent cross-worker corruption.
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, env={**os.environ, "PYTHONUNBUFFERED": "1",
                                        "GENOS_LOG_CAPTURED": "1", "GENOS_LOG_RUN_ID": session.run_id})
        def forward(sig, frame):
            session.event("command.signal", signal=sig)
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                pass
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous_signals[sig] = signal.signal(sig, forward)
        def capture(pipe, name, fd):
            try:
                while True:
                    raw = os.read(pipe.fileno(), 65536)
                    if not raw:
                        break
                    session.write(name, raw)
                    try:
                        remaining = memoryview(raw)
                        while remaining:
                            size = os.write(fd, remaining)
                            remaining = remaining[size:]
                    except OSError:
                        pass  # Closing a console must not destroy retained logs.
            finally:
                pipe.close()
        for pipe, name, fd in ((child.stdout, "stdout.log", 1), (child.stderr, "stderr.log", 2)):
            thread = threading.Thread(target=capture, args=(pipe, name, fd), daemon=True)
            thread.start()
            threads.append(thread)
        code = child.wait()
        result = code if code >= 0 else 128 - code
        for thread in threads:
            thread.join(timeout=3)
        if any(thread.is_alive() for thread in threads):
            session.event("command.output.still_open", reason="descendant still owns stdout/stderr")
    except Exception:
        raw = traceback.format_exc()
        session.write("stderr.log", raw.encode("utf-8"))
        print(raw, file=sys.stderr, end="", flush=True)
        session.event("command.launch.failed")
    finally:
        for sig, previous in previous_signals.items():
            signal.signal(sig, previous)
        session.event("command.finished", exit_code=result)
        session.write("result.json", ("{\"exit_code\":" + str(result) + "}\n").encode())
        complete = session.close()
        print("GENOS_SYSTEM_LOG_RESULT", result, "NFS_COMPLETE", complete,
              "PENDING", session.pending(), "SPOOL", session.spool, flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
