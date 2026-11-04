"""One entry point for local development, disposable checks and releases.

Usage: python scripts/dev.py --help
"""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import closing, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "signal_flow_component"
sys.path.insert(0, str(ROOT))


def run(command, *, cwd=ROOT, env=None):
    print("+ " + " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, env=env, check=True)


def free_port(requested=0):
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", requested))
        return connection.getsockname()[1]


def wait_ready(url, process, timeout=45):
    deadline = time.monotonic() + timeout
    # Development traffic must stay local, independent of system proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited ({process.returncode}): {url}")
        try:
            with opener.open(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    raise RuntimeError(f"Server not ready: {url}")


def stop(process):
    if process is not None and process.poll() is None:
        if os.name == "nt":
            # Windows venv Python may use a redirector child. Stop only the
            # process tree started by this runner, including that child.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@contextmanager
def temporary_workspace():
    directory = tempfile.TemporaryDirectory(prefix="ee-req-ui-")
    try:
        yield Path(directory.name)
    finally:
        # Windows can release SQLite/WAL handles just after the process exits.
        # Retry removal of this runner-owned temporary directory only.
        for attempt in range(50):
            try:
                directory.cleanup()
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.1)


def demo_database(path):
    """Seed only a new DB or a database previously marked as our demo."""
    path = Path(path).resolve()
    if path == (ROOT / "ee_req.db").resolve():
        raise ValueError("Production ee_req.db cannot be used as a development fixture.")
    if path.exists() and path.stat().st_size:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
            try:
                marked = connection.execute("SELECT 1 FROM projects WHERE code='DEV-DEMO'").fetchone()
            except sqlite3.DatabaseError as exc:
                raise ValueError(f"Existing non-demo database preserved: {path}") from exc
            if not marked:
                raise ValueError(f"Existing non-demo database preserved: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Import db only after choosing the development database.
    os.environ["EE_REQ_DB_PATH"] = str(path)
    from db import SessionLocal, engine, init_db
    from services.demo_data import seed_demo

    if Path(engine.url.database).resolve() != path:
        raise RuntimeError("db.py was imported before the development database was selected.")
    init_db()
    with SessionLocal() as session:
        seed_demo(session)
    engine.dispose()
    return path


def frontend_command(*args):
    node = shutil.which("node")
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite.exists():
        raise RuntimeError("Frontend tools missing. Run python scripts/dev.py setup --frontend first.")
    return [node, str(vite), *args]


def setup(args):
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        run([sys.executable, "-m", "venv", ROOT / ".venv"])
    run([python, "-m", "ensurepip"])
    run([python, "-m", "pip", "install", "-r", ROOT / "requirements-dev.txt"])
    if args.frontend:
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm:
            raise RuntimeError("Node.js/npm is required to develop the canvas.")
        run([npm, "ci"], cwd=FRONTEND)
    print("Setup complete. Run .venv's Python: scripts/dev.py serve", flush=True)


def serve(args):
    database = demo_database(args.db)
    env = dict(os.environ, EE_REQ_DB_PATH=str(database), PYTHONUTF8="1")
    component = None
    server = None
    try:
        port = free_port(args.port)
        if not args.built:
            component_port = free_port(args.component_port)
            component_url = f"http://127.0.0.1:{component_port}"
            component = subprocess.Popen(
                frontend_command("--host", "127.0.0.1", "--port", str(component_port), "--strictPort"),
                cwd=FRONTEND, env=env,
            )
            wait_ready(component_url, component)
            env["EE_REQ_COMPONENT_DEV_URL"] = component_url
        else:
            env.pop("EE_REQ_COMPONENT_DEV_URL", None)
        url = f"http://127.0.0.1:{port}"
        server = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.address", "127.0.0.1", "--server.port", str(port),
            "--server.headless", "true", "--browser.gatherUsageStats", "false",
        ], cwd=ROOT, env=env)
        wait_ready(url + "/_stcore/health", server)
        print(f"\nDevelopment URL: {url}\nDemo database: {database}\nCtrl+C stops both servers.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        while server.poll() is None:
            if component is not None and component.poll() is not None:
                raise RuntimeError("Canvas dev server exited.")
            time.sleep(0.5)
        if server.returncode:
            raise RuntimeError(f"Streamlit exited: {server.returncode}")
    finally:
        stop(server)
        stop(component)


def check(args):
    # Syntax checks never execute app.py or open its default database.
    for directory in (ROOT, ROOT / "services", ROOT / "workspaces", ROOT / "scripts", ROOT / "tests"):
        for source in directory.glob("*.py"):
            ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
    run([sys.executable, "-m", "ruff", "check", "."])
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    if args.frontend:
        run([shutil.which("node") or "node", "--test", "tests/graph-state.test.mjs"], cwd=FRONTEND)
        run(frontend_command("build"), cwd=FRONTEND)
    if args.ui:
        with temporary_workspace() as folder:
            path = folder / "demo.db"
            # Seed in a child process so no parent-held SQLite handle can delay
            # cleanup of the disposable directory on Windows.
            run([sys.executable, ROOT / "scripts/dev.py", "demo", "--db", path])
            env = dict(os.environ, EE_REQ_DB_PATH=str(path), PYTHONUTF8="1")
            env.pop("EE_REQ_COMPONENT_DEV_URL", None)
            component = None
            if args.hot:
                component_url = f"http://127.0.0.1:{free_port()}"
                component = subprocess.Popen(
                    frontend_command("--host", "127.0.0.1", "--port", component_url.rsplit(":", 1)[-1], "--strictPort"),
                    cwd=FRONTEND, env=env, stdout=subprocess.DEVNULL,
                )
                try:
                    wait_ready(component_url, component)
                except Exception:
                    stop(component)
                    raise
                env["EE_REQ_COMPONENT_DEV_URL"] = component_url
            port = free_port()
            url = f"http://127.0.0.1:{port}"
            output = ROOT / "test-results"
            output.mkdir(exist_ok=True)
            server_log = (output / "server.log").open("w", encoding="utf-8")
            server = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run", "app.py",
                "--server.address", "127.0.0.1", "--server.port", str(port),
                "--server.headless", "true", "--browser.gatherUsageStats", "false",
            ], cwd=ROOT, env=env, stdout=server_log, stderr=subprocess.STDOUT)
            try:
                wait_ready(url + "/_stcore/health", server)
                env["EE_REQ_TEST_URL"] = url
                run([sys.executable, ROOT / "tests" / "ui_smoke.py"], env=env)
            finally:
                stop(server)
                stop(component)
                server_log.close()
    print("CHECKS PASSED", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("setup", help="Install pinned Python dependencies and optionally npm dependencies")
    install.add_argument("--frontend", action="store_true")
    dev = sub.add_parser("serve", help="Start Streamlit + Vite hot reload against a demo database")
    dev.add_argument("--db", type=Path, default=ROOT / ".dev/demo.db")
    dev.add_argument("--port", type=int, default=8510)
    dev.add_argument("--component-port", type=int, default=5173)
    dev.add_argument("--built", action="store_true", help="Use compiled canvas without Node.js")
    dev.add_argument("--no-browser", action="store_true")
    seed = sub.add_parser("demo", help="Create the repeatable demo scenario without running servers")
    seed.add_argument("--db", type=Path, default=ROOT / ".dev/demo.db")
    checks = sub.add_parser("check", help="Run syntax, lint and isolated unit tests")
    checks.add_argument("--frontend", action="store_true", help="Also test and build the canvas")
    checks.add_argument("--ui", action="store_true", help="Also run a disposable-database browser regression")
    checks.add_argument("--hot", action="store_true", help="Run --ui against Vite instead of the release canvas")
    sub.add_parser("build", help="Build the release canvas")
    args = parser.parse_args()
    try:
        if args.command == "setup":
            setup(args)
        elif args.command == "serve":
            serve(args)
        elif args.command == "demo":
            print(f"Demo database ready: {demo_database(args.db)}")
        elif args.command == "check":
            if args.hot and not args.ui:
                parser.error("--hot requires --ui")
            check(args)
        elif args.command == "build":
            run(frontend_command("build"), cwd=FRONTEND)
    except KeyboardInterrupt:
        print("\nDevelopment servers stopped.")
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
