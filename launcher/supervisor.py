"""Multi-process supervisor orchestrating FastAPI Backend, Celery Worker, and Celery Beat."""

from __future__ import annotations

import logging
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import psutil

from launcher.config import get_app_root, load_env_dict

logger = logging.getLogger("Supervisor")


def is_port_in_use(host: str, port: int) -> bool:
    """Check if a TCP port is currently occupied."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def get_preferred_bind_port() -> int:
    """
    Determine preferred web port:
    Attempts standard HTTP Port 80 first (enabling zero-port URLs).
    If Port 80 is occupied or restricted, falls back to 8000.
    """
    env = load_env_dict()
    configured_port = env.get("PLATFORM_PORT") or env.get("PORT")
    if configured_port and configured_port.isdigit():
        return int(configured_port)

    # Check if standard port 80 is available
    if not is_port_in_use("127.0.0.1", 80):
        # Test binding to verify OS permission
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", 80))
                return 80
        except Exception:
            pass

    return 8000


def find_python_interpreter() -> str:
    """Locate Python executable across virtual environments or system."""
    root = get_app_root()
    candidates = [
        root / "backend" / ".venv" / "Scripts" / "python.exe",
        root / "backend" / ".venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            # Do not dereference symlinks with .resolve(), as virtual environment
            # binaries rely on their path within the venv to activate site-packages.
            return str(c.absolute())
    return sys.executable


class ProcessStreamReader(threading.Thread):
    """Pipes subprocess stdout or stderr into a thread-safe Queue with color tags."""

    def __init__(self, stream, tag: str, color: str, log_queue: queue.Queue):
        super().__init__(daemon=True)
        self.stream = stream
        self.tag = tag
        self.color = color
        self.log_queue = log_queue

    def run(self):
        try:
            for line in iter(self.stream.readline, b""):
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    self.log_queue.put((self.tag, self.color, text))
        except Exception:
            pass


class ProcessSupervisor:
    """Supervises and manages child processes for the platform."""

    def __init__(self, log_queue: queue.Queue, on_status_change: Optional[Callable[[], None]] = None):
        self.log_queue = log_queue
        self.on_status_change = on_status_change
        self.procs: List[subprocess.Popen] = []
        self._is_running = False
        self.port: int = 8000
        self.backend_ready = False
        self.worker_ready = False
        self.beat_ready = False

    def log(self, tag: str, text: str, color: str = "#38BDF8"):
        """Emit a formatted log message directly to the UI terminal queue."""
        self.log_queue.put((tag, color, text))

    def check_prerequisites(self) -> Tuple[bool, bool]:
        """Check availability of Redis (6379) and PostgreSQL (5432)."""
        redis_ok = is_port_in_use("127.0.0.1", 6379)
        postgres_ok = is_port_in_use("127.0.0.1", 5432)

        if redis_ok:
            self.log("PLATFORM", "Redis detected active on port 6379.", "#10B981")
        else:
            self.log("PLATFORM", "Notice: Redis is not detected on port 6379. Make sure Redis service or Docker is active.", "#F5A623")

        if postgres_ok:
            self.log("PLATFORM", "PostgreSQL detected active on port 5432.", "#10B981")
        else:
            self.log("PLATFORM", "Notice: PostgreSQL is not listening on port 5432. Verify database connection in Settings.", "#F5A623")

        return redis_ok, postgres_ok

    def start_all(self):
        """Launch FastAPI Backend, Celery Worker, and Celery Beat in background."""
        if self._is_running:
            return

        self._is_running = True
        self.port = get_preferred_bind_port()
        self.log("PLATFORM", f"Starting Algo Platform Engine on port {self.port} (0.0.0.0)...", "#38BDF8")

        self.check_prerequisites()

        root = get_app_root()
        backend_dir = root / "backend"
        is_frozen = getattr(sys, "frozen", False)
        python_exe = sys.executable if is_frozen else find_python_interpreter()

        env = os.environ.copy()
        env["PYTHONPATH"] = str(backend_dir)
        env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
        env["PYTHONUNBUFFERED"] = "1"

        # Propagate virtual environment PATH and VIRTUAL_ENV
        py_path = Path(python_exe)
        bin_dir = str(py_path.parent)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        venv_root = py_path.parent.parent
        if (venv_root / "pyvenv.cfg").is_file():
            env["VIRTUAL_ENV"] = str(venv_root)

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        # 1. Start FastAPI Backend Server
        if is_frozen:
            api_cmd = [sys.executable, "--service", "backend", "--port", str(self.port)]
        else:
            api_cmd = [
                python_exe, "-m", "uvicorn", "app.main:app",
                "--host", "0.0.0.0",
                "--port", str(self.port),
            ]

        self.log("PLATFORM", f"Spawning Backend API (Uvicorn on port {self.port})...", "#06B6D4")
        try:
            api_proc = subprocess.Popen(
                api_cmd, cwd=str(backend_dir), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
            self.procs.append(api_proc)
            ProcessStreamReader(api_proc.stdout, "BACKEND", "#06B6D4", self.log_queue).start()
            ProcessStreamReader(api_proc.stderr, "BACKEND", "#06B6D4", self.log_queue).start()
            self.backend_ready = True
        except Exception as e:
            self.log("ERROR", f"Failed to start Backend Server: {e}", "#EF4444")

        # 2. Start Celery Worker
        pool_type = "solo" if (sys.platform in ("darwin", "win32")) else "prefork"
        if is_frozen:
            worker_cmd = [sys.executable, "--service", "worker"]
        else:
            worker_cmd = [
                python_exe, "-m", "celery",
                "-A", "app.worker.celery_app",
                "worker", "--loglevel=info",
                "-P", pool_type,
            ]

        self.log("PLATFORM", "Spawning Celery Strategy Worker...", "#10B981")
        try:
            worker_proc = subprocess.Popen(
                worker_cmd, cwd=str(backend_dir), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
            self.procs.append(worker_proc)
            ProcessStreamReader(worker_proc.stdout, "WORKER ", "#10B981", self.log_queue).start()
            ProcessStreamReader(worker_proc.stderr, "WORKER ", "#10B981", self.log_queue).start()
            self.worker_ready = True
        except Exception as e:
            self.log("ERROR", f"Failed to start Celery Worker: {e}", "#EF4444")

        # 3. Start Celery Beat Scheduler
        if is_frozen:
            beat_cmd = [sys.executable, "--service", "beat"]
        else:
            beat_cmd = [
                python_exe, "-m", "celery",
                "-A", "app.worker.celery_app",
                "beat", "--loglevel=info",
            ]

        self.log("PLATFORM", "Spawning Celery Beat Scheduler...", "#D946EF")
        try:
            beat_proc = subprocess.Popen(
                beat_cmd, cwd=str(backend_dir), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
            self.procs.append(beat_proc)
            ProcessStreamReader(beat_proc.stdout, "BEAT   ", "#D946EF", self.log_queue).start()
            ProcessStreamReader(beat_proc.stderr, "BEAT   ", "#D946EF", self.log_queue).start()
            self.beat_ready = True
        except Exception as e:
            self.log("ERROR", f"Failed to start Celery Beat: {e}", "#EF4444")

        if self.on_status_change:
            self.on_status_change()

    def stop_all(self):
        """Recursively terminate all child processes and process trees."""
        self._is_running = False
        self.log("PLATFORM", "Stopping all platform processes...", "#F5A623")

        for proc in self.procs:
            try:
                if proc.poll() is None:
                    # Terminate process tree
                    parent = psutil.Process(proc.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.terminate()
                        except Exception:
                            pass
                    parent.terminate()
            except Exception:
                pass

        # Give 1 second for graceful shutdown
        time.sleep(0.8)

        # Force kill any lingering processes
        for proc in self.procs:
            try:
                if proc.poll() is None:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
                    else:
                        proc.kill()
            except Exception:
                pass

        self.procs.clear()
        self.backend_ready = False
        self.worker_ready = False
        self.beat_ready = False
        self.log("PLATFORM", "All platform services stopped cleanly.", "#94A3B8")

        if self.on_status_change:
            self.on_status_change()

    def restart_all(self):
        """Stop and restart all platform services."""
        self.log("PLATFORM", "Restarting services...", "#38BDF8")
        self.stop_all()
        time.sleep(1)
        self.start_all()

    @property
    def is_running(self) -> bool:
        return self._is_running and any(p.poll() is None for p in self.procs)
