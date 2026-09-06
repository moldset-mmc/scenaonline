"""Local operator connection setup. Credentials never enter the site database."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from scena_telegram_setup import configuration_path as telegram_configuration_path, installation_key


class ConnectionSetupError(ValueError):
    pass


@dataclass(frozen=True)
class AIConnection:
    api_key: str = field(repr=False)
    model: str
    endpoint: str = "https://api.openai.com/v1/responses"

    def __post_init__(self):
        if not isinstance(self.api_key, str) or not 8 <= len(self.api_key) <= 4096 or re.search(r"\s", self.api_key):
            raise ConnectionSetupError("Вставьте API-ключ целиком, без пробелов.")
        if not isinstance(self.model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", self.model):
            raise ConnectionSetupError("Укажите идентификатор модели, доступной вашему API-ключу.")
        parts = urlsplit(self.endpoint)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ConnectionSetupError("Укажите HTTPS-адрес Responses API без паролей и параметров.")

    def as_environment(self):
        return {"SCENA_AI_API_KEY": self.api_key, "SCENA_AI_MODEL": self.model, "SCENA_AI_API_URL": self.endpoint}


def configuration_path(app_dir: Path) -> Path:
    return telegram_configuration_path(app_dir).with_name("ai.json")


def save_connection(app_dir: Path, connection: AIConnection) -> Path:
    """Save atomically outside application/backup; never call the provider."""
    path = configuration_path(app_dir)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            path.parent.chmod(0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".ai-", dir=path.parent)
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"schema": 1, "installation": installation_key(app_dir), **connection.as_environment()}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        return path
    except OSError:
        raise ConnectionSetupError("Не удалось сохранить подключение в личных настройках компьютера.") from None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def load_connection(app_dir: Path) -> AIConnection | None:
    path = configuration_path(app_dir)
    if not path.exists():
        return None
    try:
        if path.is_symlink() or path.stat().st_size > 8192:
            raise ValueError("invalid file")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or data.get("installation") != installation_key(app_dir):
            raise ValueError("wrong installation")
        return AIConnection(data.get("SCENA_AI_API_KEY"), data.get("SCENA_AI_MODEL"), data.get("SCENA_AI_API_URL"))
    except (ValueError, OSError, TypeError, AttributeError):
        raise ConnectionSetupError("Проверьте сохранённое AI-подключение в разделе «Подключения».") from None


def load_environment(app_dir: Path) -> dict[str, str]:
    connection = load_connection(app_dir)
    return connection.as_environment() if connection else {}


def effective_environment(app_dir: Path, environment=None, *, channels=("ai", "telegram")) -> dict[str, str]:
    """Environment credentials override the entire corresponding private config."""
    from scena_telegram_setup import load_environment as load_telegram_environment
    values = dict(os.environ if environment is None else environment)
    if "ai" in channels and not any(values.get(key) for key in ("SCENA_AI_API_KEY", "SCENA_AI_MODEL", "SCENA_AI_API_URL")):
        values.update(load_environment(app_dir))
    if "telegram" in channels and not any(values.get(key) for key in ("SCENA_TELEGRAM_BOT_TOKEN", "SCENA_TELEGRAM_ADMIN_CHAT_ID", "SCENA_TELEGRAM_ADMIN_USER_IDS")):
        values.update(load_telegram_environment(app_dir))
    return values


def _t(locale, ru, ro, en):
    return {"ru": ru, "ro": ro, "en": en}.get(locale, ru)


def render_connections(db_path, app_dir: Path, locale: str = "ru") -> None:
    import streamlit as st
    from scena_cabinet import get_integration_health
    from scena_integrations import OpenAIResponsesAdapter, TelegramBotAdapter, IntegrationConfigurationError
    from scena_telegram_setup import TelegramSetupError
    try:
        env = effective_environment(app_dir)
        ai, telegram = OpenAIResponsesAdapter.from_env(env), TelegramBotAdapter.from_env(env)
    except (ConnectionSetupError, TelegramSetupError, IntegrationConfigurationError, ValueError):
        st.error(_t(locale, "Проверьте сохранённые параметры подключения.", "Verificați parametrii conexiunii salvate.", "Check your saved connection settings."))
        ai, telegram = OpenAIResponsesAdapter(), TelegramBotAdapter()
    st.write(_t(locale, "Настройки владельца: AI отвечает по данным вашей Сцены, Telegram доставляет обращения команде.", "Setările proprietarului: AI răspunde folosind datele Scenei, iar Telegram transmite solicitările echipei.", "Owner settings: AI uses your Scene data; Telegram delivers requests to your team."))
    for channel, name, adapter in (("ai", "AI", ai), ("telegram", "Telegram", telegram)):
        health = get_integration_health(db_path, channel)
        verified = bool(adapter.configured and health.get("configuration_fingerprint") == adapter.configuration_fingerprint and health.get("last_check_status") == "success")
        label = _t(locale, "Связь проверена", "Conexiune verificată", "Connection verified") if verified else (_t(locale, "Настроено · ожидает проверки", "Configurat · de verificat", "Configured · awaiting verification") if adapter.configured else _t(locale, "Добавить подключение", "Adăugați conexiunea", "Add connection"))
        st.caption(f"{name} · {label}")
    st.subheader(_t(locale, "Мозг SCENA Ассистента", "Inteligența Asistentului SCENA", "SCENA Assistant intelligence"))
    st.caption(_t(locale, "Ключ хранится в личных настройках этого компьютера и не входит в резервную копию сайта.", "Cheia rămâne în setările private ale acestui calculator și nu intră în copia site-ului.", "The key stays in this computer's private settings and is excluded from site backups."))
    with st.form("scena_ai_connection_form", clear_on_submit=True):
        key = st.text_input(_t(locale, "API-ключ", "Cheie API", "API key"), type="password", autocomplete="off")
        model = st.text_input(_t(locale, "Модель AI", "Model AI", "AI model"), value=ai.model, placeholder=_t(locale, "ID модели из вашего API-проекта", "ID-ul modelului din proiectul dvs. API", "Model ID from your API project"))
        endpoint = st.text_input(_t(locale, "Адрес Responses API", "Adresa Responses API", "Responses API endpoint"), value=ai.endpoint)
        consent = st.checkbox(_t(locale, "Разрешаю отправлять этому AI мои вопросы, тексты страниц и сводку моей работы для ответа.", "Permit trimiterea întrebărilor, textelor paginilor și rezumatului activității mele acestui AI pentru răspunsuri.", "I allow sending my questions, page text and work summary to this AI for answers."))
        save = st.form_submit_button(_t(locale, "Сохранить AI-подключение", "Salvează conexiunea AI", "Save AI connection"), type="primary", width="stretch")
    if save:
        if not consent:
            st.error(_t(locale, "Подтвердите отправку контекста выбранному AI.", "Confirmați trimiterea contextului către AI ales.", "Confirm sharing context with the selected AI."))
        else:
            try:
                save_connection(app_dir, AIConnection(key.strip(), model.strip(), endpoint.strip()))
            except ConnectionSetupError:
                st.error(_t(locale, "Проверьте ключ, модель и HTTPS-адрес API.", "Verificați cheia, modelul și adresa HTTPS API.", "Check the key, model and HTTPS API endpoint."))
            else:
                st.success(_t(locale, "Сохранено. Внешний запрос не выполнялся. Откройте Ассистента и задайте вопрос для проверки.", "Salvat. Nu s-a trimis nicio cerere externă. Deschideți Asistentul și puneți o întrebare pentru verificare.", "Saved. No external request was made. Open the Assistant and ask a question to verify."))
                if any(os.environ.get(k) for k in ("SCENA_AI_API_KEY", "SCENA_AI_MODEL", "SCENA_AI_API_URL")):
                    st.info(_t(locale, "Настройки запуска имеют приоритет. Для этой замены обновите их и перезапустите SCENA.", "Setările de pornire au prioritate. Actualizați-le și reporniți SCENA pentru această schimbare.", "Startup settings take priority. Update them and restart SCENA to apply this change."))
    st.subheader(_t(locale, "Команда SCENA → ваш Telegram", "Echipa SCENA → Telegramul dvs.", "SCENA team → your Telegram"))
    st.write(_t(locale, "Откройте CONNECT-TELEGRAM.cmd в папке сайта. Введите токен отдельного бота из BotFather и подтвердите свой личный чат по коду. Программа покажет получателя и отдельно предложит проверку.", "Deschideți CONNECT-TELEGRAM.cmd din dosarul site-ului. Introduceți tokenul unui bot dedicat din BotFather și confirmați chatul personal prin cod. Programul va afișa destinatarul și va propune verificarea separat.", "Open CONNECT-TELEGRAM.cmd in the site folder. Enter a dedicated bot token from BotFather and confirm your private chat using a code. The program shows the recipient and offers a separate test."))
    st.write(_t(locale, "Обращение приходит вам в Telegram вместе с выбранным каналом ответа. Ответьте через Reply — текст появится в SCENA после обновления ответов. Для Telegram, SMS или email напишите клиентке по контакту из обращения.", "Solicitarea ajunge în Telegram cu canalul ales pentru răspuns. Folosiți Reply, iar textul apare în SCENA după actualizare. Pentru Telegram, SMS sau email, scrieți persoanei folosind contactul din solicitare.", "Requests arrive in Telegram with the preferred reply channel. Use Reply and your text appears in SCENA after refreshing replies. For Telegram, SMS or email, contact the person using the details in their request."))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Настройка AI для этой копии SCENA")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    app_dir = Path(__file__).resolve().parent
    try:
        if args.status:
            saved = load_connection(app_dir)
            print(f"AI: {saved.model} · {saved.endpoint}" if saved else "AI-подключение не задано.")
            print("Показаны только локальные настройки. Внешний запрос не выполнялся.")
            return 0
        print("SCENA AI. Подготовьте API-ключ и ID модели в своём API-проекте.")
        key = getpass.getpass("API-ключ (не отображается): ").strip()
        model = input("ID модели: ").strip()
        endpoint = input("Responses API URL [https://api.openai.com/v1/responses]: ").strip() or "https://api.openai.com/v1/responses"
        connection = AIConnection(key, model, endpoint)
        print(f"Модель: {model}\nAPI: {endpoint}\nПапка SCENA: {app_dir}")
        print("При вашем вопросе AI получит тексты ваших страниц, услуги и сводку работы. Контакты клиентов и ключи в контекст не входят. Сейчас запрос не выполняется.")
        if input("Разрешить такие ответы и сохранить настройки? Введите СОХРАНИТЬ: ").strip().casefold() in {"сохранить", "save"}:
            save_connection(app_dir, connection)
            print("Сохранено. Откройте SCENA Ассистента для первого вопроса.")
        return 0
    except (ConnectionSetupError, EOFError, KeyboardInterrupt):
        print("Настройка не завершена. Проверьте данные и повторите запуск.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
