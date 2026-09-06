"""Per-installation Telegram setup. Nothing is sent when saving or loading.

Credentials stay in the operating system's user configuration directory and
are keyed by the normalized application path. Copies sold to other owners and
SCENA backups never carry the connection credentials.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from typing import Callable, Mapping
import unicodedata
from urllib.request import Request, urlopen

from scena_integrations import TelegramBotAdapter


TEST_MESSAGE = (
    "SCENA · проверка подключения.\n"
    "Сообщение отправлено из вашей SCENA по вашему подтверждению."
)
_TOKEN_PATTERN = re.compile(r"[1-9][0-9]{4,19}:[A-Za-z0-9_-]{20,200}\Z")
_CHAT_PATTERN = re.compile(r"[1-9][0-9]{0,19}\Z")


class TelegramSetupError(ValueError):
    """A deliberately credential-free configuration or connection error."""


@dataclass(frozen=True)
class TelegramConnection:
    token: str = field(repr=False)
    chat_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or not _TOKEN_PATTERN.fullmatch(self.token):
            raise TelegramSetupError("Проверьте токен бота: вставьте его целиком из BotFather.")
        if not isinstance(self.chat_id, str) or not _CHAT_PATTERN.fullmatch(self.chat_id):
            raise TelegramSetupError(
                "Нужен числовой ID вашего личного чата: положительное число без @. "
                "Группы этим способом не подключаются."
            )

    @property
    def bot_id(self) -> str:
        return self.token.split(":", 1)[0]

    def as_environment(self) -> dict[str, str]:
        return {
            "SCENA_TELEGRAM_BOT_TOKEN": self.token,
            "SCENA_TELEGRAM_ADMIN_CHAT_ID": self.chat_id,
            "SCENA_TELEGRAM_ADMIN_USER_IDS": self.chat_id,
        }


def installation_key(app_dir: Path) -> str:
    normalized = os.path.normcase(str(Path(app_dir).resolve()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def configuration_path(app_dir: Path) -> Path:
    """Return a user-private path outside this application, without creating it."""
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        root = root / "SCENA"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "scena"
    if not root.is_absolute():
        raise TelegramSetupError("Каталог личных настроек должен иметь полный путь.")
    target = root / "connections" / installation_key(app_dir) / "telegram.json"
    if target.resolve().is_relative_to(Path(app_dir).resolve()):
        raise TelegramSetupError("Подключение нужно хранить отдельно от папки SCENA.")
    return target


def load_connection(app_dir: Path) -> TelegramConnection | None:
    path = configuration_path(app_dir)
    try:
        if not path.exists():
            return None
        if path.is_symlink() or path.stat().st_size > 4096:
            raise TelegramSetupError("Сохранённое подключение повреждено. Запустите CONNECT-TELEGRAM.cmd снова.")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema") != 1 or raw.get("installation") != installation_key(app_dir):
            raise ValueError("Invalid connection file")
        return TelegramConnection(token=raw.get("bot_token"), chat_id=raw.get("private_chat_id"))
    except (OSError, ValueError, TypeError):
        raise TelegramSetupError(
            "Не удалось прочитать подключение Telegram. Запустите CONNECT-TELEGRAM.cmd снова."
        ) from None


def load_environment(app_dir: Path) -> dict[str, str]:
    """Load only this installation's Telegram settings; do not mutate os.environ."""
    connection = load_connection(app_dir)
    return connection.as_environment() if connection else {}


def save_connection(app_dir: Path, connection: TelegramConnection) -> Path:
    """Atomically save the approved local connection; this makes no network calls."""
    path = configuration_path(app_dir)
    temporary: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            path.parent.chmod(0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".telegram-", dir=path.parent)
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        payload = {
            "schema": 1,
            "installation": installation_key(app_dir),
            "bot_token": connection.token,
            "private_chat_id": connection.chat_id,
        }
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        return path
    except OSError:
        raise TelegramSetupError("Не удалось сохранить подключение в личных настройках компьютера.") from None
    finally:
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def save_preview(app_dir: Path, connection: TelegramConnection) -> str:
    return (
        f"Папка SCENA: {Path(app_dir).resolve()}\n"
        f"Бот: ID {connection.bot_id}\n"
        f"Получатель: ваш личный Telegram, chat ID {connection.chat_id}\n\n"
        "После следующего запуска SCENA обращения из раздела «Помощь» смогут "
        "отправляться этому получателю. Его ответы на эти сообщения появятся в SCENA "
        "при обновлении раздела «Помощь».\n"
        "Токен сохраняется только в личных настройках этого компьютера. "
        "Сейчас сообщения не отправляются."
    )


