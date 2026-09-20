"""Owner-only editor mounted inside the existing Pages cabinet."""
import base64
from pathlib import Path
import sqlite3

from scena_business_card import CARD_URL, get_card, portrait_bytes, render_card, save_card, validate_card
from scena_i18n import tr
from scena_ui import st


def render_card_editor(db_path, app_dir, locale):
    from scena_model_intro import _original
    from scena_photo_library import catalog
    from model_landing import image_uri

    def t(ru, ro, en):
        return tr(locale, ru, ro, en)

    key = 'business_card_editor'
    source = st.session_state.setdefault(key + '_source', get_card(db_path))
    revision = st.session_state.get(key + '_revision', 0)
    if st.session_state.pop(key + '_saved', False):
        st.success(t('Визитка сохранена. Страница и скачиваемый контакт обновлены.',
                     'Cartea de vizită a fost salvată. Pagina și contactul descărcabil au fost actualizate.',
                     'Card saved. The page and downloadable contact are updated.'))
    st.caption(t('У визитки свои данные. Изменения имени, фото и контактов на основных страницах сайта сюда не переносятся.',
                 'Cartea de vizită are propriile date. Modificările de pe paginile site-ului nu se transferă aici.',
                 'This card has its own data. Changes to the main website pages do not carry over here.'))
    fields, preview_column = st.columns([1.1, 1])
    values = {}
    with fields:
        with st.form(key + '_' + str(revision)):
            for field, label, limit in [
                ('first_name', t('Имя', 'Prenume', 'First name'), 60),
                ('last_name', t('Фамилия', 'Nume', 'Last name'), 80),
                ('profession', t('Профессия или подпись', 'Profesie sau subtitlu', 'Profession or subtitle'), 80),
                ('tagline', t('Короткая фраза', 'Slogan scurt', 'Short tagline'), 160),
            ]:
                values[field] = st.text_input(label, value=source[field], max_chars=limit)
            with st.expander(t('Фото визитки', 'Fotografia cărții de vizită', 'Card photo')):
                upload = st.file_uploader(t('Загрузить фото', 'Încarcă o fotografie', 'Upload a photo'), type=['jpg', 'jpeg', 'png', 'webp'])
                st.caption(t('До 20 МБ. Минимум 400 × 600 px. Новое фото будет видно только после сохранения.',
                             'Până la 20 MB. Minimum 400 × 600 px. Fotografia nouă apare public după salvare.',
                             'Up to 20 MB. At least 400 × 600 px. A new photo becomes public after saving.'))
                photos = catalog(db_path, app_dir, locale)
                names = {row['path']: row['name'] for row in photos}
                labels = {'__current__': t('Оставить текущее фото', 'Păstrează fotografia actuală', 'Keep current photo'),
                          '__default__': t('Начальный портрет MBStudio', 'Portretul inițial MBStudio', 'Original MBStudio portrait'), **names}
                choice = st.selectbox(t('Выбрать из медиатеки', 'Alege din bibliotecă', 'Choose from photo library'), list(labels), format_func=labels.get)
                values['photo'] = source['photo'] if choice == '__current__' else '' if choice == '__default__' else choice
            with st.expander(t('Кнопка и ссылки', 'Buton și linkuri', 'Button and links')):
                for field, label in [
                    ('primary_label', t('Название основной кнопки', 'Textul butonului principal', 'Primary button label')),
                    ('primary_url', t('Ссылка основной кнопки', 'Linkul butonului principal', 'Primary button link')),
                    ('site_url', t('Сайт', 'Site web', 'Website')),
                    ('instagram_url', 'Instagram'), ('telegram_url', 'Telegram'),
                ]:
                    values[field] = st.text_input(label, value=source[field], max_chars=50 if field == 'primary_label' else 2048)
                st.caption(t('Ссылки начинаются с https://. Пустые ссылки не показываются. Чтобы убрать основную кнопку, очистите её название и ссылку.',
                             'Linkurile încep cu https://. Câmpurile goale nu apar. Pentru a elimina butonul principal, golește textul și linkul.',
                             'Links start with https://. Empty links are hidden. Clear both the label and link to remove the primary button.'))
            with st.expander(t('Контакты', 'Contacte', 'Contact details')):
                values['phone'] = st.text_input(t('Телефон с кодом страны', 'Telefon cu prefix de țară', 'Phone with country code'), value=source['phone'], max_chars=40)
                values['email'] = st.text_input('Email', value=source['email'], max_chars=254)
                st.caption(t('Заполненные контакты видны в визитке и попадают в скачиваемый файл контакта.',
                             'Contactele completate apar pe cartea de vizită și în fișierul de contact.',
                             'These details appear on the card and in the downloadable contact file.'))
            preview_clicked = st.form_submit_button(t('Обновить предпросмотр', 'Actualizează previzualizarea', 'Update preview'), width='stretch')
            st.caption(t('Сохранение сразу обновляет публичную визитку. Ссылка, QR-код и NFC-метка остаются прежними.',
                         'Salvarea actualizează imediat cartea publică. Linkul, codul QR și eticheta NFC rămân aceleași.',
                         'Saving updates the public card immediately. Its link, QR code and NFC tag stay the same.'))
            submitted = st.form_submit_button(t('Сохранить визитку', 'Salvează cartea de vizită', 'Save business card'), type='primary', width='stretch')
        if submitted:
            try:
                saved = save_card(db_path, app_dir, values, expected=source, upload=upload.getvalue() if upload else None)
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(t(str(exc) if isinstance(exc, ValueError) else 'Не удалось сохранить визитку. Повторите попытку.',
                           'Nu s-a putut salva. Verifică datele și încearcă din nou. Dacă altă fereastră a salvat modificări, reîncarcă editorul.',
                           'Could not save. Check the fields and try again. If another window saved changes, reload the editor.'))
            else:
                st.session_state[key + '_source'] = saved
                st.session_state[key + '_revision'] = revision + 1
                st.session_state[key + '_saved'] = True
                st.rerun()
        if st.button(t('Обновить редактор из сохранённых данных', 'Reîncarcă datele salvate', 'Reload saved data')):
            st.session_state.pop(key + '_source', None)
            st.session_state[key + '_revision'] = revision + 1
            st.rerun()
    with preview_column:
        st.subheader(t('Предпросмотр', 'Previzualizare', 'Preview'))
        proposed = source
        photo = None
        try:
            proposed = validate_card(values)
            if upload:
                data = upload.getvalue()
                _original(data)
                photo = 'data:image/webp;base64,' + base64.b64encode(portrait_bytes(data)).decode()
            elif proposed['photo']:
                photo = image_uri(Path(app_dir), proposed['photo'])
            else:
                photo = '/card/assets/portrait.webp'
        except (ValueError, OSError) as exc:
            if preview_clicked:
                st.error(t(str(exc), 'Verifică datele pentru previzualizare.', 'Check the fields to update the preview.'))
            proposed = source
        st.iframe(render_card(proposed, preview=True, photo_url=photo), height=850)
        st.link_button(t('Открыть опубликованную визитку', 'Deschide cartea publicată', 'Open published card'), '/card/', width='stretch')
        st.caption(CARD_URL)
        st.caption(t('Контакт, уже сохранённый в телефоне получателя, автоматически не обновляется.',
                     'Contactul deja salvat în telefonul destinatarului nu se actualizează automat.',
                     'A contact already saved on someone’s phone does not update automatically.'))
