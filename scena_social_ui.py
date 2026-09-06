"""Publications → Facebook/Instagram. All network operations require a click."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st

from scena_publications import (
    PublicationValidationError, dispatch_delivery, get_channel_draft, get_delivery,
    get_draft, get_publication, list_deliveries, prepare_delivery, refresh_delivery,
    save_channel_draft, render_publication_image, managed_original, get_private_export_source,
)
from scena_social import get_adapters, is_public_https_url
from scena_i18n import localized_name, tr as translate


_EN = {
    "Подготовьте вариант для соцсети. Материал и история отправок остаются в SCENA.": "Prepare a social post. Your content and delivery history stay in SCENA.",
    "Площадка": "Platform", "Язык публикации": "Post language", "Фото и подпись для страницы Facebook или профессионального аккаунта Instagram.": "Photograph and caption for a Facebook Page or professional Instagram account.",
    "Площадка подтвердила публикацию.": "The platform confirmed your publication.", "Открыть публикацию": "Open publication",
    "Для соцсетей используется опубликованная версия. Новые правки сначала опубликуйте в своей Сцене.": "Social exports use the published version. Publish your latest changes on your Scene first.",
    "Подпись для соцсети": "Social caption", "Сохранить вариант": "Save version", "Скачать фото и подпись": "Download photograph and caption",
    "Скачайте готовые фото и подпись. Для прямой отправки ваша Сцена должна быть доступна в интернете.": "Download your photograph and caption. Direct sending requires a publicly accessible Scene.",
    "Чтобы отправлять прямо из SCENA, обратитесь в поддержку для подключения своего аккаунта.": "Contact the team to connect your account for direct sending.",
    "Проверить аккаунт": "Verify account", "Посмотреть перед отправкой": "Preview before sending",
    "Instagram обрабатывает фотографию. Продолжите отправку примерно через минуту.": "Instagram is processing the photograph. Continue sending in about a minute.",
    "Фотография для отправки": "Photograph to send", "Если фотография уже размещена в интернете, укажите её ссылку. Иначе скачайте готовый материал ниже.": "If your photograph is hosted online, enter its link. Otherwise download the prepared material below.",
    "Ссылка на фотографию SCENA": "SCENA photograph link", "Вариант сохранён. Он останется после закрытия кабинета.": "Version saved. It remains available after you close your workspace.",
    "Адрес сайта или язык изменился. Сохраните вариант заново перед отправкой.": "The site address or language changed. Save this version again before sending.",
    "Для скачивания загрузите фотографию через редактор публикации — отдельная версия с лейблом SCENA появится автоматически.": "Upload a photograph in the post editor to prepare a downloadable version with the SCENA label.",
    "Аккаунт для отправки: ": "Destination account: ", "Перед отправкой сначала опубликуйте материал в своей Сцене.": "Publish the post on your Scene before sending it.",
    "Проверка отправки": "Review delivery", "Проверить ссылку на мою публикацию": "Check my publication link", "История отправок": "Delivery history",
    "Результат пока неизвестен. Проверьте свою страницу; автоматического повтора не будет.": "The result is unknown. Check your page; this will not be sent again automatically.",
    "Аккаунт подтверждён: ": "Verified account: ", "Не удалось подтвердить аккаунт. Обратитесь к оператору SCENA.": "We could not verify the account. Contact the SCENA team.",
    "Перед отправкой подтвердите, что подключён именно ваш аккаунт.": "Verify that the connected account belongs to you before sending.",
    "Проверила фото, подпись, актуальность цены и аккаунт. Разрешаю публикацию.": "I checked the photograph, caption, current price and destination account. I approve publishing.",
    "Отправка не подтверждена. Проверьте подключение и материал.": "Delivery was not confirmed. Check the connection and content.", "Отправить в ": "Send to ",
    "Открыть": "Open", "Продолжить отправку": "Continue sending", "Проверить результат без повтора": "Check result without resending",
    "Подготовлено":"Prepared", "Не подключено":"Account connection required", "Отправляется":"Sending", "Проверяется":"Checking", "Обрабатывается":"Processing", "Опубликовано":"Published", "Результат неизвестен":"Unknown result", "Ошибка отправки":"Delivery error", "Требует проверки":"Needs review",
}


def _tr(locale, ru, ro, en=None):
    return translate(locale, ru, ro, en or _EN.get(ru))


def _branded_path(app_dir, relative):
    base = Path(app_dir).resolve()
    path = (base / str(relative)).resolve()
    folder = base / "media" / "publications"
    if not path.is_relative_to(folder) or path.name != "scena-publication.jpg" or not path.is_file():
        raise PublicationValidationError("Сначала загрузите фотографию в редакторе публикации: SCENA подготовит отдельную версию с лейблом.")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise PublicationValidationError("Подготовленная фотография превышает 20 МБ.")
    return path


def build_social_export(app_dir, image_url, caption, *, original_image_path="", frame_style="auto", frame_format=None):
    """Export only the prepared image and reviewed caption, never originals/DB."""
    image_path = _branded_path(app_dir, image_url)
    image_bytes = image_path.read_bytes()
    if frame_format:
        original = managed_original(app_dir, original_image_path)
        image_bytes = render_publication_image(app_dir, original.read_bytes(), frame_style=frame_style, frame_format=frame_format)
    package = BytesIO()
    with ZipFile(package, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("scena-publication.jpg", image_bytes)
        archive.writestr("caption.txt", str(caption).encode("utf-8"))
    return package.getvalue()


def public_post_url(settings, public_id, locale):
    base = str(settings.get("public_base_url", "")).strip()
    if not is_public_https_url(base):
        return ""
    parts = urlsplit(base)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + "/", urlencode({"page": "post", "post": public_id, "lang": locale}), ""))


def _default_caption(post, locale, return_url, author_name=""):
    elements = [post.get("title_" + locale, ""), post.get("body_" + locale, "")]
    if post.get("price_text"):
        elements.append(post.get("price_text", ""))
    if author_name:
        elements.append(author_name)
    if return_url:
        elements.append(return_url)
    return "\n\n".join(value.strip() for value in elements if value and value.strip())


def _show_result(result, locale):
    status = result.get("status")
    if status == "sent":
        st.success(_tr(locale, "Площадка подтвердила публикацию.", "Platforma a confirmat publicarea."))
    elif status == "processing":
        st.info(_tr(locale, "Instagram обрабатывает фотографию. Продолжите отправку примерно через минуту.", "Instagram procesează fotografia. Continuați trimiterea peste aproximativ un minut."))
    elif status in {"unknown", "sending", "checking"}:
        st.warning(_tr(locale, "Результат пока неизвестен. Проверьте свою страницу; автоматического повтора не будет.", "Rezultatul nu este încă cunoscut. Verificați pagina; nu repetăm automat trimiterea."))
    elif status in {"failed", "not_configured"}:
        st.error(_tr(locale, "Отправка не подтверждена. Проверьте подключение и материал.", "Trimiterea nu a fost confirmată. Verificați conexiunea și materialul."))
    if result.get("url"):
        st.link_button(_tr(locale, "Открыть публикацию", "Deschide publicația"), result["url"])


def render_social_workspace(db_path, app_dir, settings, locale, post_id):
    """Scoped editor panel; only explicit verify/send/continue reaches Meta."""
    draft = get_draft(db_path, post_id)
    published = get_publication(db_path, draft["public_id"])
    source = get_private_export_source(db_path, post_id)
    is_published = bool(published and published["status"] == "published")
    st.write(_tr(locale, "Подготовьте вариант для соцсети. Материал и история отправок остаются в SCENA.", "Pregătiți o variantă pentru rețeaua socială. Materialul și istoricul rămân în SCENA."))
    if is_published and draft["has_unpublished_changes"]:
        st.info(_tr(locale, "Для соцсетей используется опубликованная версия. Новые правки сначала опубликуйте в своей Сцене.", "Pentru rețele folosim versiunea publicată. Publicați mai întâi modificările în Scena dvs."))
    channel = st.radio(_tr(locale, "Площадка", "Platformă"), ["facebook", "instagram"], format_func={"facebook": "Facebook Page", "instagram": "Instagram"}.get, horizontal=True, key=f"social_channel_{post_id}")
    key = f"social_{post_id}_{channel}"
    adapter = get_adapters()[channel]
    config = adapter.configuration_status()
    stored = get_channel_draft(db_path, post_id, channel)
    available_locales = [language for language in ("ru", "ro", "en") if source.get("body_"+language)] or [locale]
    initial_locale = (stored or {}).get("locale", locale)
    selected_locale = st.radio(_tr(locale, "Язык публикации", "Limba publicației"), available_locales,
                               index=available_locales.index(initial_locale) if initial_locale in available_locales else 0,
                               format_func=str.upper, horizontal=True, key=key + "_locale")
    return_url = public_post_url(settings, draft["public_id"], selected_locale)
    default_caption = stored["caption"] if stored and stored["locale"] == selected_locale else _default_caption(source, selected_locale, return_url, localized_name(settings, selected_locale))
    with st.form(key + "_draft"):
        caption = st.text_area(_tr(locale, "Подпись для соцсети", "Descriere pentru rețea"), value=default_caption, max_chars=2200, height=180, key=key + "_caption_" + selected_locale)
        with st.expander(_tr(locale, "Фотография для отправки", "Fotografia pentru trimitere")):
            st.caption(_tr(locale, "Если фотография уже размещена в интернете, укажите её ссылку. Иначе скачайте готовый материал ниже.", "Completați după găzduirea JPEG-ului pregătit pe un site public. Fișierul local nu este accesibil Facebook și Instagram."))
            image_url = st.text_input(_tr(locale, "Ссылка на фотографию SCENA", "Link HTTPS către JPEG cu eticheta SCENA"), value=(stored or {}).get("image_url", ""), key=key + "_image_url")
        save = st.form_submit_button(_tr(locale, "Сохранить вариант", "Salvează varianta"), type="primary")
    if save:
        try:
            stored = save_channel_draft(db_path, post_id, channel, caption, selected_locale, image_url, return_url, adapter.account_id if config["configured"] else "")
            st.success(_tr(locale, "Вариант сохранён. Он останется после закрытия кабинета.", "Varianta a fost salvată și rămâne disponibilă după închiderea cabinetului."))
            st.session_state.pop(key + "_preview", None)
        except PublicationValidationError as exc:
            st.error(str(exc))
    if return_url and stored and stored.get("return_url") != return_url:
        st.caption(_tr(locale, "Адрес сайта или язык изменился. Сохраните вариант заново перед отправкой.", "Adresa site-ului sau limba s-a schimbat. Salvați din nou varianta înainte de trimitere."))
    download_caption = stored["caption"] if stored and stored["locale"] == selected_locale else default_caption
    if return_url and return_url not in download_caption:
        download_caption += "\n\n" + return_url
    try:
        branded = _branded_path(app_dir, source.get("image_url", ""))
    except PublicationValidationError:
        branded = None
        st.caption(_tr(locale, "Для скачивания загрузите фотографию через редактор публикации — отдельная версия с лейблом SCENA появится автоматически.", "Pentru descărcare, încărcați fotografia în editor; o versiune separată cu eticheta SCENA va fi creată automat."))
    if branded:
        choices = {"portrait":"4:5 · 1080 × 1350", "tall":"3:4 · 1080 × 1440", "square":"1:1 · 1080 × 1080", "story":"Story · 1080 × 1920"}
        original = None
        if source.get("original_image_path"):
            try:
                original = managed_original(app_dir, source["original_image_path"])
            except (OSError, PublicationValidationError):
                pass
        current_format = source.get("frame_format", "portrait")
        available_formats = list(choices) if original else [current_format]
        render_format = st.pills(_tr(locale, "Формат для скачивания", "Format pentru descărcare", "Download format"),
                                 available_formats, default=current_format, format_func=choices.get,
                                 selection_mode="single", key=key+"_export_format") or current_format
        export_style = source.get("frame_style", "auto")
        export_bytes = branded.read_bytes()
        export_options = {}
        if original:
            export_bytes = render_publication_image(app_dir, original.read_bytes(), frame_style=export_style, frame_format=render_format)
            export_options = {"original_image_path": source["original_image_path"], "frame_style": export_style, "frame_format": render_format}
        st.image(export_bytes, width=330)
        st.text(download_caption)
        st.download_button(_tr(locale, "Скачать фото и подпись", "Descarcă fotografia și descrierea"), build_social_export(app_dir, source["image_url"], download_caption, **export_options), file_name=f"SCENA-{render_format}-{draft['public_id'][:8]}.zip", mime="application/zip", key=key + "_download")

    st.caption(_tr(locale, "Для ленты — 4:5, 3:4 или квадрат. Для Stories скачайте вертикальный вариант и добавьте его в приложении Instagram.", "Pentru feed: 4:5, 3:4 sau pătrat. Pentru Stories, descarcă varianta verticală și adaug-o în aplicația Instagram.", "Choose 4:5, 3:4 or square for your feed. Download the vertical version for Stories and add it in the Instagram app."))
    if not config["configured"]:
        with st.expander(_tr(locale, "Отправка прямо в ленту", "Trimite direct în feed", "Send directly to your feed")):
            st.link_button(_tr(locale, "Подключить Facebook или Instagram", "Conectează Facebook sau Instagram", "Connect Facebook or Instagram"), "?page=admin&section=help&view=support")
    else:
        st.write(_tr(locale, "Аккаунт для отправки: ", "Cont pentru trimitere: ") + config["account_id"])
        verification_key = key + "_verified_" + config["fingerprint"]
        if st.button(_tr(locale, "Проверить аккаунт", "Verifică contul"), key=key + "_verify"):
            # This is the sole read-only identity verification call in this UI.
            st.session_state[verification_key] = adapter.verify_account()
        verification = st.session_state.get(verification_key, {})
        if verification.get("verified"):
            st.success(_tr(locale, "Аккаунт подтверждён: ", "Cont confirmat: ") + verification.get("display_name", config["account_id"]))
        elif verification:
            st.error(_tr(locale, "Не удалось подтвердить аккаунт. Обратитесь к оператору SCENA.", "Contul nu a putut fi confirmat. Contactați operatorul SCENA."))
        else:
            st.caption(_tr(locale, "Перед отправкой подтвердите, что подключён именно ваш аккаунт.", "Înainte de trimitere, verificați că este conectat contul dvs."))
        ready = bool(verification.get("verified") and is_published and stored and stored.get("return_url") == return_url and return_url and is_public_https_url(stored.get("image_url", "")))
        if not is_published:
            st.caption(_tr(locale, "Перед отправкой сначала опубликуйте материал в своей Сцене.", "Înainte de trimitere, publicați materialul în Scena dvs."))
        if st.button(_tr(locale, "Посмотреть перед отправкой", "Previzualizează trimiterea"), disabled=not ready, key=key + "_prepare"):
            try:
                prepared = prepare_delivery(db_path, post_id, channel, stored["caption"], stored["image_url"], return_url, adapter.account_id, config["fingerprint"])
                st.session_state[key + "_preview"] = prepared["id"]
            except PublicationValidationError as exc:
                st.error(str(exc))
        preview_id = st.session_state.get(key + "_preview")
        if preview_id:
            delivery = get_delivery(db_path, preview_id)
            exact = delivery["snapshot"]
            st.write(_tr(locale, "Проверка отправки", "Verificarea trimiterii"))
            st.caption(f"{channel.title()} · {exact['account_id']}")
            st.image(exact["image_url"], width=280)
            st.text(exact["caption"])
            st.link_button(_tr(locale, "Проверить ссылку на мою публикацию", "Verifică linkul spre publicația mea"), exact["return_url"])
            if delivery["status"] in {"prepared", "not_configured"}:
                confirmed = st.checkbox(_tr(locale, "Проверила фото, подпись, актуальность цены и аккаунт. Разрешаю публикацию.", "Am verificat fotografia, descrierea, prețul actual și contul. Autorizez publicarea."), key=key + "_confirm_" + delivery["snapshot_hash"])
                if st.button(_tr(locale, "Отправить в ", "Trimite pe ") + channel.title(), disabled=not confirmed, type="primary", key=key + "_send_" + delivery["id"]):
                    try:
                        delivery = dispatch_delivery(db_path, delivery["id"], adapter, delivery["snapshot_hash"], confirmed=True)
                    except PublicationValidationError as exc:
                        st.error(str(exc))
            _show_result(delivery, locale)

    history = [row for row in list_deliveries(db_path, post_id) if row["channel"] == channel]
    if history:
        with st.expander(_tr(locale, "История отправок", "Istoricul trimiterilor")):
            labels = {"prepared": ("Подготовлено", "Pregătit"), "not_configured": ("Не подключено", "Neconectat"), "sending": ("Отправляется", "Se trimite"), "checking": ("Проверяется", "Se verifică"), "processing": ("Обрабатывается", "Se procesează"), "sent": ("Опубликовано", "Publicat"), "unknown": ("Результат неизвестен", "Rezultat necunoscut"), "failed": ("Ошибка отправки", "Eroare la trimitere")}
            for delivery in history[:20]:
                state_label = _tr(locale, *labels.get(delivery["status"], ("Требует проверки", "Necesită verificare")))
                st.write(delivery["created_at"][:16].replace("T", " ") + " · " + state_label)
                if delivery.get("url"):
                    st.link_button(_tr(locale, "Открыть", "Deschide"), delivery["url"])
                if channel == "instagram" and delivery["status"] in {"processing", "unknown"} and delivery.get("container_id"):
                    label = _tr(locale, "Продолжить отправку", "Continuă trimiterea") if delivery["status"] == "processing" else _tr(locale, "Проверить результат без повтора", "Verifică rezultatul fără retrimitere")
                    if st.button(label, key=key + "_refresh_" + delivery["id"], disabled=not config["configured"]):
                        try:
                            result = refresh_delivery(db_path, delivery["id"], adapter, delivery["snapshot_hash"], confirmed=True)
                            _show_result(result, locale)
                        except PublicationValidationError as exc:
                            st.error(str(exc))
