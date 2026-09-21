"""Month-based owner scheduling over the existing booking rules."""
import calendar
from datetime import datetime, time, timedelta

from scena_ui import st
from scena_i18n import tr
from scena_core import (CHISINAU, _connect, _working_periods, save_dates_hours,
                        RequestValidationError)


def render_calendar(db, settings, locale):
    text = lambda ru, ro, en: tr(locale, ru, ro, en)
    today = datetime.now(CHISINAU).date()
    offset = int(st.session_state.get('schedule_month_offset', 0))
    index = today.year * 12 + today.month - 1 + offset
    year, month = index // 12, index % 12 + 1
    months = {'ru': 'Январь Февраль Март Апрель Май Июнь Июль Август Сентябрь Октябрь Ноябрь Декабрь'.split(),
              'ro': 'Ianuarie Februarie Martie Aprilie Mai Iunie Iulie August Septembrie Octombrie Noiembrie Decembrie'.split(),
              'en': 'January February March April May June July August September October November December'.split()}
    with st.container(key='schedule_month_navigation'):
        if st.button('‹', key='schedule_previous_month', disabled=offset <= 0,
                     help=text('Предыдущий месяц','Luna precedentă','Previous month')):
            st.session_state['schedule_month_offset'] = offset - 1
            st.rerun()
        st.subheader(f'{months[locale][month-1]} {year}')
        if st.button('›', key='schedule_next_month', disabled=offset >= 12,
                     help=text('Следующий месяц','Luna următoare','Next month')):
            st.session_state['schedule_month_offset'] = offset + 1
            st.rerun()
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    with _connect(db) as con:
        rows = con.execute('SELECT * FROM schedule_exceptions WHERE exception_date BETWEEN ? AND ? ORDER BY id',
                           (weeks[0][0].isoformat(), weeks[-1][-1].isoformat())).fetchall()
        by_date = {}
        for row in rows:
            by_date.setdefault(row['exception_date'], []).append(row)
        periods = {day: _working_periods(con, day, settings, by_date.get(day.isoformat(), [])) for week in weeks for day in week}
        reserved = con.execute("SELECT preferred_date, COUNT(*) AS total FROM requests WHERE status IN ('Ожидает подтверждения','Связались','Подтверждена') AND slot_start != '' AND preferred_date BETWEEN ? AND ? GROUP BY preferred_date",
                               (weeks[0][0].isoformat(), weeks[-1][-1].isoformat())).fetchall()
        booked = {row['preferred_date']: row['total'] for row in reserved}
    st.caption(text('Выберите одну или несколько дат, затем задайте часы или выходной.',
                    'Selectați una sau mai multe date, apoi orele sau o zi liberă.',
                    'Select one or more dates, then set working hours or a day off.'))
    names = {'ru':['Пн','Вт','Ср','Чт','Пт','Сб','Вс'], 'ro':['Lu','Ma','Mi','Jo','Vi','Sâ','Du'],
             'en':['Mo','Tu','We','Th','Fr','Sa','Su']}[locale]
    with st.form('schedule_calendar_form'):
        st.markdown('<div class="schedule-weekdays">'+''.join('<span>'+day+'</span>' for day in names)+'</div>', unsafe_allow_html=True)
        chosen = []
        with st.container(key='schedule_calendar_month'):
            for week in weeks:
                for day in week:
                    if day.month != month:
                        st.markdown('<span aria-hidden="true"></span>', unsafe_allow_html=True)
                        continue
                    hours = periods[day]
                    short = f'{hours[0][0]:%H:%M}–{hours[-1][1]:%H:%M}' if hours else text('выходной','liber','off')
                    hint = day.strftime('%d.%m.%Y')+' · '+short
                    if booked.get(day.isoformat()):
                        hint += text(' · есть записи',' · există programări',' · has bookings')
                    display = str(day.day) + (' •' if booked.get(day.isoformat()) else '') + '\n' + (f'{hours[0][0].hour}–{hours[-1][1].hour}' if hours else '—')
                    if st.checkbox(display, key='schedule_date_'+day.isoformat(), disabled=day < today, help=hint):
                        chosen.append(day.isoformat())
        st.caption(text('Часы — рабочий день · «—» — выходной · «•» — есть записи.',
                        'Ore — zi de lucru · «—» — liber · «•» — există programări.',
                        'Hours — work day · “—” — day off · “•” — booked appointments.'))
        st.subheader(text('Для выбранных дат','Pentru datele selectate','For selected dates'))
        closed = st.checkbox(text('Выходной','Zi liberă','Day off'), key='schedule_calendar_closed')
        cols = st.columns(2)
        start = cols[0].time_input(text('Начало работы','Începutul programului','Work starts'), value=time.fromisoformat(settings['schedule_start']), key='schedule_calendar_start')
        end = cols[1].time_input(text('Конец работы','Sfârșitul programului','Work ends'), value=time.fromisoformat(settings['schedule_end']), key='schedule_calendar_end')
        pause = st.checkbox(text('Добавить перерыв','Adaugă o pauză','Add a break'), key='schedule_calendar_break')
        cols = st.columns(2)
        pause_start = cols[0].time_input(text('Перерыв с','Pauză de la','Break from'), value=time(13), key='schedule_calendar_pause_start')
        pause_end = cols[1].time_input(text('Перерыв до','Pauză până la','Break until'), value=time(14), key='schedule_calendar_pause_end')
        st.caption(text('Существующие записи сохранятся. Изменение графика не отменяет их.',
                        'Programările existente se păstrează. Modificarea programului nu le anulează.',
                        'Existing bookings stay in place. Schedule changes do not cancel them.'))
        save = st.form_submit_button(text('Применить к выбранным датам','Aplică datelor selectate','Apply to selected dates'), type='primary')
        reset = st.form_submit_button(text('Вернуть обычный график','Restabilește programul obișnuit','Restore regular hours'))
    if save or reset:
        try:
            save_dates_hours(db, chosen, start_time=start.strftime('%H:%M'), end_time=end.strftime('%H:%M'),
                             break_start=pause_start.strftime('%H:%M') if pause else '',
                             break_end=pause_end.strftime('%H:%M') if pause else '', closed=closed, reset=reset)
        except RequestValidationError as error:
            st.error(str(error) if locale == 'ru' else text('', 'Verificați datele, orele și pauza.', 'Check the dates, hours and break.'))
        else:
            st.session_state['scena_admin_notice'] = ('success', text(f'График обновлён: {len(chosen)} дат.', f'Program actualizat: {len(chosen)} date.', f'Schedule updated: {len(chosen)} dates.'))
            st.rerun()
