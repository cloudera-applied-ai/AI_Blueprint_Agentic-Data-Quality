#!/usr/bin/env python3
"""Launch the Data Quality AI application.

Environment detection:
  Cloudera AI (CDSW_APP_PORT set or home is /home/cdsw):
    Backend:  127.0.0.1:8090
    Frontend: 127.0.0.1:{CDSW_APP_PORT}  (exposed by Cloudera)

  Standalone (everything else):
    Backend:  0.0.0.0:8000
    Frontend: 0.0.0.0:5173
"""

import os
import signal
import subprocess
import sys
import time

# __file__ is unavailable when Cloudera AI runs this in a Jupyter kernel;
# fall back to cwd which CAI sets to the project root.
try:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    ROOT_DIR = os.getcwd()
BACKEND_DIR = os.path.join(ROOT_DIR, "app", "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "app", "frontend")

IS_CLOUDERA = bool(os.environ.get("CDSW_APP_PORT")) or os.path.expanduser("~") == "/home/cdsw"

processes = []


def cleanup(signum=None, frame=None):
    """Terminate all child processes."""
    print("\nShutting down...")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if IS_CLOUDERA:
        backend_host = "127.0.0.1"
        backend_port = "8090"
        frontend_host = "127.0.0.1"
        frontend_port = os.environ.get("CDSW_APP_PORT", "8100")
        env_label = "Cloudera AI"
    else:
        backend_host = "0.0.0.0"
        backend_port = "8000"
        frontend_host = "0.0.0.0"
        frontend_port = "5173"
        env_label = "Standalone"

    print("=" * 60)
    print("  Data Quality AI - Application Launcher")
    print(f"  Environment: {env_label}")
    print("=" * 60)

    # Start backend
    print(f"\nStarting backend ({backend_host}:{backend_port})...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app",
         "--host", backend_host, "--port", backend_port, "--reload"],
        cwd=BACKEND_DIR,
    )
    processes.append(backend)

    # Give backend a moment to start
    time.sleep(1)

    # Start frontend — pass BACKEND_PORT so vite.config.ts proxies to the right place
    env = os.environ.copy()
    env["BACKEND_PORT"] = backend_port

    print(f"Starting frontend ({frontend_host}:{frontend_port})...")
    frontend = subprocess.Popen(
        ["npx", "vite", "--host", frontend_host, "--port", frontend_port],
        cwd=FRONTEND_DIR,
        env=env,
    )
    processes.append(frontend)

    print("\n" + "-" * 60)
    print(f"  Backend:  http://{backend_host}:{backend_port}")
    print(f"  Frontend: http://{frontend_host}:{frontend_port}")
    print(f"  API proxy: /api -> http://127.0.0.1:{backend_port}")
    print("  Press Ctrl+C to stop all services")
    print("-" * 60 + "\n")

    # Wait for either process to exit
    while True:
        for proc in processes:
            ret = proc.poll()
            if ret is not None:
                name = "Backend" if proc == backend else "Frontend"
                print(f"\n{name} exited with code {ret}")
                cleanup()
        time.sleep(1)


if __name__ == "__main__":
    main()
