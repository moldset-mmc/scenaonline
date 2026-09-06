"""Owner-only, on-demand backups and a separate public interchange preview."""

from __future__ import annotations
from scena_i18n import translate_literaltext

import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st

from scena_transfer import (
    TransferValidationError,
    build_backup,
    build_platform_export,
    inspect_backup,
)


def ui(value):
    return translate_literaltext(st.session_state.get("scena_ui_locale", "ru"), value)

def _summary(summary: dict) -> None:
    size_mb = summary["total_bytes"] / (1024 * 1024)
    st.caption(
        f"{ui('Файлов: ')}{summary['file_count']}{ui(' · Материалов: ')}{summary['media_count']}{ui(' · Размер после распаковки: ')}{size_mb:.1f}{ui(' МБ')}"
    )
    for warning in summary.get("warnings", []):
        st.warning(ui(str(warning)))


def _export_panel(db_path: Path, app_dir: Path, prefix: str, *, public: bool) -> None:
    state_key = prefix + ("_public_export" if public else "_backup")
    builder = build_platform_export if public else build_backup
    action = "Подготовить публичный пакет" if public else "Создать резервную копию"
    st.write(
        ui('Только опубликованные страницы, услуги, посты и связанные сохранённые материалы. Клиенты, переписка и черновики сюда не входят.') if public else ui('Сохраните свою Сцену: настройки, услуги, записи, публикации и сохранённые фотографии. Копия содержит личные данные клиентов и переписку — храните её у себя.')
    )
    if public:
        st.info(
            ui('Это файл для будущего переноса. Подключение и синхронизация с платформой ещё не реализованы. Ничего не отправляется автоматически.')
        )
    if st.button(ui(action), key=state_key + "_create"):
        st.session_state.pop(state_key, None)
        try:
            with st.spinner(ui('Подготавливаем материалы…')):
                data = builder(db_path, app_dir / "media")
                summary = inspect_backup(data)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            name = "SCENA-PUBLIC" if public else "SCENA-BACKUP"
            st.session_state[state_key] = {
                "data": data, "summary": summary,
                "filename": f"{name}-{timestamp}.zip",
                "created": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            }
        except TransferValidationError as exc:
            st.error(ui(str(exc)))
        except OSError:
            st.error(ui('Не удалось прочитать файлы. Проверьте доступ к папке SCENA и повторите.'))
    package = st.session_state.get(state_key)
    if package:
        st.success(f"{ui('Пакет подготовлен: ')}{package['created']}.")
        _summary(package["summary"])
        st.download_button(
            ui('Скачать публичный пакет') if public else ui('Скачать резервную копию'),
            data=package["data"], file_name=package["filename"], mime="application/zip",
            key=state_key + "_download", on_click="ignore",
        )
        st.caption(ui('После новых изменений создайте свежую копию кнопкой выше.'))


def _restore_panel(app_dir: Path, prefix: str) -> None:
    st.write(
        ui('Выберите ранее скачанную резервную копию SCENA. Восстановленная Сцена появится в отдельной папке рядом с текущей.')
    )
    upload = st.file_uploader(
        ui('Резервная копия SCENA (.zip)'), type=["zip"],
        key=prefix + "_upload", max_upload_size=512,
    )
    preview_key = prefix + "_restore_preview"
    result_key = prefix + "_restore_result"
    if upload is None:
        st.session_state.pop(preview_key, None)
        return
    data = upload.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    preview = st.session_state.get(preview_key)
    if preview and preview["digest"] != digest:
        st.session_state.pop(preview_key, None)
        preview = None
    if st.button(ui('Проверить архив и показать восстановление'), key=prefix + "_inspect"):
        st.session_state.pop(preview_key, None)
        st.session_state.pop(result_key, None)
        preview = None
        try:
            with st.spinner(ui('Проверяем архив…')):
                summary = inspect_backup(data)
            if summary["kind"] != "private_backup":
                raise TransferValidationError(
                    "Это публичный пакет. Для восстановления нужна полная резервная копия SCENA."
                )
            suffix = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
            destination = app_dir.parent / ("SCENA-RESTORED-" + suffix)
            preview = {
                "digest": digest, "destination": str(destination),
                "summary": summary, "confirmation_id": uuid4().hex,
            }
            st.session_state[preview_key] = preview
        except TransferValidationError as exc:
            st.error(ui(str(exc)))
        except OSError:
            st.error(ui('Не удалось проверить архив. Проверьте доступ к диску и повторите.'))
    if preview:
        st.success(ui('Архив проверен. Можно восстановить отдельную Сцену.'))
        _summary(preview["summary"])
        st.write(ui('Будет создана новая папка:'))
        st.text(preview["destination"])
        st.caption(
            ui('Текущая Сцена продолжит работать. Подключения к внешним сервисам в новой установке нужно настроить отдельно.')
        )
        confirmation_key = prefix + "_confirm_" + preview["confirmation_id"]
        confirmed = st.checkbox(
            ui('Восстановить выбранный архив в указанную новую папку'),
            key=confirmation_key,
        )
        if st.button(
            ui('Восстановить отдельную Сцену'), key=prefix + "_restore",
            disabled=not confirmed, type="primary",
        ):
            try:
                from scena_restore import restore_installation

                with st.spinner(ui('Восстанавливаем вашу Сцену…')):
                    result = restore_installation(data, app_dir, Path(preview["destination"]))
                st.session_state[result_key] = {
                    "digest": digest, "directory": str(result["destination"]),
                }
                st.session_state.pop(preview_key, None)
                st.rerun()
            except TransferValidationError as exc:
                st.error(ui(str(exc)))
            except OSError:
                st.error(
                    ui('Не удалось создать новую Сцену. Проверьте свободное место и доступ к папке, затем повторите.')
                )
    result = st.session_state.get(result_key)
    if result and result["digest"] == digest:
        st.success(ui('Ваша Сцена восстановлена в отдельной папке.'))
        st.text(result["directory"])
        st.write(ui('Откройте эту папку и запустите START-SCENA.cmd.'))


def render_transfer_workspace(db_path, app_dir) -> None:
    """Render in an already authenticated cabinet; never publish or send data."""
    root = Path(app_dir).resolve()
    prefix = "scena_transfer_" + hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
    st.subheader(ui('Резервная копия и перенос'))
    st.caption(ui('Ваши материалы остаются с вами. Выберите нужное действие.'))
    with st.expander(ui('Сохранить свою Сцену'), expanded=True):
        _export_panel(Path(db_path), root, prefix, public=False)
    with st.expander(ui('Восстановить из резервной копии')):
        _restore_panel(root, prefix)
    with st.expander(ui('Подготовить материалы для будущей платформы')):
        _export_panel(Path(db_path), root, prefix, public=True)