def _read_bot_updates(token: str) -> object:
    """Read without an offset or allowed_updates: never acknowledge old updates."""
    request = Request(
        f"https://api.telegram.org/bot{token}/getUpdates",
        data=b'{"limit":100,"timeout":0}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, Mapping) or result.get("ok") is not True:
            raise ValueError("Rejected read")
        return result.get("result")
    except Exception:
        raise TelegramSetupError(
            "Не удалось прочитать код. Проверьте токен и используйте отдельного бота SCENA "
            "без другого подключённого сервиса. Настройки бота не изменялись."
        ) from None


def _safe_display(value: object) -> str:
    return "".join(char for char in str(value or "") if not unicodedata.category(char).startswith("C"))[:100]


def discover_private_chat(
    token: str,
    *,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
    fetch_updates: Callable[[str], object] = _read_bot_updates,
    clock: Callable[[], float] = time.time,
    code_factory: Callable[[], str] = lambda: secrets.token_hex(5).upper(),
) -> str | None:
    """Bind only a fresh, unique private-chat code the owner explicitly confirms."""
    if not isinstance(token, str) or not _TOKEN_PATTERN.fullmatch(token):
        raise TelegramSetupError("Проверьте токен бота: вставьте его целиком из BotFather.")
    code = "SCENA CONNECT " + code_factory()
    started_at = clock()
    write(
        f"Бот: ID {token.split(':', 1)[0]}. Откройте именно своего бота в Telegram.\n"
        f"Отправьте ему из своего личного чата этот одноразовый код:\n\n{code}\n\n"
        "Затем программа один раз прочитает до 100 ожидающих обновлений этого бота "
        "и найдёт только ваш свежий код в личном чате. Другие сообщения не будут "
        "показаны или сохранены. Программа не отправит сообщение и не изменит "
        "настройки бота или очередь обновлений."
    )
    if read("Когда код отправлен, разрешите это чтение словом ПРОЧИТАТЬ: ").strip().casefold() not in ("прочитать", "read"):
        write("Поиск отменён. В Telegram программа не обращалась.")
        return None
    if clock() - started_at > 600:
        raise TelegramSetupError("Код действовал 10 минут. Начните настройку снова, чтобы получить новый код.")
    try:
        updates = fetch_updates(token)
    except Exception:
        raise TelegramSetupError(
            "Не удалось прочитать код. Проверьте токен и используйте отдельного бота SCENA. "
            "Программа не меняла настройки или очередь обновлений."
        ) from None
    if not isinstance(updates, list):
        raise TelegramSetupError("Telegram не вернул список обновлений. Подключение не сохранено.")
    candidates: dict[str, Mapping] = {}
    now = clock()
    for update in updates:
        if not isinstance(update, Mapping):
            continue
        message = update.get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("text"), str) or message["text"].strip() != code:
            continue
        chat, sender = message.get("chat"), message.get("from")
        if not isinstance(chat, Mapping) or not isinstance(sender, Mapping):
            continue
        chat_id = str(chat.get("id", ""))
        sent_at = message.get("date")
        if (
            chat.get("type") != "private"
            or not _CHAT_PATTERN.fullmatch(chat_id)
            or str(sender.get("id")) != chat_id
            or sender.get("is_bot") is not False
            or message.get("forward_origin")
            or not isinstance(sent_at, (int, float))
            or not started_at - 5 <= sent_at <= now + 60
        ):
            continue
        candidates[chat_id] = chat
    if not candidates:
        raise TelegramSetupError(
            "Свежий код не найден в личном чате. Проверьте, что он отправлен нужному боту. "
            "Начните настройку снова. Для действующего бота со старой очередью используйте "
            "известный ID вручную или отдельного бота SCENA."
        )
    if len(candidates) != 1:
        raise TelegramSetupError("Код найден в нескольких чатах. Подключение не выбрано. Начните настройку с новым кодом.")
    chat_id, chat = next(iter(candidates.items()))
    name = " ".join(_safe_display(chat.get(part)) for part in ("first_name", "last_name")).strip()
    username = _safe_display(chat.get("username"))
    write(f"Найден личный чат: {name or 'Имя не указано'}{f' (@{username})' if username else ''}.\nChat ID: {chat_id}.")
    if read("Если это именно ваш Telegram, введите МОЙ ЧАТ: ").strip().casefold() not in ("мой чат", "my chat"):
        write("Получатель не подтверждён. Подключение не сохранено.")
        return None
    return chat_id


