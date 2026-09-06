"""Mobile-first conversations for the owner's assistant and the SCENA team."""
from __future__ import annotations

import uuid
from pathlib import Path


def _t(locale, ru, ro, en):
    return {"ru": ru, "ro": ro, "en": en}.get(locale, ru)


def local_guide_answer(question: str, context: dict, locale: str = "ru") -> str:
    """Deterministic navigation help, explicitly identified as a guide, never AI."""
    text = question.casefold()
    pages = context.get("pages", {})
    services = pages.get("professional", {}).get("published_services", 0)
    posts = context.get("promotion", {}).get("published_posts", 0)
    intro = _t(locale, "Подсказка SCENA", "Ghid SCENA", "SCENA guide")
    if any(word in text for word in ("услуг", "цен", "service", "servici", "price", "preț", "групп", "group", "grup")):
        answer = _t(locale,
            f"У вас опубликовано профессиональных услуг: {services}. Откройте «Работа → Услуги», выберите услугу и отредактируйте название, описание, цену и длительность. Для объединения услуг выберите одну группу. Перед публикацией проверьте языковые версии.",
            f"Aveți {services} servicii profesionale publicate. Deschideți «Activitate → Servicii», alegeți un serviciu și modificați numele, descrierea, prețul și durata. Selectați același grup pentru servicii înrudite. Verificați versiunile lingvistice înainte de publicare.",
            f"You have {services} published professional services. Open “Work → Services”, select a service and edit its name, description, price and duration. Use the same group for related services. Check the language versions before publishing.")
    elif any(word in text for word in ("врем", "график", "дат", "schedule", "calendar", "orar", "program", "slot", "time")):
        answer = _t(locale,
            "Откройте «Работа → График». Выберите дату и откройте подходящие интервалы. Клиенты увидят свободное время с учётом длительности услуги. Новые обращения проверяйте в «Работа → Заявки»: подтвердите подходящую запись лично.",
            "Deschideți «Activitate → Program». Alegeți data și deschideți intervalele potrivite. Clienții vor vedea orele libere în funcție de durata serviciului. Verificați cererile noi în «Activitate → Solicitări» și confirmați personal programarea.",
            "Open “Work → Schedule”. Choose a date and open suitable time slots. Clients see available times based on the service duration. Check new requests in “Work → Requests” and confirm each suitable booking yourself.")
    elif any(word in text for word in ("model", "модел", "образ", "image", "portret", "портрет")):
        answer = _t(locale,
            "Откройте «Страницы → Model». Начните со знакомства: отдельный портрет и несколько строк о себе. Затем выберите образы, порядок и личные подписи. В «Продвижение → Промпты» можно подготовить задание для своего AI. Перед публикацией откройте предпросмотр на телефоне и компьютере.",
            "Deschideți «Pagini → Model». Începeți cu prezentarea: un portret separat și câteva rânduri despre dvs. Apoi alegeți imaginile, ordinea și textele personale. În «Promovare → Prompturi» pregătiți instrucțiuni pentru propriul AI. Verificați pagina pe telefon și calculator înainte de publicare.",
            "Open “Pages → Model”. Start with your introduction: a separate portrait and a few lines about yourself. Then choose images, their order and personal captions. Use “Promotion → Prompts” to prepare instructions for your AI. Preview on a phone and computer before publishing.")
    elif any(word in text for word in ("qr", "ссыл", "link", "adres", "адрес")):
        answer = _t(locale,
            "Откройте «Продвижение → QR-коды». Каждый код ведёт на своё направление: запись, Моя Сцена, профессиональная страница или Model. Проверьте публичную ссылку с телефона, затем скачайте нужный QR-код. Поле «Адрес страницы» — короткое имя вашей личной ссылки.",
            "Deschideți «Promovare → Coduri QR». Fiecare cod duce la o destinație: programare, Scena mea, pagina profesională sau Model. Verificați linkul public de pe telefon și descărcați codul dorit. «Adresa paginii» este numele scurt al linkului personal.",
            "Open “Promotion → QR codes”. Each code opens a different destination: booking, My Scene, the professional page or Model. Check the public link from a phone, then download the QR code. “Page address” is the short name used for your personal link.")
    elif any(word in text for word in ("пост", "публик", "продвиж", "post", "promov", "instagram")):
        answer = _t(locale,
            f"У вас активных публикаций: {posts}. В «Продвижение → Публикации» выберите фотографию, напишите короткую историю и добавьте конкретное предложение с ценой. Проверьте оформление и ссылку перед публикацией. Для следующего поста можно показать одну работу и объяснить, кому она подходит.",
            f"Aveți {posts} publicații active. În «Promovare → Publicații», alegeți o fotografie, scrieți o poveste scurtă și adăugați o ofertă concretă cu preț. Verificați aspectul și linkul înainte de publicare. Următoarea postare poate prezenta o lucrare și persoana căreia i se potrivește.",
            f"You have {posts} active posts. In “Promotion → Posts”, choose a photo, write a short story and add a specific offer with its price. Check the design and link before publishing. Your next post could show one piece of work and explain who it suits.")
    elif any(word in text for word in ("shop", "market", "шоп", "магаз", "маркет", "товар", "magazin", "produs")):
        answer = _t(locale,
            "Откройте «Страницы → Market». Добавьте товар, фотографию, цену и своё объяснение: почему рекомендуете его и кому он подходит. Проверьте условия получения товара и опубликуйте карточку. Заявки на товар проверяйте во вкладке «Заказы» магазина.",
            "Deschideți «Pagini → Market». Adăugați produsul, fotografia, prețul și recomandarea dvs.: de ce îl recomandați și cui i se potrivește. Verificați condițiile de primire și publicați fișa. Consultați solicitările în fila «Comenzi».",
            "Open “Pages → Market”. Add a product, photo, price and your recommendation: why you chose it and who it suits. Check collection or delivery terms and publish the card. Review product requests in the store’s “Orders” tab.")
    elif any(word in text for word in ("pro", "продл", "подпис", "abon", "subscription")):
        status = context.get("membership", {})
        answer = _t(locale,
            f"Ваш режим: {status.get('label', 'FREE')}. Откройте страницу PRO: там указаны возможности, срок доступа и продление. Созданные фотографии и тексты остаются вашими; завершение подписки само по себе их не удаляет.",
            f"Planul dvs.: {status.get('label', 'FREE')}. Deschideți pagina PRO pentru funcții, perioada de acces și reînnoire. Fotografiile și textele create rămân ale dvs.; expirarea abonamentului nu le șterge.",
            f"Your plan: {status.get('label', 'FREE')}. Open PRO for features, access dates and renewal. Your photos and text remain yours; an expired subscription does not delete them.")
    else:
        if not pages.get("scene", {}).get("has_bio"):
            answer = _t(locale, "Начните с «Страницы → Моя Сцена»: добавьте несколько строк о себе и главное фото. Затем откройте предпросмотр и проверьте первое впечатление с телефона.", "Începeți cu «Pagini → Scena mea»: adăugați câteva rânduri despre dvs. și fotografia principală. Apoi previzualizați pagina pe telefon.", "Start with “Pages → My Scene”: add a few lines about yourself and your main photo. Then preview the first impression on a phone.")
        else:
            answer = _t(locale,
                f"Личная история заполнена. Сейчас у вас профессиональных услуг: {services}, активных публикаций: {posts}. Могу подсказать шаги для услуг, графика, Model, Shop, публикаций или QR-кодов. Напишите, с чем хотите разобраться.",
                f"Povestea personală este completată. Aveți {services} servicii profesionale și {posts} publicații active. Vă pot ghida prin servicii, program, Model, Shop, publicații sau coduri QR. Scrieți ce doriți să clarificați.",
                f"Your personal story is filled in. You have {services} professional services and {posts} active posts. I can guide you through services, scheduling, Model, Shop, posts or QR codes. Tell me what you want to work on.")
    return f"{intro}\n\n{answer}"


