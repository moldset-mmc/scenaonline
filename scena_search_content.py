"""Original, factual page copy: booking behaviour and published service types."""
from html import escape
from scena_i18n import content_text, localized_name, tr

SERVICE_COPY = {
    'Дневной Makeup': (
        'Дневной макияж в Кишинёве. Выберите этот вариант, если планируете дневную встречу или повседневный образ. Перед визитом обсудите с Машей желаемые акценты; длительность и стоимость указаны в карточке услуги.',
        'Machiaj de zi în Chișinău. Alegeți această opțiune pentru o întâlnire în timpul zilei sau un look de zi cu zi. Discutați cu Masha accentele dorite înainte de vizită; durata și prețul sunt afișate în fișa serviciului.',
        'Daytime makeup in Chișinău. Choose this option for a daytime occasion or an everyday look. Discuss the details you want with Masha before your visit; the service card lists the duration and price.'),
    'Вечерний Makeup': (
        'Вечерний макияж в Кишинёве для особого события. Расскажите Маше о поводе, наряде и желаемом настроении образа. Выберите свободное время в календаре и удобный способ связи для подтверждения записи.',
        'Machiaj de seară în Chișinău pentru un eveniment special. Povestiți-i Mashei despre ocazie, ținută și stilul dorit. Alegeți o oră disponibilă în calendar și canalul de comunicare pentru confirmarea programării.',
        'Evening makeup in Chișinău for a special occasion. Tell Masha about the event, your outfit and the look you have in mind. Choose an available time and your preferred contact channel to confirm the appointment.'),
    'Makeup Невеста': (
        'Свадебный макияж в Кишинёве. Начните с даты свадьбы и времени, к которому нужно быть готовой. Отправьте заявку на подходящий интервал; детали образа и запись Маша подтвердит лично. Пробный макияж и дополнительные услуги обсуждаются отдельно.',
        'Machiaj de mireasă în Chișinău. Începeți cu data nunții și ora la care trebuie să fiți gata. Trimiteți o cerere pentru intervalul potrivit; Masha va confirma personal detaliile lookului și programarea. Proba și serviciile suplimentare se discută separat.',
        'Bridal makeup in Chișinău. Start with your wedding date and the time you need to be ready. Request a suitable appointment; Masha will confirm the look and booking personally. Trials and additional services are discussed separately.'),
    'Сэлфи макияж': (
        'Курс «Сэлфи макияж» в Кишинёве — возможность обсудить обучение макияжу для себя. Оставьте контакты и напишите, какой образ хотите научиться создавать. Маша уточнит программу, формат и ближайшие даты; предзапись сама по себе не подтверждает место.',
        'Cursul de machiaj pentru selfie-uri în Chișinău vă permite să discutați despre învățarea machiajului pentru sine. Lăsați datele de contact și descrieți lookul pe care doriți să învățați să îl creați. Masha va preciza programa, formatul și datele; preînscrierea nu confirmă automat locul.',
        'The Selfie Makeup course in Chișinău is an opportunity to discuss learning makeup for yourself. Leave your contact details and describe the look you want to learn. Masha will explain the programme, format and upcoming dates; preregistration does not automatically confirm a place.'),
}