def test_connection(
    connection: TelegramConnection,
    *,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
    adapter_factory: Callable[..., TelegramBotAdapter] = TelegramBotAdapter,
) -> bool:
    """Send exactly one test, only after displaying the target, actions and text."""
    write(
        f"Проверка бота ID {connection.bot_id}.\n"
        f"Получатель: личный chat ID {connection.chat_id}.\n"
        "Будет проверен ID бота, затем отправлено одно сообщение:\n\n"
        f"{TEST_MESSAGE}\n\n"
        "Контакты клиентов и обращения в этот тест не входят."
    )
    if read("Для отправки этого сообщения введите ОТПРАВИТЬ: ").strip().casefold() not in ("отправить", "send"):
        write("Тест отменён. Ничего не отправлено.")
        return False
    try:
        adapter = adapter_factory(bot_token=connection.token, admin_chat_id=connection.chat_id)
        bot = adapter._call("getMe", {})
        if not isinstance(bot, Mapping) or str(bot.get("id")) != connection.bot_id or bot.get("is_bot") is not True:
            raise TelegramSetupError("ID бота не подтверждён. Тестовое сообщение не отправлено.")
        result = adapter._call("sendMessage", {"chat_id": connection.chat_id, "text": TEST_MESSAGE})
        if (
            not isinstance(result, Mapping)
            or not isinstance(result.get("chat"), Mapping)
            or str(result["chat"].get("id")) != connection.chat_id
            or result["chat"].get("type") != "private"
            or result.get("message_id") is None
        ):
            raise TelegramSetupError("Telegram не подтвердил доставку в указанный личный чат. Автоматического повтора не будет.")
        write("Telegram подтвердил доставку теста. Проверьте это сообщение у себя в Telegram.")
        return True
    except TelegramSetupError:
        raise
    except Exception:
        raise TelegramSetupError(
            "Доставка теста не подтверждена. Проверьте токен, ID и что вы нажали «Старт» "
            "в чате с ботом. Автоматического повтора не будет."
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Подключить личный Telegram к этой копии SCENA.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test", action="store_true", help="Показать и отдельно подтвердить тест сохранённого подключения")
    mode.add_argument("--status", action="store_true", help="Показать получателя без токена и без обращения в Telegram")
    args = parser.parse_args(argv)
    app_dir = Path(__file__).resolve().parent
    try:
        if args.test or args.status:
            connection = load_connection(app_dir)
            if not connection:
                raise TelegramSetupError("Подключение для этой папки ещё не сохранено. Запустите CONNECT-TELEGRAM.cmd.")
            if args.status:
                print(f"Сохранён бот ID {connection.bot_id}, личный chat ID {connection.chat_id}.")
                print("Это сохранённые настройки. Для проверки доставки используйте --test.")
                return 0
            return 0 if test_connection(connection) else 1
        print("Подключение вашего Telegram к этой папке SCENA.")
        print("Используйте отдельного бота SCENA. Откройте его в Telegram и нажмите «Старт».")
        token = getpass.getpass("Вставьте токен из BotFather (символы не отображаются): ").strip()
        chat_id = input("ID вашего личного чата, если знаете; Enter — определить по коду: ").strip()
        if not chat_id:
            chat_id = discover_private_chat(token)
            if chat_id is None:
                return 0
        connection = TelegramConnection(token=token, chat_id=chat_id)
        print("\n" + save_preview(app_dir, connection))
        if input("Чтобы сохранить именно это подключение, введите СОХРАНИТЬ: ").strip().casefold() not in ("сохранить", "save"):
            print("Сохранение отменено.")
            return 0
        save_connection(app_dir, connection)
        print("Подключение сохранено. Доставка ещё не проверена.")
        if input("Показать отдельную проверку доставки? ДА / Enter — закончить: ").strip().casefold() in ("да", "yes"):
            test_connection(connection)
        print("Перезапустите SCENA через START-SCENA.cmd, чтобы применить подключение.")
        return 0
    except TelegramSetupError as exc:
        print(str(exc))
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nНастройка прервана.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
