"""Local non-Docker runner for development and demos.

The project was adapted to run on machines that cannot use Docker. This script
keeps the daily command small while still making every external dependency
explicit: PostgreSQL must exist, Redis/Chroma/FastAPI can be started here.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
POSTGRES_APP_BIN = Path("/Applications/Postgres.app/Contents/Versions/17/bin")


def run(command: List[str], check: bool = True) -> subprocess.CompletedProcess:
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=str(ROOT), check=check)


def resolve_command(command: str) -> Optional[str]:
    # Search order is intentionally local-friendly: PATH first, Postgres.app for
    # macOS database tools, then the project-local .local/bin utilities.
    found = shutil.which(command)
    if found:
        return found
    postgres_app_command = POSTGRES_APP_BIN / command
    if postgres_app_command.exists():
        return str(postgres_app_command)
    local_command = ROOT / ".local" / "bin" / command
    if local_command.exists():
        return str(local_command)
    return None


def ensure_python_version() -> None:
    version = sys.version_info
    if version < (3, 9):
        raise SystemExit("Python 3.9+ is required. This machine should use Python 3.9.6.")
    print(f"Python OK: {version.major}.{version.minor}.{version.micro}")


def ensure_env_file() -> None:
    if ENV_FILE.exists():
        return
    if not ENV_EXAMPLE.exists():
        raise SystemExit(".env.example was not found.")
    ENV_FILE.write_text(ENV_EXAMPLE.read_text())
    print("Created .env from .env.example")


def ensure_postgres_app() -> None:
    # PostgreSQL is not started by this script on every platform. On macOS we
    # can nudge Postgres.app open; on Windows the README documents manual setup.
    if is_port_open("localhost", 5433):
        print("PostgreSQL OK on localhost:5433")
        return
    if POSTGRES_APP_BIN.exists():
        run(["open", "-a", "Postgres"], check=False)
        time.sleep(3)
    if not is_port_open("localhost", 5433):
        print("PostgreSQL is not listening on localhost:5433. Open Postgres.app and retry.")


def is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def start_redis_if_needed(processes: List[subprocess.Popen]) -> None:
    if is_port_open("localhost", 6379):
        print("Redis OK on localhost:6379")
        return
    redis_server = resolve_command("redis-server")
    if not redis_server:
        raise SystemExit("redis-server was not found. Expected .local/bin/redis-server.")
    redis_dir = ROOT / ".local" / "redis"
    redis_dir.mkdir(parents=True, exist_ok=True)
    processes.append(
        start_process(
            [
                redis_server,
                "--bind",
                "127.0.0.1",
                "--port",
                "6379",
                "--dir",
                str(redis_dir),
                "--appendonly",
                "no",
                "--save",
                "",
            ]
        )
    )
    time.sleep(1)


def create_database() -> None:
    # The database name is derived from DATABASE_URL so local credentials can
    # change without editing this script.
    createdb = resolve_command("createdb")
    if not createdb:
        print("createdb was not found. Open or install Postgres.app.")
        return
    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://wen@localhost:5433/asadero_mc")
    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    database_name = parsed.path.lstrip("/") or "asadero_mc"
    command = [createdb]
    if parsed.hostname:
        command += ["-h", parsed.hostname]
    if parsed.port:
        command += ["-p", str(parsed.port)]
    if parsed.username:
        command += ["-U", parsed.username]
    command.append(database_name)
    run(command, check=False)


def migrate_and_seed() -> None:
    run([sys.executable, "-m", "scripts.migrate"])
    run([sys.executable, "-m", "scripts.seed"])


def chroma_command() -> List[str]:
    local_chroma = ROOT / ".venv" / "bin" / "chroma"
    if local_chroma.exists():
        return [str(local_chroma)]
    chroma = shutil.which("chroma")
    if chroma:
        return [chroma]
    raise SystemExit("ChromaDB CLI was not found. Run: pip install -e \".[dev]\"")


def start_process(command: List[str]) -> subprocess.Popen:
    print("$ " + " ".join(command), flush=True)
    env = os.environ.copy()
    # Redis on macOS can fail under localized locales; forcing C keeps startup
    # deterministic without changing the user's shell configuration.
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return subprocess.Popen(command, cwd=str(ROOT), env=env)


def maybe_start_chroma(processes: List[subprocess.Popen]) -> None:
    # Reuse an existing Chroma process when the port is already open. This avoids
    # the common "address already in use" loop during bot testing.
    if is_port_open("localhost", 8001):
        print("ChromaDB OK on localhost:8001")
        return
    processes.append(
        start_process(
            chroma_command()
            + ["run", "--host", "localhost", "--port", "8001", "--path", "./.chroma"]
        )
    )
    time.sleep(2)


def maybe_start_api(processes: List[subprocess.Popen]) -> None:
    # Same reuse behavior for FastAPI: if uvicorn is already running, the script
    # becomes a watcher/status command instead of crashing.
    if is_port_open("localhost", 8000):
        print("FastAPI OK on localhost:8000")
        return
    processes.append(
        start_process(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--reload",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ]
        )
    )


def terminate(processes: List[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()


def run_stack(skip_services: bool, skip_db_init: bool) -> None:
    ensure_python_version()
    ensure_env_file()

    if not skip_services:
        ensure_postgres_app()

    processes: List[subprocess.Popen] = []
    start_redis_if_needed(processes)

    if not skip_db_init:
        create_database()
        migrate_and_seed()

    maybe_start_chroma(processes)
    maybe_start_api(processes)

    print("")
    print("API:     http://localhost:8000")
    print("Swagger: http://localhost:8000/docs")
    print("Health:  http://localhost:8000/health")
    print("")
    if processes:
        print("Press Ctrl+C to stop services started by this command.")
    else:
        print("All services were already running. Press Ctrl+C to exit this watcher.")

    try:
        while not processes or all(process.poll() is None for process in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping local stack...")
    finally:
        terminate(processes)

    failed: Optional[int] = next(
        (
            process.returncode
            for process in processes
            if process.returncode and process.returncode not in (-signal.SIGTERM, -signal.SIGINT)
        ),
        None,
    )
    if failed:
        raise SystemExit(f"Local stack stopped with exit code {failed}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ASADERO MC locally without Docker.")
    parser.add_argument("--skip-services", action="store_true", help="Do not check/start Postgres.app.")
    parser.add_argument("--skip-db-init", action="store_true", help="Do not create DB, migrate or seed.")
    args = parser.parse_args()
    run_stack(skip_services=args.skip_services, skip_db_init=args.skip_db_init)


if __name__ == "__main__":
    main()