def _adapters(app_dir):
    from scena_connect_setup import effective_environment, ConnectionSetupError
    from scena_telegram_setup import TelegramSetupError
    from scena_integrations import OpenAIResponsesAdapter, TelegramBotAdapter, IntegrationConfigurationError
    assistant, telegram = OpenAIResponsesAdapter(), TelegramBotAdapter()
    try:
        assistant = OpenAIResponsesAdapter.from_env(effective_environment(Path(app_dir), channels=("ai",)))
    except (ConnectionSetupError, TelegramSetupError, IntegrationConfigurationError, ValueError):
        pass
    try:
        telegram = TelegramBotAdapter.from_env(effective_environment(Path(app_dir), channels=("telegram",)))
    except (ConnectionSetupError, TelegramSetupError, IntegrationConfigurationError, ValueError):
        pass
    return assistant, telegram


def _conversation(db_path, channel, locale):
    import streamlit as st
    from scena_cabinet import list_support_messages
    messages = [item for item in list_support_messages(db_path) if item["channel"] in ({"assistant", "system"} if channel == "assistant" else {"support"})]
    for item in messages:
        sender = item["sender"]
        label = (_t(locale, "Вы", "Dvs.", "You") if sender == "user" else
                 _t(locale, "Команда SCENA", "Echipa SCENA", "SCENA team") if sender == "admin" else
                 _t(locale, "Подсказки SCENA", "Ghid SCENA", "SCENA guide") if sender == "system" and "SCENA" in item["body"].split("\n")[0] else
                 "SCENA AI" if sender == "assistant" else "SCENA")
        with st.chat_message("user" if sender == "user" else "assistant", avatar=":material/auto_awesome:" if sender != "user" else None):
            st.caption(f"{label} · {item['created_at'].replace('T', ' ')[:16]}")
            body = item["body"]
            if sender == "system" and ("Ассистент пока недоступен" in body or "AI-подключение платформы пока не настроено" in body):
                body = _t(locale, "Вопрос сохранён в истории.", "Întrebarea a fost păstrată în istoric.", "Your question is saved in this history.")
            st.markdown(body)
            if sender == "user" and channel == "support":
                statuses = {
                    "queued": _t(locale, "В очереди отправки", "În coada de trimitere", "Queued for delivery"),
                    "failed": _t(locale, "Не доставлено · можно повторить", "Nelivrat · puteți reîncerca", "Not delivered · you can retry"),
                    "sent": _t(locale, "Доставлено команде", "Livrat echipei", "Delivered to the team"),
                }
                st.caption(statuses.get(item["delivery_status"], ""))
    return messages


