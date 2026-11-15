#!/usr/bin/env python3
"""
Algo Platform — Universal Standalone Application Runner
======================================================
Runs the complete trading platform from a single place without running
multiple terminal commands manually.

Orchestrates:
  1. FastAPI Backend Server (API, WebSockets, and static React UI on http://localhost:8000)
  2. Celery Worker (strategy engine, live Dhan feed, risk management)
  3. Celery Beat (watchdogs, token renewal, periodic schedulers)
  (Optional) Vite Dev Server if --dev flag is passed.

Usage:
  python run.py             # Normal standalone mode (FastAPI serves built React UI)
  python run.py --dev       # Development mode (also runs Vite dev server on port 5173)
  python run.py --port 8080 # Run on custom port
"""

import os
import sys
import time
import socket
import signal
import subprocess
import threading
import webbrowser
import argparse

# ── Color Utilities ────────────────────────────────────────────────────────────
class Colors:
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE    = "\033[94m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RESET   = "\033[0m"

def log_launcher(msg: str, color=Colors.BLUE):
    print(f"{color}{Colors.BOLD}[PLATFORM]{Colors.RESET} {msg}")

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT_DIR     = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR  = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
DIST_DIR     = os.path.join(FRONTEND_DIR, "dist")

def find_python_executable():
    """Locate Python executable in virtual environments or system."""
    candidates = [
        os.path.join(BACKEND_DIR, ".venv", "bin", "python"),
        os.path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe"),
        os.path.join(ROOT_DIR, ".venv", "bin", "python"),
        os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe"),
        sys.executable,
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return sys.executable

def is_port_in_use(host: str, port: int) -> bool:
    """Check if a port is listening on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.8)
        return s.connect_ex((host, port)) == 0

def ensure_services():
    """Verify or auto-start required background services (Redis & Postgres)."""
    # Check Redis
    if not is_port_in_use("127.0.0.1", 6379):
        log_launcher("Redis is not running on port 6379. Attempting to start local Redis...", Colors.YELLOW)
        started = False
        # Try brew redis on macOS
        if sys.platform == "darwin":
            try:
                subprocess.run(["brew", "services", "start", "redis"], capture_output=True)
                time.sleep(1.5)
                started = is_port_in_use("127.0.0.1", 6379)
            except Exception:
                pass
            if not started:
                for brew_redis in ["/opt/homebrew/bin/redis-server", "/usr/local/bin/redis-server", "redis-server"]:
                    try:
                        subprocess.run([brew_redis, "--daemonize", "yes"], capture_output=True)
                        time.sleep(1)
                        if is_port_in_use("127.0.0.1", 6379):
                            started = True
                            break
                    except Exception:
                        pass
        elif sys.platform.startswith("linux"):
            try:
                subprocess.run(["redis-server", "--daemonize", "yes"], capture_output=True)
                time.sleep(1)
                started = is_port_in_use("127.0.0.1", 6379)
            except Exception:
                pass

        if started:
            log_launcher("Redis started successfully.", Colors.GREEN)
        else:
            log_launcher("Warning: Redis is still not detected on port 6379. Make sure Redis or Docker is running.", Colors.YELLOW)
    else:
        log_launcher("Redis is active on port 6379.", Colors.GREEN)

    # Check PostgreSQL
    if not is_port_in_use("127.0.0.1", 5432):
        log_launcher("Notice: PostgreSQL is not listening on localhost:5432.", Colors.YELLOW)
        if sys.platform == "darwin":
            try:
                subprocess.run(["brew", "services", "start", "postgresql@16"], capture_output=True)
                time.sleep(2)
            except Exception:
                pass
        if not is_port_in_use("127.0.0.1", 5432):
            log_launcher("If using remote or Docker Postgres, ensure connectivity.", Colors.YELLOW)
    else:
        log_launcher("PostgreSQL is active on port 5432.", Colors.GREEN)

    # Check Outgoing Public IPv4 for Dhan SEBI Static IP Setup
    try:
        import urllib.request
        import json
        req = urllib.request.Request("https://api.ipify.org?format=json", headers={"User-Agent": "algo-platform"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            ip = data.get("ip")
            if ip:
                log_launcher(f"Outgoing Public IPv4: {ip} (Verify this matches Dhan Portal IP Setup)", Colors.CYAN)
    except Exception:
        pass

def ensure_frontend_built():
    """Ensure frontend/dist is built for standalone serving."""
    index_html = os.path.join(DIST_DIR, "index.html")
    if not os.path.exists(index_html):
        log_launcher("Frontend build not found. Building production UI bundle once...", Colors.CYAN)
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        res = subprocess.run([npm_cmd, "run", "build"], cwd=FRONTEND_DIR)
        if res.returncode == 0:
            log_launcher("Frontend built successfully.", Colors.GREEN)
        else:
            log_launcher("Warning: npm build failed. Standalone frontend may not be available.", Colors.RED)

# ── Process Stream Logger ──────────────────────────────────────────────────────
class ProcessLogger(threading.Thread):
    def __init__(self, stream, tag: str, color: str):
        super().__init__(daemon=True)
        self.stream = stream
        self.tag = tag
        self.color = color

    def run(self):
        try:
            for line in iter(self.stream.readline, b""):
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    print(f"{self.color}{Colors.BOLD}[{self.tag}]{Colors.RESET} {text}")
        except Exception:
            pass

# ── Supervisor ─────────────────────────────────────────────────────────────────
class ProcessSupervisor:
    def __init__(self, python_exe: str, port: int, dev_mode: bool, open_browser: bool = False):
        self.python_exe   = python_exe
        self.port         = port
        self.dev_mode     = dev_mode
        self.open_browser = open_browser
        self.procs: list[subprocess.Popen] = []
        self._running     = True

    def start(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = BACKEND_DIR
        env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

        # 1. Start FastAPI Backend Server
        log_launcher(f"Starting Backend API & Web Server on port {self.port}...", Colors.CYAN)
        api_cmd = [
            self.python_exe, "-m", "uvicorn", "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(self.port),
        ]
        if self.dev_mode:
            api_cmd.append("--reload")

        api_proc = subprocess.Popen(
            api_cmd, cwd=BACKEND_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.procs.append(api_proc)
        ProcessLogger(api_proc.stdout, "BACKEND", Colors.CYAN).start()
        ProcessLogger(api_proc.stderr, "BACKEND", Colors.CYAN).start()

        # 2. Start Celery Worker
        log_launcher("Starting Celery Strategy Worker...", Colors.GREEN)
        pool_type = "solo" if (sys.platform in ("darwin", "win32")) else "prefork"
        worker_cmd = [
            self.python_exe, "-m", "celery",
            "-A", "app.worker.celery_app",
            "worker", "--loglevel=info",
            "-P", pool_type,
        ]
        worker_proc = subprocess.Popen(
            worker_cmd, cwd=BACKEND_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.procs.append(worker_proc)
        ProcessLogger(worker_proc.stdout, "WORKER ", Colors.GREEN).start()
        ProcessLogger(worker_proc.stderr, "WORKER ", Colors.GREEN).start()

        # 3. Start Celery Beat Scheduler
        log_launcher("Starting Celery Beat Scheduler...", Colors.MAGENTA)
        beat_cmd = [
            self.python_exe, "-m", "celery",
            "-A", "app.worker.celery_app",
            "beat", "--loglevel=info",
        ]
        beat_proc = subprocess.Popen(
            beat_cmd, cwd=BACKEND_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.procs.append(beat_proc)
        ProcessLogger(beat_proc.stdout, "BEAT   ", Colors.MAGENTA).start()
        ProcessLogger(beat_proc.stderr, "BEAT   ", Colors.MAGENTA).start()

        # 4. Optional Vite Dev Server if --dev passed
        if self.dev_mode:
            log_launcher("Starting Frontend Vite Dev Server (port 5173)...", Colors.YELLOW)
            npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
            dev_proc = subprocess.Popen(
                [npm_cmd, "run", "dev"], cwd=FRONTEND_DIR, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            self.procs.append(dev_proc)
            ProcessLogger(dev_proc.stdout, "VITE   ", Colors.YELLOW).start()
            ProcessLogger(dev_proc.stderr, "VITE   ", Colors.YELLOW).start()

        # Monitor startup and display access URLs
        threading.Thread(target=self._wait_for_startup, daemon=True).start()

        # Main supervision loop
        try:
            while self._running:
                for p in self.procs:
                    ret = p.poll()
                    if ret is not None and self._running:
                        log_launcher(f"Process PID {p.pid} exited unexpectedly with code {ret}", Colors.RED)
                time.sleep(1)
        except KeyboardInterrupt:
            self.shutdown()

    def _wait_for_startup(self):
        target_url = f"http://localhost:{self.port}"
        health_url = f"{target_url}/api/health"
        log_launcher(f"Waiting for services to become healthy at {health_url}...", Colors.BLUE)

        for _ in range(50):
            if is_port_in_use("localhost", self.port):
                time.sleep(1.0)
                print("\n" + "=" * 64)
                print(f" {Colors.GREEN}{Colors.BOLD}[ONLINE] Algo Platform is live and running!{Colors.RESET}")
                print(f" Web UI:      {Colors.CYAN}{Colors.BOLD}{target_url}{Colors.RESET}")
                print(f" API Health:  {Colors.DIM}{health_url}{Colors.RESET}")
                if self.dev_mode:
                    print(f" Vite Dev UI: {Colors.YELLOW}http://localhost:5173{Colors.RESET}")
                print(" Press Ctrl+C at any time to cleanly stop all services.")
                print("=" * 64 + "\n")
                if self.open_browser:
                    try:
                        webbrowser.open(target_url)
                    except Exception:
                        pass
                return
            time.sleep(0.5)

    def shutdown(self):
        if not self._running:
            return
        self._running = False
        print("\n")
        log_launcher("Stopping all platform services cleanly...", Colors.YELLOW)
        for p in self.procs:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        # Wait up to 3 seconds for graceful exit
        time.sleep(1.5)
        for p in self.procs:
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass
        log_launcher("All processes stopped. Goodbye!", Colors.GREEN)
        sys.exit(0)

# ── Entry Point ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Algo Platform Standalone Runner")
    parser.add_argument("--port", type=int, default=8000, help="Web server port (default: 8000)")
    parser.add_argument("--dev", action="store_true", help="Run with live Vite frontend hot-reloading")
    parser.add_argument("--open-browser", action="store_true", default=False, help="Automatically open web browser on startup (default: False)")
    args = parser.parse_args()

    print(f"""
{Colors.CYAN}{Colors.BOLD}=============================================================
         ALGO TRADING PLATFORM — UNIVERSAL RUNNER            
============================================================={Colors.RESET}
""")

    py_exe = find_python_executable()
    log_launcher(f"Using Python: {py_exe}")

    # Ensure background services
    ensure_services()

    # Ensure frontend build exists
    if not args.dev:
        ensure_frontend_built()

    supervisor = ProcessSupervisor(
        python_exe=py_exe,
        port=args.port,
        dev_mode=args.dev,
        open_browser=args.open_browser,
    )

    def sig_handler(sig, frame):
        supervisor.shutdown()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    supervisor.start()

if __name__ == "__main__":
    main()
