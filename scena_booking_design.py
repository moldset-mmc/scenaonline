"""Booking presentation using the existing registered form and scheduler."""
from html import escape

from scena_ui import st
from scena_i18n import tr, content_text, localized_name, DEFAULT_I18N_SETTINGS


def introduction(app_dir, settings, locale, *, confirmation=False, receipt=False):
    from model_landing import image_uri
    from scena_web.media import assets
    step = 3 if confirmation or receipt else 1
    labels = [tr(locale,'Услуга','Serviciu','Service'), tr(locale,'Дата и время','Data și ora','Date and time'), tr(locale,'Контакты','Contacte','Contact')]
    back = tr(locale,'К услугам','La servicii','Back to services')
    steps = ''.join('<li'+(' aria-current="step"' if index == step else '')+'><span>'+str(index)+'</span>'+escape(label)+'</li>' for index,label in enumerate(labels,1))
    st.markdown('<a class="booking-back" href="?page=professional&amp;lang='+locale+'">‹ '+escape(back)+'</a><ol class="booking-steps" aria-label="'+escape(tr(locale,'Шаги записи','Pașii programării','Booking steps'))+'">'+steps+'</ol>',unsafe_allow_html=True)
    if confirmation or receipt:
        st.markdown('<h1 class="booking-heading">'+escape(tr(locale,'Ваша запись','Programarea dvs.','Your appointment'))+'</h1>',unsafe_allow_html=True)
        return
    prefix,accent={'ru':('Ваш красивый','момент'),'ro':('Momentul tău','de frumusețe'),'en':('Your beautiful','moment')}[locale]
    current_title=content_text(settings,'booking_title',locale)
    default_title=DEFAULT_I18N_SETTINGS.get('booking_title_'+locale,'')
    title=escape(prefix)+' <em>'+escape(accent)+'</em>' if not current_title or current_title==default_title else escape(current_title)
    intro=content_text(settings,'booking_description',locale)
    if not intro or intro==DEFAULT_I18N_SETTINGS.get('booking_description_'+locale,''):
        intro=tr(locale,'Начнём с выбора макияжа.','Începem cu alegerea machiajului.','Let’s choose your makeup.')
    brush=assets().get('scena_web/static/booking-brush.png','') if locale=='ru' else ''
    art='<img class="booking-brush" src="'+escape(brush,quote=True)+'" alt="" width="143" height="170">' if brush else ''
    st.markdown('<section class="booking-intro">'+art+'<h1 class="booking-heading">'+title+'</h1><p>'+escape(intro)+'</p></section>',unsafe_allow_html=True)
    portrait=image_uri(app_dir,settings.get('professional_hero_image',''))
    photo='<img src="'+escape(portrait,quote=True)+'" alt="" width="48" height="48">' if portrait else ''
    st.markdown('<div class="booking-master">'+photo+'<div><strong>'+escape(localized_name(settings,locale))+'</strong><span>'+escape(tr(locale,'Ваш мастер','Specialistul dvs.','Your makeup artist'))+'</span></div></div>',unsafe_allow_html=True)


def services_picker(services, settings, locale, labels, price, on_change):
    from scena_web.context import current
    from scena_web.widgets import callback
    ctx=current.get()
    options=[int(item['id']) for item in services]
    selected=st.session_state.get('booking_service')
    if selected not in options:
        selected=options[0]
    label=tr(locale,'1. Выберите услугу','1. Alegeți serviciul','1. Choose a service')
    identity,selected=ctx.register('choice',label,'booking_service',selected,options=options,disabled=False,callback=callback(on_change))
    st.session_state['booking_service']=selected
    cards=[]
    for index,item in enumerate(services):
        name=labels[item['id']]
        description=content_text(item,'description',locale)
        cards.append('<label class="booking-service"><input type="radio" name="'+identity+'" value="'+str(index)+'" data-auto="1"'+(' checked' if item['id']==selected else '')+'><span class="booking-service-content"><strong>'+escape(name)+'</strong>'+
            ('<span class="booking-service-note">'+escape(description)+'</span>' if description else '')+
            '<b>'+escape(price(item,settings,locale))+'</b><small>'+str(int(item['duration']))+' '+escape(tr(locale,'мин.','min.','min.'))+'</small></span></label>')
    st.markdown('<fieldset class="booking-services" id="'+identity+'"><legend>'+escape(tr(locale,'Выберите услугу','Alegeți serviciul','Choose a service'))+'</legend><div class="booking-service-grid">'+''.join(cards)+'</div></fieldset>',unsafe_allow_html=True)
    return selected


def selection_summary(item, settings, locale, price):
    description=content_text(item,'description',locale)
    st.markdown('<section class="booking-selection"><h2>'+escape(content_text(item,'name',locale))+'</h2>'+('<p>'+escape(description)+'</p>' if description else '')+'</section><div class="booking-total"><span>'+str(int(item['duration']))+' '+escape(tr(locale,'мин.','min.','min.'))+'</span><strong>'+escape(price(item,settings,locale))+'</strong></div>',unsafe_allow_html=True)