def render_assistant(db_path, app_dir, settings=None, locale="ru"):
    import streamlit as st
    from scena_cabinet import ask_scena_assistant, CabinetValidationError
    assistant, _ = _adapters(app_dir)
    st.caption(_t(locale, "AI по данным вашей Сцены", "AI bazat pe datele Scenei dvs.", "AI using your Scene data") if assistant.configured else _t(locale, "Подсказки SCENA · помощник по настройке", "Ghid SCENA · ajutor la configurare", "SCENA guide · setup help"))
    with st.container(key="scena_assistant_conversation"):
        messages = _conversation(db_path, "assistant", locale)
        if not messages:
            with st.chat_message("assistant", avatar=":material/auto_awesome:"):
                st.write(_t(locale, "Что хотите сделать сегодня? Помогу разобраться с вашей Сценой, услугами и продвижением.", "Ce doriți să faceți astăzi? Vă ajut cu Scena, serviciile și promovarea dvs.", "What would you like to do today? I can help with your Scene, services and promotion."))
        quick_question = None
        if not messages:
            for index, triple in enumerate((("С чего начать?", "De unde încep?", "Where should I start?"), ("Как улучшить Model?", "Cum îmbunătățesc Model?", "How can I improve Model?"), ("Как добавить услугу?", "Cum adaug un serviciu?", "How do I add a service?"))):
                label = _t(locale, *triple)
                if st.button(label, key=f"scena_assistant_quick_{index}", width="stretch"):
                    quick_question = label
        question = st.chat_input(_t(locale, "Напишите вопрос…", "Scrieți o întrebare…", "Ask a question…"), max_chars=4000, key="scena_assistant_question")
    if question or quick_question:
        try:
            with st.spinner(_t(locale, "Готовлю ответ…", "Pregătesc răspunsul…", "Preparing an answer…")):
                ask_scena_assistant(db_path, question or quick_question, assistant, locale=locale)
        except CabinetValidationError:
            st.error(_t(locale, "Введите вопрос длиной до 4000 символов.", "Introduceți o întrebare de până la 4000 de caractere.", "Enter a question of up to 4000 characters."))
        else:
            st.rerun()


