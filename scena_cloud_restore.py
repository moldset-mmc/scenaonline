"""Validate and stage a backup before atomically restoring the cloud database."""
from pathlib import Path
import sqlite3
import tempfile

from scena_database import connect
from scena_transfer import BACKUP_TABLES, TransferValidationError, restore_backup


def restore_cloud(data, db_path, app_dir):
    from scena_core import init_db
    from scena_model_builder import init_model_builder
    from scena_media import persist, hydrate
    with tempfile.TemporaryDirectory(prefix='scena-cloud-restore-') as folder:
        staging = Path(folder) / 'validated'
        restore_backup(data, staging)
        init_db(staging / 'scena_master.db')
        init_model_builder(staging / 'scena_master.db')
        local = sqlite3.connect(staging / 'scena_master.db')
        remote = None
        try:
            local.execute('''CREATE TABLE IF NOT EXISTS scena_media_files (
                path TEXT PRIMARY KEY, private_url TEXT NOT NULL,
                sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
                public_url TEXT NOT NULL DEFAULT '')''')
            # Ignore URLs from another installation; use the validated archive bytes.
            local.execute('DELETE FROM scena_media_files')
            for path in sorted((staging / 'media').rglob('*')):
                if path.is_file():
                    persist(path, staging, connection=local)
            local.commit()
            init_model_builder(db_path)
            remote = connect(db_path, timeout=30)
            cloud_meta = remote.execute("SELECT key,value FROM app_meta WHERE key LIKE 'cloud_%'").fetchall()
            tables = [r[0] for r in remote.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] in BACKUP_TABLES and r[0] != 'sqlite_sequence']
            source_tables = {r[0] for r in local.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            remote.execute('PRAGMA foreign_keys=OFF')
            remote.execute('BEGIN IMMEDIATE')
            for table in tables:
                remote.execute('DELETE FROM "' + table + '"')
            for table in tables:
                if table not in source_tables:
                    continue
                source_columns = {r[1] for r in local.execute('PRAGMA table_info("' + table + '")')}
                columns = [r[1] for r in remote.execute('PRAGMA table_info("' + table + '")') if r[1] in source_columns]
                quoted = ','.join('"' + c.replace('"', '""') + '"' for c in columns)
                remote.executemany('INSERT INTO "' + table + '" (' + quoted + ') VALUES (' + ','.join('?' for _ in columns) + ')', local.execute('SELECT ' + quoted + ' FROM "' + table + '"').fetchall())
            remote.executemany('INSERT INTO app_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', cloud_meta)
            if remote.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise TransferValidationError('Связи данных в архиве повреждены. Текущая Сцена сохранена.')
            remote.commit()
        except Exception:
            if remote:
                remote.rollback()
            raise
        finally:
            local.close()
            if remote:
                remote.close()
        hydrate(app_dir, force=True)


def render_cloud_restore(db_path, app_dir):
    from scena_ui import st
    from scena_transfer import inspect_backup
    st.write('Восстановите настройки, записи и фотографии из личной резервной копии SCENA.')
    upload = st.file_uploader('Резервная копия SCENA (.zip)', type=['zip'], key='cloud_restore_upload')
    if upload is None:
        return
    data = upload.getvalue()
    try:
        summary = inspect_backup(data)
    except TransferValidationError as exc:
        st.error(str(exc))
        return
    st.write(f"Сцена: {summary['owner_name']}. Файлов: {summary['file_count']}.")
    confirmed = st.checkbox('Заменить данные текущей Сцены данными из этой резервной копии')
    if st.button('Восстановить данные', disabled=not confirmed):
        try:
            with st.spinner('Восстанавливаем данные и фотографии…'):
                restore_cloud(data, db_path, app_dir)
            st.success('Данные восстановлены. Обновите страницу кабинета.')
        except Exception:
            st.error('Не удалось завершить восстановление. Проверьте подключение и повторите попытку.')
