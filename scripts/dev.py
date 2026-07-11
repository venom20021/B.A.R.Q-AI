"""
BARQ Development Startup Script

Starts both the Electron app and Python sidecar for development.
"""

import os
import sys
import subprocess
import signal
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def main():
    """Start both Electron and Python sidecar."""
    print("=" * 50)
    print("  BARQ - Development Mode")
    print("=" * 50)

    processes = []

    try:
        # Start Python sidecar
        print("\n[1/2] Starting Python sidecar...")
        python_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--host", "127.0.0.1", "--port", "8970"],
            cwd=PROJECT_ROOT / "python",
            env={**os.environ, "BARQ_DEBUG": "true"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(python_process)
        time.sleep(2)  # Wait for Python to start

        # Start Electron
        print("\n[2/2] Starting Electron app...")
        electron_process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=PROJECT_ROOT,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(electron_process)

        print("\n✅ Both services started!")
        print("   Electron: http://localhost:5173")
        print("   Python API: http://127.0.0.1:8970")
        print("   Python Docs: http://127.0.0.1:8970/docs")
        print("\nPress Ctrl+C to stop both services.\n")

        # Wait for any process to finish
        for proc in processes:
            proc.wait()

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    print("Done.")


if __name__ == "__main__":
    main()