def render_support(db_path, app_dir, locale="ru"):
    import streamlit as st
    from scena_cabinet import list_support_messages, submit_support_message, dispatch_support_notifications, sync_telegram_replies, CabinetValidationError
    _, telegram = _adapters(app_dir)
    st.write(_t(locale, "Расскажите, с чем нужна помощь, и выберите удобное место для ответа.", "Spuneți cu ce aveți nevoie de ajutor și alegeți unde preferați răspunsul.", "Tell us what you need help with and choose where you would like a reply."))
    messages = _conversation(db_path, "support", locale)
    if messages:
        if st.button(_t(locale, "Обновить ответы", "Actualizează răspunsurile", "Refresh replies"), key="scena_support_refresh"):
            if telegram.configured:
                try:
                    sync_telegram_replies(db_path, telegram)
                except Exception:
                    st.error(_t(locale, "Не удалось получить новые ответы. Переписка сохранена.", "Nu s-au putut primi răspunsuri noi. Conversația este păstrată.", "Could not fetch new replies. Your conversation is saved."))
                else:
                    st.rerun()
        pending = sum(item["sender"] == "user" and item["delivery_status"] in {"queued", "failed"} for item in messages)
        if pending and telegram.configured:
            if st.button(_t(locale, f"Повторить отправку ({pending})", f"Reîncearcă trimiterea ({pending})", f"Retry delivery ({pending})"), key="scena_support_retry"):
                dispatch_support_notifications(db_path, telegram)
                st.rerun()
    with st.expander(_t(locale, "Где получить ответ", "Unde primiți răspunsul", "Where to receive a reply"), expanded=True):
        labels = {"telegram": "Telegram", "sms": "SMS", "email": "Email", "scena": _t(locale, "Здесь, в SCENA", "Aici, în SCENA", "Here in SCENA")}
        channel = st.selectbox(_t(locale, "Удобный канал", "Canal preferat", "Preferred channel"), tuple(labels), format_func=labels.get, key="scena_support_channel")
        contact = ""
        if channel != "scena":
            contact = st.text_input(_t(locale, "Контакт для ответа", "Contact pentru răspuns", "Reply contact"), placeholder={"telegram": "@username", "sms": "+37360123456", "email": "name@example.com"}[channel], key=f"scena_support_contact_{channel}")
        st.caption(_t(locale, "Команда ответит лично по выбранному контакту. Если выберете SCENA, переписка продолжится здесь.", "Echipa vă va răspunde personal la contactul ales. Dacă alegeți SCENA, conversația continuă aici.", "The team replies personally using your chosen contact. Choose SCENA to continue the conversation here."))
    request_key = st.session_state.setdefault("scena_support_request_key", uuid.uuid4().hex)
    with st.form("scena_support_composer", clear_on_submit=False):
        body = st.text_area(_t(locale, "Сообщение команде SCENA", "Mesaj pentru echipa SCENA", "Message to the SCENA team"), placeholder=_t(locale, "Опишите, что хотите сделать или где нужна помощь…", "Descrieți ce doriți să faceți sau unde aveți nevoie de ajutor…", "Describe what you would like to do or where you need help…"), max_chars=4000, height=110, key=f"scena_support_body_{request_key}")
        submitted = st.form_submit_button(_t(locale, "Отправить", "Trimite", "Send"), type="primary", width="stretch")
    if submitted:
        try:
            submit_support_message(db_path, body, reply_channel=channel, contact=contact, locale=locale, request_key=request_key)
        except CabinetValidationError:
            st.error(_t(locale, "Проверьте сообщение и контакт: Telegram — @username, SMS — телефон с кодом страны, email — полный адрес.", "Verificați mesajul și contactul: Telegram — @username, SMS — telefon cu prefix de țară, email — adresa completă.", "Check the message and contact: Telegram — @username; SMS — phone with country code; email — full address."))
        else:
            dispatch_support_notifications(db_path, telegram)
            st.session_state["scena_support_request_key"] = uuid.uuid4().hex
            st.rerun()
