"""Docker olmadan yerel demo; Ctrl+C ile yalnızca bu betiğin servisleri kapanır."""

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
BACKEND = ROOT / "backend"


def wait_http(url, processes, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError(
                "Bir servis başlatılamadı; .local/*.log dosyalarını inceleyin"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 400:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError(f"Servis hazır olmadı: {url}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--postgres", action="store_true", help="Gerçek yerel PostgreSQL kullan"
    )
    args = parser.parse_args()
    LOCAL.mkdir(exist_ok=True, mode=0o700)
    python = BACKEND / ".venv/bin/python"
    if not python.exists() or not (ROOT / "frontend/node_modules/.bin/vite").exists():
        raise SystemExit("Önce: cd backend && uv sync; cd ../frontend && npm ci")
    redis = shutil.which("redis-server")
    if not redis:
        raise SystemExit("redis-server gerekli. Alternatif: make up")
    for port in [8000, 5173, 55000, 56379] + ([55432] if args.postgres else []):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise SystemExit(
                    f"{port} portu meşgul; mevcut servisi kapatın"
                ) from exc
    secret_file = LOCAL / "app-secret"
    if not secret_file.exists():
        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(secrets.token_hex(32))
    env = {
        **os.environ,
        "ENVIRONMENT": "development",
        "APP_SECRET": secret_file.read_text(),
        "PUBLIC_ORIGIN": "http://localhost:5173",
        "REDIS_URL": "redis://127.0.0.1:56379/0",
        "S3_MODE": "local",
        "S3_ENDPOINT_URL": "http://127.0.0.1:55000",
        "AWS_ACCESS_KEY_ID": "local-demo",
        "AWS_SECRET_ACCESS_KEY": "local-demo",
        "AWS_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "DATABASE_URL": f"sqlite:///{LOCAL / 'demo.db'}",
        "PYTHONUNBUFFERED": "1",
    }
    processes = []
    logs = []
    pgctl = None

    def start(name, command, cwd=BACKEND):
        log = open(LOCAL / f"{name}.log", "w")  # noqa: SIM115 - closed in outer finally
        logs.append(log)
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        processes.append(process)

    def stop_signal(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_signal)
    try:
        if args.postgres:
            bindir = os.environ.get("POSTGRES_BIN")
            if not bindir:
                found = shutil.which("initdb")
                bindir = (
                    str(Path(found).parent) if found else "/Library/PostgreSQL/17/bin"
                )
            pgctl = str(Path(bindir) / "pg_ctl")
            data = LOCAL / "postgres"
            if not (data / "PG_VERSION").exists():
                subprocess.run(
                    [
                        str(Path(bindir) / "initdb"),
                        "-D",
                        str(data),
                        "-U",
                        "tenantfiles",
                        "-A",
                        "trust",
                        "--encoding=UTF8",
                        "--locale=C",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
            subprocess.run(
                [
                    pgctl,
                    "-D",
                    str(data),
                    "-l",
                    str(LOCAL / "postgres.log"),
                    "-o",
                    f"-h 127.0.0.1 -p 55432 -k {LOCAL}",
                    "-w",
                    "start",
                ],
                check=True,
            )
            for dbname in ["tenantfiles", "tenantfiles_test"]:
                exists = subprocess.check_output(
                    [
                        str(Path(bindir) / "psql"),
                        "-h",
                        "127.0.0.1",
                        "-p",
                        "55432",
                        "-U",
                        "tenantfiles",
                        "-d",
                        "postgres",
                        "-tAc",
                        f"SELECT 1 FROM pg_database WHERE datname='{dbname}'",
                    ],
                    text=True,
                ).strip()
                if not exists:
                    subprocess.run(
                        [
                            str(Path(bindir) / "createdb"),
                            "-h",
                            "127.0.0.1",
                            "-p",
                            "55432",
                            "-U",
                            "tenantfiles",
                            dbname,
                        ],
                        check=True,
                    )
            env["DATABASE_URL"] = (
                "postgresql+psycopg://tenantfiles@127.0.0.1:55432/tenantfiles"
            )
        start(
            "redis",
            [
                redis,
                "--bind",
                "127.0.0.1",
                "--port",
                "56379",
                "--save",
                "",
                "--appendonly",
                "no",
                "--maxmemory",
                "128mb",
                "--maxmemory-policy",
                "noeviction",
            ],
        )
        start(
            "s3",
            [str(BACKEND / ".venv/bin/moto_server"), "-H", "127.0.0.1", "-p", "55000"],
        )
        wait_http("http://127.0.0.1:55000", processes)
        subprocess.run(
            [str(python), "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=env,
            check=True,
        )
        seeded = subprocess.check_output(
            [str(python), "-m", "app.demo"], cwd=BACKEND, env=env, text=True
        )
        fd = os.open(
            LOCAL / "demo-keys.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
        )
        with os.fdopen(fd, "w") as output:
            json.dump(json.loads(seeded), output, indent=2)
        start(
            "api",
            [
                str(python),
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
                "--no-proxy-headers",
                "--log-config",
                str(BACKEND / "logging.json"),
            ],
        )
        wait_http("http://127.0.0.1:8000/health/ready", processes)
        start(
            "web",
            [
                "node",
                str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
            ],
            cwd=ROOT / "frontend",
        )
        wait_http("http://127.0.0.1:5173", processes)
        print("Demo hazır: http://localhost:5173", flush=True)
        print(
            "API anahtarları: .local/demo-keys.json (yalnızca yerel demo)", flush=True
        )
        print(
            "Durdurmak için Ctrl+C. Yerel veritabanı korunur; S3 demo verileri yeniden oluşturulur.",
            flush=True,
        )
        while all(process.poll() is None for process in processes):
            time.sleep(1)
        raise RuntimeError("Bir servis durdu; .local/*.log dosyalarını inceleyin")
    except KeyboardInterrupt:
        print("Yerel servisler kapatılıyor…", flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()
        if pgctl and (LOCAL / "postgres/postmaster.pid").exists():
            subprocess.run(
                [pgctl, "-D", str(LOCAL / "postgres"), "-m", "fast", "-w", "stop"],
                check=False,
            )


if __name__ == "__main__":
    main()
