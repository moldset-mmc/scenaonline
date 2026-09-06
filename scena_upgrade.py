"""Bring an existing pilot's data into a separate V1.7 installation.

The old database is only read through SQLite backup; migration happens when the
owner starts the newly created copy. Neither old nor stock application is changed.
"""

from __future__ import annotations

import argparse
import uuid
from datetime import datetime
from pathlib import Path

from scena_restore import restore_installation
from scena_transfer import TransferValidationError, build_backup, inspect_backup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Перенести свою старую SCENA в отдельную копию V1.7.")
    parser.add_argument("old_folder", nargs="?", help="Папка прежней распакованной SCENA")
    arguments = parser.parse_args(argv)
    try:
        entered = arguments.old_folder or input("Вставьте полный путь к старой папке SCENA: ")
        old = Path(entered.strip().strip('"')).absolute()
        current = Path(__file__).resolve().parent
        if not old.is_dir() or any(path.is_symlink() for path in (old, *old.parents)):
            raise TransferValidationError("Старая папка не найдена или является ссылкой.")
        if old == current:
            raise TransferValidationError("Укажите папку прежней версии, в которой находятся ваши сохранённые данные.")
        public_trust = None
        trust_path = old / "config" / "pro-issuer-public.pem"
        if trust_path.exists():
            if trust_path.is_symlink() or trust_path.parent.is_symlink() or trust_path.stat().st_size > 4096:
                raise TransferValidationError("Неверный файл публичного ключа PRO.")
            try:
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            except ImportError:
                raise TransferValidationError(
                    "Для проверки ключа PRO нужен пакет cryptography. Запустите UPGRADE-SCENA.cmd: "
                    "он подготовит отдельное окружение этой версии и установит зависимости. "
                    "Старая SCENA не изменена."
                ) from None
            try:
                public_trust = trust_path.read_bytes()
                if not isinstance(serialization.load_pem_public_key(public_trust), Ed25519PublicKey):
                    raise ValueError()
            except (ValueError, TypeError):
                raise TransferValidationError("Не удалось проверить публичный ключ PRO.")
        print("Проверяем вашу сохранённую Сцену…")
        bundle = build_backup(old / "scena_master.db", old / "media")
        summary = inspect_backup(bundle)
        suffix = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        destination = current.parent / ("SCENA-UPGRADED-V1.7-" + suffix)
        print(f"Владелец: {summary['owner_name'] or 'Имя не указано'}")
        print(f"Старая папка: {old}")
        print(f"Проверено файлов: {summary['file_count']}; медиа: {summary['media_count']}.")
        print(f"Новая папка V1.7: {destination}")
        print("Ваши настройки, записи, публикации и фотографии перейдут в новую копию.")
        print("Старая папка и чистая V1.7 сохранятся без изменений. Пароли окружения и подключения не копируются.")
        if input("Для создания этой новой копии введите ДА: ").strip().casefold() not in ("да", "yes"):
            print("Перенос отменён.")
            return 0
        result = restore_installation(bundle, current, destination)
        if public_trust:
            key_destination = destination / "config" / "pro-issuer-public.pem"
            key_destination.parent.mkdir(exist_ok=True)
            key_destination.write_bytes(public_trust)
        print(f"Готово: {result['destination']}")
        print("Откройте эту новую папку и запустите START-SCENA.cmd.")
        print("При первом запуске обновится только новая база. Старая останется у вас.")
        return 0
    except (TransferValidationError, OSError, EOFError, KeyboardInterrupt) as exc:
        print(f"Перенос не выполнен: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
