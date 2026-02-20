from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backend and frontend dev servers together.")
    parser.add_argument("--backend-host", default="127.0.0.1", help="Backend host (default: 127.0.0.1)")
    parser.add_argument("--backend-port", default="8000", help="Backend port (default: 8000)")
    parser.add_argument("--frontend-port", default="5173", help="Frontend port (default: 5173)")
    parser.add_argument("--no-reload", action="store_true", help="Disable backend auto-reload")
    return parser.parse_args()


def start_processes(args: argparse.Namespace, root: Path) -> list[subprocess.Popen]:
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        args.backend_host,
        "--port",
        args.backend_port,
    ]
    if not args.no_reload:
        backend_cmd.append("--reload")

    npm_exe = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm_exe:
        raise FileNotFoundError(
            "npm executable was not found in PATH. Install Node.js and ensure npm is available."
        )

    frontend_cmd = [npm_exe, "run", "dev", "--", "--port", args.frontend_port]
    frontend_env = os.environ.copy()
    frontend_env.setdefault("VITE_API_ROOT", f"http://{args.backend_host}:{args.backend_port}")

    backend = subprocess.Popen(backend_cmd, cwd=root)
    try:
        frontend = subprocess.Popen(frontend_cmd, cwd=root / "frontend", env=frontend_env)
    except Exception:
        if backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except Exception:
                backend.kill()
        raise
    return [backend, frontend]


def stop_processes(processes: list[subprocess.Popen]) -> None:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()

    deadline = time.time() + 5
    while time.time() < deadline:
        if all(proc.poll() is not None for proc in processes):
            return
        time.sleep(0.1)

    for proc in processes:
        if proc.poll() is None:
            proc.kill()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent
    try:
        processes = start_processes(args, root)
    except FileNotFoundError as exc:
        print(f"[dev] {exc}")
        return 1

    print(f"[dev] Backend: http://{args.backend_host}:{args.backend_port}")
    print(f"[dev] Frontend: http://127.0.0.1:{args.frontend_port}")
    print("[dev] Press Ctrl+C to stop both.")

    try:
        while True:
            for proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f"[dev] Process exited with code {code}. Shutting down all.")
                    stop_processes(processes)
                    return code
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[dev] Stopping...")
        stop_processes(processes)
        return 0


if __name__ == "__main__":
    if os.name == "nt":
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    raise SystemExit(main())
