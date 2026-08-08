from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--reload", "--port", "8765"],
            cwd=root,
        ),
        subprocess.Popen(["npm", "run", "dev:frontend"], cwd=root),
    ]

    def stop(*_: object) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        return max(process.wait() for process in processes)
    finally:
        stop()


if __name__ == "__main__":
    raise SystemExit(main())
