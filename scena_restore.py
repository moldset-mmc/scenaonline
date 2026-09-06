"""Restore owner data beside this application, never over a live installation."""

from __future__ import annotations

import argparse
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from scena_transfer import MAX_TOTAL_BYTES, TransferValidationError, inspect_backup, restore_backup


# Explicit distribution files only. Never copy credentials, databases, archives,
# environment folders, user scripts, QA/customer exports or repository metadata.
APPLICATION_FILES = (
    "scena_app.py", "scena_core.py", "scena_cabinet.py", "scena_integrations.py",
    "scena_publications.py", "scena_publication_ui.py", "scena_social.py", "scena_social_ui.py",
    "scena_transfer.py", "scena_transfer_ui.py", "scena_restore.py", "model_landing.py",
    "start_scena.py", "scena-master-standalone.py", "START-SCENA.cmd", "RESTORE-SCENA.cmd",
    "scena_upgrade.py", "UPGRADE-SCENA.cmd",
    "scena_design.py", "scena_booking_ui.py", "scena_portfolio.py", "scena_pro_ui.py",
    "scena_telegram_setup.py", "CONNECT-TELEGRAM.cmd", "TELEGRAM-SETUP.md",
    "scena_model_intro.py", "scena_i18n.py", "scena_workspace_ui.py",
    "scena_shop.py", "scena_prompts.py", "scena_licensing.py", "scena_pro_operator.py", "PRO-OPERATOR.cmd",
    "PRO-RENEWAL-SETUP.md", "PROMPT-LIBRARY-GUIDE.md", "config/pro-issuer-public.pem", "scena_qr.py", "scena_model_builder.py",
    "scena_help_ui.py", "scena_connect_setup.py", "CONNECT-AI.cmd", "CONNECTIONS.md",
    "requirements.txt", "README.md", ".streamlit/config.toml",
)
REQUIRED_APPLICATION_FILES = tuple(
    name for name in APPLICATION_FILES if name.endswith((".py", ".cmd")) or name == "requirements.txt"
)
# Trusted distribution assets only: never enumerate another installation's media.
# Owner files from the backup always win, including an image at a bundled path.
BUNDLED_MEDIA_FILES = (
    "media/qr-scenes/scene.png", "media/qr-scenes/professional.png",
    "media/qr-scenes/model.png", "media/qr-scenes/booking.png",
    "media/scena-v13/my-scena-hero.webp", "media/scena-v13/professional-portrait.webp",
    "media/model-slider/01-black-halo.webp", "media/model-slider/02-black-portrait.webp",
    "media/model-slider/03-white-couture.webp", "media/model-slider/04-white-motion.webp",
    "media/model-slider/05-tan-white-wings.webp",
    "media/model-slider/NimbusSans-Regular.otf", "media/model-slider/P052-Roman.otf",
    "media/model-slider/arrow-left.svg", "media/model-slider/arrow-right.svg",
    "media/model-slider/play.svg", "media/model-slider/pause.svg",
)


def new_restore_destination(app_dir) -> Path:
    return Path(app_dir).absolute().parent / f"SCENA-RESTORED-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def restore_installation(data: bytes, app_dir, destination) -> dict:
    """Assemble a separate runnable copy from validated data and this trusted app."""
    summary = inspect_backup(data)
    if summary["kind"] != "private_backup":
        raise TransferValidationError("Для восстановления нужна личная резервная копия SCENA.")
    source = Path(app_dir).absolute()
    target = Path(destination).absolute()
    if not source.is_dir() or any(part.is_symlink() for part in (source, *source.parents)):
        raise TransferValidationError("Исходная папка приложения недоступна или является ссылкой.")
    if target.parent != source.parent or target == source:
        raise TransferValidationError("Копия создаётся только в новой соседней папке приложения.")
    if target.exists() or target.is_symlink():
        raise TransferValidationError("Папка уже существует. Выберите новое имя для восстановления.")
    files = {}
    for name in APPLICATION_FILES:
        path = source / name
        if path.is_symlink() or any(part.is_symlink() for part in path.parents):
            raise TransferValidationError("Файл приложения является символической ссылкой.")
        if path.is_file():
            if path.stat().st_size > 8 * 1024 * 1024:
                raise TransferValidationError("Файл приложения имеет неожиданный размер.")
            files[name] = path.read_bytes()
    if any(name not in files for name in REQUIRED_APPLICATION_FILES):
        raise TransferValidationError("Не найдены файлы запуска. Восстанавливайте рядом с полной распакованной SCENA V1.7.")
    with tempfile.TemporaryDirectory(prefix="scena-copy-", dir=source.parent) as temp:
        staged = Path(temp) / "installation"
        restore_backup(data, staged)
        for name, value in files.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(value)
        for name in BUNDLED_MEDIA_FILES:
            path = staged / name
            if path.exists():
                continue
            asset = source / name
            if asset.is_symlink() or any(part.is_symlink() for part in asset.parents):
                raise TransferValidationError("Установочное изображение является символической ссылкой.")
            if not asset.is_file():
                continue
            if asset.stat().st_size > 8 * 1024 * 1024:
                raise TransferValidationError("Установочное изображение имеет неожиданный размер.")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(asset.read_bytes())
        if target.exists() or target.is_symlink():
            raise TransferValidationError("Папка назначения появилась во время проверки. Текущая установка сохранена.")
        try:
            staged.rename(target)
        except OSError as exc:
            raise TransferValidationError("Не удалось создать соседнюю копию. Проверьте свободное место и доступ к папке.") from exc
    return {"destination": str(target), "db_path": str(target / "scena_master.db"),
            "media_dir": str(target / "media"), "launcher": str(target / "START-SCENA.cmd"),
            "identity": summary["identity"], "contains_private_data": True,
            "operator_configuration_copied": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Восстановить личную копию SCENA в новую соседнюю папку.")
    parser.add_argument("archive", nargs="?", help="Путь к ZIP резервной копии")
    arguments = parser.parse_args(argv)
    try:
        entered = arguments.archive or input("Вставьте полный путь к ZIP резервной копии: ")
        path = Path(entered.strip().strip('"'))
        if not path.is_file() or path.stat().st_size > MAX_TOTAL_BYTES:
            raise TransferValidationError("ZIP не найден или превышает лимит 512 МБ.")
        data = path.read_bytes()
        summary = inspect_backup(data)
        if summary["kind"] != "private_backup":
            raise TransferValidationError("Это публичный экспорт, а не личная резервная копия.")
        source = Path(__file__).resolve().parent
        target = new_restore_destination(source)
        print(f"Проверено файлов: {summary['file_count']}. Фотографий и других медиа: {summary['media_count']}.")
        print(f"Новая папка: {target}")
        print("Личные данные вернутся в новую копию. Текущая SCENA останется без изменений.")
        print("Настройки подключений и пароли окружения не переносятся.")
        if input("Для создания копии введите ДА: ").strip().casefold() not in ("да", "yes"):
            print("Восстановление отменено.")
            return 0
        result = restore_installation(data, source, target)
        print(f"Копия готова: {result['destination']}")
        print("Откройте эту папку и запустите START-SCENA.cmd.")
        return 0
    except (TransferValidationError, OSError, EOFError, KeyboardInterrupt) as exc:
        print(f"Восстановление не выполнено: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
