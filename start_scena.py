"""Safe local launcher for SCENA V1.7."""

from __future__ import annotations

import getpass
import os
import socket
import subprocess
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent


def find_available_port(start: int = 8501, attempts: int = 20) -> int:
    """Return the first localhost port that can be bound."""

    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError(
        f"Не найден свободный порт в диапазоне {start}–{start + attempts - 1}."
    )


def main() -> int:
    password = os.environ.get("SCENA_ADMIN_PASSWORD", "").strip()
    if not password:
        password = getpass.getpass("Пароль кабинета мастера: ").strip()
    if len(password) < 8:
        print("Пароль должен содержать не менее 8 символов.")
        return 2

    environment = os.environ.copy()
    environment["SCENA_ADMIN_PASSWORD"] = password
    from scena_telegram_setup import load_environment, TelegramSetupError
    telegram_keys = ("SCENA_TELEGRAM_BOT_TOKEN", "SCENA_TELEGRAM_ADMIN_CHAT_ID", "SCENA_TELEGRAM_ADMIN_USER_IDS")
    if not any(environment.get(key, "").strip() for key in telegram_keys):
        try:
            environment.update(load_environment(APP_DIR))
        except TelegramSetupError as exc:
            print(str(exc))
    try:
        port = find_available_port()
    except RuntimeError as exc:
        print(str(exc))
        return 3
    base_url = f"http://localhost:{port}"
    environment["SCENA_LOCAL_BASE_URL"] = base_url
    if port != 8501:
        print(f"Порт 8501 занят. SCENA автоматически использует порт {port}.")
    print(f"Моя Сцена:       {base_url}/?page=scene")
    print(f"Страница Model:  {base_url}/?page=model")
    print(f"Магазин Market:  {base_url}/?page=shop")
    print(f"Кабинет мастера: {base_url}/?page=admin&admin=1")
    print("Оставьте это окно открытым, пока работаете с SCENA.")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_DIR / "scena-master-standalone.py"),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
        "--server.headless",
        "false",
    ]
    try:
        return subprocess.call(command, cwd=APP_DIR, env=environment)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
