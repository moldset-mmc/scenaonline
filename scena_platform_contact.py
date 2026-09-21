"""PRO enquiries use only the platform's explicitly configured recipient."""
import os
import uuid

from scena_integrations import TelegramBotAdapter


class PlatformTelegram(TelegramBotAdapter):
    @property
    def configured(self):
        # Sending to the platform channel needs no incoming-reply allowlist.
        return bool(self.bot_token and self.admin_chat_id)


def platform_adapter():
    return PlatformTelegram(bot_token=os.environ.get('SCENA_PLATFORM_TELEGRAM_BOT_TOKEN', ''),
                            admin_chat_id=os.environ.get('SCENA_PLATFORM_TELEGRAM_CHAT_ID', ''))


def render_pro_contact(db, profile, locale):
    from scena_ui import st
    from scena_i18n import tr
    from scena_cabinet import submit_support_message, dispatch_support_notifications, CabinetValidationError
    text = lambda ru, ro, en: tr(locale, ru, ro, en)
    if st.button(text('Обсудить продление с SCENA','Discută reînnoirea cu SCENA','Discuss renewal with SCENA'), key='pro_contact_support', width='stretch'):
        st.session_state['pro_contact_open'] = True
    if not st.session_state.get('pro_contact_open'):
        return
    adapter = platform_adapter()
    if not adapter.configured:
        st.info(text('Канал команды SCENA ещё не подключён. Отправка станет доступна после его настройки.',
                     'Canalul echipei SCENA nu este încă conectat. Trimiterea va fi disponibilă după configurare.',
                     'The SCENA team channel is not connected yet. Sending becomes available after setup.'))
        return
    st.caption(text('Сообщение будет отправлено команде платформы SCENA в Telegram.',
                    'Mesajul va fi trimis echipei platformei SCENA în Telegram.',
                    'Your message will be sent to the SCENA platform team on Telegram.'))
    request_key = st.session_state.setdefault('pro_contact_request', uuid.uuid4().hex)
    with st.form('pro_contact_form'):
        contact = st.text_input(text('Ваш Telegram для ответа','Telegram pentru răspuns','Your Telegram for a reply'), placeholder='@username', key='pro_reply_'+request_key)
        body = st.text_area(text('Сообщение команде SCENA','Mesaj pentru echipa SCENA','Message to the SCENA team'),
                            value=text('Хочу обсудить продление PRO.','Doresc să discut reînnoirea PRO.','I would like to discuss my PRO renewal.'),
                            max_chars=3500, key='pro_message_'+request_key)
        submitted = st.form_submit_button(text('Отправить в Telegram SCENA','Trimite în Telegram SCENA','Send to SCENA Telegram'), type='primary')
    if submitted:
        try:
            message = submit_support_message(db, f'PRO · {profile}\n\n{body}', reply_channel='telegram', contact=contact,
                                             locale=locale, request_key=request_key)
            result = dispatch_support_notifications(db, adapter, message_id=message['id'])
            if result['sent'] or message.get('delivery_status') == 'sent':
                st.success(text('Сообщение доставлено команде SCENA.','Mesaj livrat echipei SCENA.','Message delivered to the SCENA team.'))
                st.session_state['pro_contact_request'] = uuid.uuid4().hex
            else:
                st.warning(text('Доставка не подтверждена. Сообщение сохранено; можно повторить отправку.',
                                'Livrarea nu este confirmată. Mesajul este salvat; puteți reîncerca.',
                                'Delivery is unconfirmed. Your message is saved; you can retry.'))
        except CabinetValidationError:
            st.error(text('Проверьте сообщение и ваш @username.','Verificați mesajul și @username.','Check your message and @username.'))