def page_content(settings, query, locale):
    """Visible contextual information; no invented address, credentials or offers."""
    page = query.get('page', 'scene')
    name = localized_name(settings, locale)
    place = content_text(settings, 'location', locale)
    copy = {
        'professional': (
            ('Макияж в Кишинёве: как выбрать и записаться', 'Machiaj în Chișinău: alegere și programare', 'Makeup in Chișinău: choosing and booking'),
            ('Сравните дневной, вечерний и свадебный макияж в списке услуг. Стоимость и продолжительность указаны рядом с каждым вариантом. Календарь показывает доступное время для выбранной услуги.',
             'Comparați machiajul de zi, de seară și de mireasă în lista serviciilor. Prețul și durata sunt afișate lângă fiecare opțiune. Calendarul arată orele disponibile pentru serviciul ales.',
             'Compare daytime, evening and bridal makeup in the service list. Each option shows its price and duration. The calendar displays available times for your chosen service.'),
            ('После отправки заявки мастер свяжется с вами выбранным способом. Для обучения откройте страницу курса: программа и даты уточняются при личном подтверждении.',
             'După trimiterea cererii, specialistul vă va contacta prin canalul ales. Pentru instruire, deschideți pagina cursului: programa și datele se stabilesc la confirmarea personală.',
             'After you submit a request, the artist will contact you through your chosen channel. For training, open the course page; the programme and dates are discussed before your place is confirmed.')),
        'booking': (
            ('Что происходит после выбора времени', 'Ce urmează după alegerea orei', 'What happens after choosing a time'),
            ('Выберите услугу, день и свободное время, затем оставьте контакты. Можно выбрать звонок, Telegram, SMS или email. Отправка заявки и окончательное подтверждение записи — отдельные шаги.',
             'Alegeți serviciul, ziua și ora disponibilă, apoi lăsați datele de contact. Puteți alege apel, Telegram, SMS sau email. Trimiterea cererii și confirmarea finală a programării sunt etape separate.',
             'Choose a service, day and available time, then leave your contact details. You can select a phone call, Telegram, SMS or email. Submitting a request and receiving final booking confirmation are separate steps.'),
            ('Если нужно изменить время после отправки, свяжитесь с мастером. При подтверждении доступность выбранного интервала проверяется ещё раз.',
             'Dacă doriți să modificați ora după trimitere, contactați specialistul. Disponibilitatea intervalului ales este verificată din nou la confirmare.',
             'Contact the artist if you need to change the time after submitting. Availability is checked again when the appointment is confirmed.')),
        'course': (
            ('Перед предзаписью на обучение', 'Înainte de preînscriere', 'Before you preregister'),
            ('Вопрос в заявке поможет начать разговор: напишите, есть ли у вас опыт, какой макияж интересует и какие даты удобны. Программа, продолжительность и состав обучения обсуждаются с мастером до подтверждения.',
             'Întrebarea din formular ajută la începerea discuției: spuneți dacă aveți experiență, ce machiaj vă interesează și ce date vă convin. Programa, durata și conținutul instruirii se discută înainte de confirmare.',
             'Use the question field to tell the artist about your experience, the makeup you are interested in and suitable dates. Discuss the programme, duration and course contents before confirming.'),
            ('Форма отправляет запрос мастеру. Автоматического зачисления или оплаты на этом шаге нет.',
             'Formularul trimite o solicitare specialistului. Acest pas nu implică înscriere automată sau plată.',
             'The form sends an enquiry to the artist. This step does not automatically enrol you or take payment.')),
        'shop': (
            ('Как заказать из подборки мастера', 'Cum comandați din selecția specialistului', 'How to order from the artist’s selection'),
            ('Откройте карточку товара, чтобы рассмотреть фотографии и описание. Добавьте нужные позиции в корзину и оставьте контакты для обсуждения заказа.',
             'Deschideți fișa produsului pentru a vedea fotografiile și descrierea. Adăugați produsele dorite în coș și lăsați datele de contact pentru discutarea comenzii.',
             'Open a product card to view its photographs and description. Add your choices to the basket and leave contact details to discuss the order.'),
            ('Наличие, получение и оплату уточните у владельца магазина. Подборка на этой странице отражает опубликованные товары; оформление запроса не означает онлайн-оплату.',
             'Confirmați disponibilitatea, primirea și plata cu proprietarul magazinului. Selecția afișează produsele publicate; trimiterea cererii nu reprezintă o plată online.',
             'Confirm availability, collection or delivery, and payment with the shop owner. This page shows published products; submitting an order request is not an online payment.')),
        'invite-model': (
            ('Что указать в предложении модели', 'Ce să includeți în invitația pentru model', 'What to include in a modelling invitation'),
            ('Опишите идею съёмки или проекта, предполагаемые дату и место, формат участия и условия. Добавьте контакт, по которому можно обсудить детали.',
             'Descrieți ideea ședinței foto sau a proiectului, data și locul propuse, formatul participării și condițiile. Adăugați un contact pentru discutarea detaliilor.',
             'Describe the shoot or project, proposed date and location, type of participation and terms. Add contact details so the proposal can be discussed.'),
            ('Предложение рассматривается лично. Отправка формы не означает согласие на участие или согласование условий.',
             'Propunerea este analizată personal. Trimiterea formularului nu înseamnă acceptarea participării sau a condițiilor.',
             'Proposals are reviewed personally. Sending the form does not confirm participation or agreement to the terms.')),
        'join-model': (
            ('Знакомство начинается с вашей анкеты', 'Primul pas este formularul dvs.', 'Start with your introduction'),
            ('Укажите город, опыт и контакты. Анкета помогает представить себя и начать обсуждение возможного участия в модельных проектах.',
             'Indicați orașul, experiența și datele de contact. Formularul vă ajută să vă prezentați și să începeți discuția despre participarea la proiecte de model.',
             'Share your city, experience and contact details. The form introduces you and starts a conversation about possible participation in modelling projects.'),
            ('Заявка не является обещанием работы, кастинга или оплаченного проекта. Условия конкретного сотрудничества обсуждаются отдельно.',
             'Cererea nu reprezintă o promisiune de lucru, casting sau proiect plătit. Condițiile colaborării se discută separat.',
             'An application is not a promise of work, a casting or a paid project. The terms of any collaboration are discussed separately.')),
    }
    if page not in copy or settings.get('seo_content_v1') != '1':
        return ''
    heading, first, second = copy[page]
    return ('<section class="scena-search-help" style="max-width:780px;margin:32px auto;padding:20px;line-height:1.6">'
            '<h2>' + escape(tr(locale, *heading)) + '</h2><p>' + escape(tr(locale, *first)) + '</p><p>'
            + escape(tr(locale, *second)) + '</p><small>' + escape(' · '.join(p for p in (name, place) if p)) + '</small></section>')
