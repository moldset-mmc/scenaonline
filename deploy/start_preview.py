"""Run an explicitly temporary SCENA preview in a writable container directory.

Production hosting must use durable database/media adapters instead of this
launcher. Credentials are supplied privately at deployment time, never in Git.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def prepare_runtime(source: Path, runtime: Path) -> Path:
    """Copy application code and bundled images, never an owner's database."""
    runtime.mkdir(parents=True, exist_ok=False)
    for file in source.glob("*.py"):
        shutil.copyfile(file, runtime / file.name)
    shutil.copytree(source / "media", runtime / "media")
    (runtime / ".streamlit").mkdir()
    shutil.copyfile(source / ".streamlit/config.toml", runtime / ".streamlit/config.toml")
    return runtime


def preview_password(source: Path, environment: dict[str, str]) -> str:
    password = environment.get("SCENA_ADMIN_PASSWORD", "").strip()
    if not password:
        private_file = source / "deploy/preview-credentials.json"
        if private_file.is_file():
            password = str(json.loads(private_file.read_text())["admin_password"])
    if len(password) < 16:
        raise RuntimeError("A private preview administrator password is required.")
    return password


def main() -> None:
    environment = dict(os.environ)
    if environment.get("VERCEL_ENV") == "production":
        raise RuntimeError("This launcher is for preview deployments only.")
    source = Path(__file__).resolve().parents[1]
    password = preview_password(source, environment)
    temporary_parent = Path(tempfile.mkdtemp(prefix="scena-preview-"))
    runtime = prepare_runtime(source, temporary_parent / "app")
    environment["SCENA_ADMIN_PASSWORD"] = password
    environment["SCENA_PREVIEW_ONLY"] = "1"
    environment["SCENA_DB_PATH"] = str(runtime / "scena_master.db")
    environment["PYTHONPATH"] = str(runtime)
    port = int(environment.get("PORT", "80"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid listening port.")
    os.chdir(runtime)
    os.execvpe(sys.executable, [
        sys.executable, "-m", "streamlit", "run", "scena-master-standalone.py",
        "--server.address", "0.0.0.0", "--server.port", str(port),
        "--server.headless", "true",
    ], environment)


if __name__ == "__main__":
    main()
