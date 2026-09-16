"""Small HTML component layer matching the presentation calls SCENA uses.

Only registered controls can submit values or actions. Application domain
functions remain responsible for permissions, validation and transactions.
"""
from __future__ import annotations

from datetime import date, datetime, time
import html
import json
from pathlib import Path
import re

from .context import current, Node, Rerun, Stop


def escape(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def callback(function, args=(), kwargs=None):
    if not callable(function):
        return None
    return [function.__module__, function.__name__, args, kwargs or {}]


def attributes(**values):
    return ''.join(f' {k.replace("_", "-")}="{escape(v)}"' for k, v in values.items() if v is not None)


class WebUI:
    @property
    def session_state(self):
        return current.get().state

    @property
    def query_params(self):
        return current.get().query

    @property
    def context(self):
        return current.get().browser_context()

    @property
    def secrets(self):
        return {}

    def set_page_config(self, page_title='SCENA — Моя Сцена', **_):
        current.get().title = page_title

    def rerun(self, **_):
        raise Rerun()

    def stop(self):
        raise Stop()

    def markdown(self, body, unsafe_allow_html=False, **_):
        body = str(body)
        if unsafe_allow_html:
            def style(match):
                current.get().styles.append(match.group(1))
                return ''
            body = re.sub(r'<style[^>]*>(.*?)</style>', style, body, flags=re.S | re.I)
        else:
            from mistune import html as markdown
            body = markdown(escape(body))
        current.get().add(Node(attributes={'class': 'stMarkdown', 'data-testid': 'stMarkdown'}, children=[body]))

    def write(self, *values, **_):
        for value in values:
            if isinstance(value, (dict, list)):
                self.json(value)
            else:
                self.markdown(str(value))

    def _heading(self, body, level):
        current.get().add(f'<h{level}>{escape(body)}</h{level}>')

    def title(self, body, **_): self._heading(body, 1)
    def header(self, body, **_): self._heading(body, 2)
    def subheader(self, body, **_): self._heading(body, 3)
    def caption(self, body, **_): current.get().add(f'<p class="scena-caption">{escape(body)}</p>')
    def text(self, body, **_): current.get().add(f'<p class="scena-pretext">{escape(body)}</p>')
    def metric(self, label, value, delta=None, **_):
        current.get().add('<div class="scena-metric"><span>'+escape(label)+'</span><strong>'+escape(value)+'</strong>'+('<small>'+escape(delta)+'</small>' if delta is not None else '')+'</div>')

    def divider(self): current.get().add('<hr>')
    def code(self, body, **_): current.get().add(f'<pre><code>{escape(body)}</code></pre>')
    def json(self, body, **_): self.code(json.dumps(body, ensure_ascii=False, indent=2, default=str))

    def _notice(self, body, kind):
        role = 'alert' if kind in ('error', 'warning') else 'status'
        current.get().add(f'<div class="scena-notice {kind}" role="{role}">{escape(body)}</div>')

    def error(self, body, **_): self._notice(body, 'error')
    def warning(self, body, **_): self._notice(body, 'warning')
    def success(self, body, **_): self._notice(body, 'success')
    def info(self, body, **_): self._notice(body, 'info')
    def toast(self, body, **_): self._notice(body, 'info')

    def container(self, key=None, border=False, **_):
        classes = 'stVerticalBlock scena-container' + (' scena-bordered' if border else '')
        if key:
            classes += ' st-key-' + str(key)
        return current.get().add(Node(attributes={'class': classes, 'data-testid': 'stVerticalBlock'}))

    def columns(self, spec, gap='small', vertical_alignment='top', **_):
        spec = [1] * spec if isinstance(spec, int) else list(spec)
        parent = current.get().add(Node(attributes={'class': 'scena-columns', 'data-testid': 'stHorizontalBlock',
            'style': '--scena-cols:' + ' '.join(str(float(v)) + 'fr' for v in spec), 'data-count': len(spec)}))
        children = [Node(attributes={'class': 'scena-column', 'data-testid': 'stColumn'}) for _ in spec]
        parent.children.extend(children)
        return children

    def form(self, key, clear_on_submit=False, **_):
        return current.get().add(Node('fieldset', {'class': 'scena-form', 'data-testid': 'stForm', 'data-form-key': key}, group=str(key)))

    def expander(self, label, expanded=False, **_):
        node = Node('details', {'class': 'scena-expander', 'id': current.get().identity('expander',label), 'open': '' if expanded else None},
                    [f'<summary>{escape(label)}</summary>'])
        return current.get().add(node)

    def tabs(self, labels, *, default=None, **_):
        selected = labels.index(default) if default in labels else 0
        parent = current.get().add(Node(attributes={'class': 'scena-tabs'}))
        number = current.get().identity('tabs', labels)
        parent.children.append('<div role="tablist">' + ''.join(
            f'<button type="button" role="tab" id="{number}-tab-{i}" aria-controls="{number}-{i}" aria-selected="{str(i==selected).lower()}" tabindex="{0 if i==selected else -1}">{escape(label)}</button>'
            for i, label in enumerate(labels)) + '</div>')
        result = [Node(attributes={'id': f'{number}-{i}', 'role': 'tabpanel',
                  'aria-labelledby': f'{number}-tab-{i}', 'hidden': '' if i != selected else None,
                  'class': 'scena-tabpanel'}) for i in range(len(labels))]
        parent.children.extend(result)
        return result

    def spinner(self, text='', **_):
        return self.container()

    def chat_message(self, name, **_):
        return current.get().add(Node(attributes={'class': 'scena-chat ' + str(name)}))

    def _label(self, identity, label, inner, kind, help=None, label_visibility='visible'):
        hint = f'<small>{escape(help)}</small>' if help else ''
        label_class = ' class="sr-only"' if label_visibility == 'collapsed' else ''
        current.get().add(f'<div class="scena-field" data-testid="st{kind}"><label for="{identity}"{label_class}>{escape(label)}</label>{inner}{hint}</div>')

    def text_input(self, label, value='', key=None, type='default', max_chars=None, disabled=False, placeholder=None,
                   label_visibility='visible', help=None, **_):
        identity, value = current.get().register('text', label, key, value, disabled=disabled, max_chars=max_chars or 20000)
        hint = str(label).lower()
        phone = type != 'password' and bool(re.search(r'телефон|telefon|phone',hint))
        email = type != 'password' and bool(re.search(r'e-?mail|электронн.*почт',hint))
        price = type != 'password' and bool(re.search(r'цена|price|preț',hint))
        inner = '<input' + attributes(id=identity, name=identity, value='' if type=='password' else value, type='password' if type=='password' else 'tel' if phone else 'email' if email else 'text',
            inputmode='tel' if phone else 'email' if email else 'decimal' if price else None,
            autocomplete='tel' if phone else 'email' if email else None,
            maxlength=max_chars, placeholder=placeholder, disabled='' if disabled else None, data_auto='1' if not current.get().group else None) + '>'
        self._label(identity, label, inner, 'TextInput', help, label_visibility)
        return value or ''

    def text_area(self, label, value='', height=None, key=None, max_chars=None, disabled=False, label_visibility='visible', help=None, **_):
        identity, value = current.get().register('text', label, key, value, disabled=disabled, max_chars=max_chars or 100000)
        inner = '<textarea' + attributes(id=identity, name=identity, rows=max(3, int((height or 110)/24)), maxlength=max_chars,
            disabled='' if disabled else None, data_auto='1' if not current.get().group else None) + '>' + escape(value) + '</textarea>'
        self._label(identity, label, inner, 'TextArea', help, label_visibility)
        return value or ''

    def checkbox(self, label, value=False, key=None, disabled=False, help=None, **_):
        identity, value = current.get().register('bool', label, key, bool(value), disabled=disabled)
        inner = '<input' + attributes(type='checkbox', id=identity, name=identity, value='1', checked='' if value else None,
            disabled='' if disabled else None, data_auto='1' if not current.get().group else None) + '>'
        current.get().add(f'<div class="scena-check" data-testid="stCheckbox"><label>{inner}<span>{escape(label)}</span></label>' + (f'<small>{escape(help)}</small>' if help else '') + '</div>')
        return bool(value)

    toggle = checkbox

    def _choices(self, kind, label, options, default, key=None, format_func=str, disabled=False,
                 label_visibility='visible', on_change=None, args=(), kwargs=None, help=None, multiple=False):
        options = list(options)
        identity, value = current.get().register('multiple' if multiple else 'choice', label, key, default,
            options=options, disabled=disabled, callback=callback(on_change, args, kwargs))
        if multiple:
            value = [v for v in (value or []) if v in options]
        elif value not in options:
            value = default if default in options else None
        current.get().widgets[identity]['value'] = value
        if key is not None:
            self.session_state[key] = value
        auto = '1' if not current.get().group else None
        if kind == 'select':
            content = '<select' + attributes(id=identity, name=identity, multiple='' if multiple else None,
                disabled='' if disabled else None, data_auto=auto) + '>'
            if not multiple and value is None and None not in options:
                content += '<option value="" selected>—</option>'
            for index, option in enumerate(options):
                selected = option in value if multiple else option == value
                content += '<option' + attributes(value=index, selected='' if selected else None) + '>' + escape(format_func(option)) + '</option>'
            content += '</select>'
            self._label(identity, label, content, 'Selectbox', help, label_visibility)
        else:
            content = '<fieldset class="scena-choices"' + attributes(id=identity, disabled='' if disabled else None) + '>'
            content += '<legend' + (' class="sr-only"' if label_visibility == 'collapsed' else '') + '>' + escape(label) + '</legend>'
            for index, option in enumerate(options):
                selected = option in value if multiple else option == value
                content += '<label><input' + attributes(type='checkbox' if multiple else 'radio', name=identity, value=index,
                    checked='' if selected else None, data_auto=auto) + '><span>' + escape(format_func(option)) + '</span></label>'
            content += '</fieldset>'
            current.get().add(content)
        return value

    def selectbox(self, label, options, index=0, key=None, format_func=str, **kwargs):
        options = list(options)
        default = options[index] if options and index is not None and 0 <= index < len(options) else None
        return self._choices('select', label, options, default, key, format_func, **{k:v for k,v in kwargs.items() if k in {'disabled','label_visibility','help','on_change','args','kwargs'}})

    def radio(self, label, options, index=0, key=None, format_func=str, **kwargs):
        options = list(options)
        default = options[index] if options and index is not None and 0 <= index < len(options) else None
        return self._choices('radio', label, options, default, key, format_func, **{k:v for k,v in kwargs.items() if k in {'disabled','label_visibility','help','on_change','args','kwargs'}})

    def pills(self, label, options, default=None, key=None, format_func=str, selection_mode='single', **kwargs):
        return self._choices('radio', label, options, default, key, format_func, multiple=selection_mode=='multi',
            **{k:v for k,v in kwargs.items() if k in {'disabled','label_visibility','help','on_change','args','kwargs'}})

    segmented_control = pills

    def multiselect(self, label, options, default=None, key=None, format_func=str, **kwargs):
        return self._choices('select', label, options, default or [], key, format_func, multiple=True,
            **{k:v for k,v in kwargs.items() if k in {'disabled','label_visibility','help','on_change','args','kwargs'}})

    def number_input(self, label, min_value=None, max_value=None, value=None, step=None, key=None, disabled=False, **_):
        value = value if value is not None else min_value if min_value is not None else 0
        identity, value = current.get().register('number', label, key, value, minimum=min_value, maximum=max_value,
            integer=isinstance(value, int), disabled=disabled)
        inner = '<input' + attributes(type='number', id=identity, name=identity, value=value, min=min_value, max=max_value,
            inputmode='numeric' if isinstance(value,int) else 'decimal',
            step=step or ('1' if isinstance(value,int) else 'any'), disabled='' if disabled else None,
            data_auto='1' if not current.get().group else None) + '>'
        self._label(identity, label, inner, 'NumberInput')
        return value

    def slider(self, label, min_value=0, max_value=100, value=None, step=1, key=None, **kwargs):
        return self.number_input(label, min_value, max_value, min_value if value is None else value, step, key, **kwargs)

    def _temporal(self, kind, label, value, key, minimum=None, maximum=None, disabled=False):
        identity, value = current.get().register(kind, label, key, value, minimum=minimum, maximum=maximum, disabled=disabled)
        inner = '<input' + attributes(type=kind, id=identity, name=identity, value=value.isoformat() if value else '',
            min=minimum.isoformat() if minimum else None, max=maximum.isoformat() if maximum else None,
            disabled='' if disabled else None, data_auto='1' if not current.get().group else None) + '>'
        self._label(identity, label, inner, 'DateInput' if kind=='date' else 'TimeInput')
        return value

    def date_input(self, label, value=None, min_value=None, max_value=None, key=None, disabled=False, **_):
        return self._temporal('date', label, value or min_value or date.today(), key, min_value, max_value, disabled)

    def time_input(self, label, value=None, key=None, disabled=False, **_):
        return self._temporal('time', label, value or time(9), key, disabled=disabled)

    def color_picker(self, label, value='#000000', key=None, **_):
        identity, value = current.get().register('color', label, key, value)
        self._label(identity, label, '<input' + attributes(type='color', id=identity, name=identity, value=value, data_auto='1' if not current.get().group else None) + '>', 'ColorPicker')
        return value

    def button(self, label, key=None, disabled=False, type='secondary', on_click=None, args=(), kwargs=None, help=None, **_):
        identity, _ = current.get().register('button', label, key, False, disabled=disabled,
                                             callback=callback(on_click, args, kwargs))
        current.get().add('<div class="stButton" data-testid="stButton"><button' + attributes(type='submit', name='_action', value=identity,
            disabled='' if disabled else None, title=help, data_kind=type,
            data_booking_day=str(key).removeprefix('booking_day_') if str(key).startswith('booking_day_') else (args[0] if key == 'booking_nearest_day' and args else None),
            data_booking_month=args[0][:7] if key in ('booking_month_previous', 'booking_month_next') and args else None,
            data_booking_time=str(key).removeprefix('booking_slot_') if str(key).startswith('booking_slot_') else None) + '>' + escape(label) + '</button></div>')
        return current.get().action == identity and not disabled

    form_submit_button = button

    def link_button(self, label, url, type='secondary', disabled=False, **_):
        if not str(url).startswith(('/', '?', '#', 'http://', 'https://', 'mailto:', 'tel:', 'sms:')):
            return
        current.get().add('<a class="scena-link-button"' + attributes(href=None if disabled else url, data_kind=type,
            aria_disabled='true' if disabled else None) + '>' + escape(label) + '</a>')

    def file_uploader(self, label, type=None, key=None, accept_multiple_files=False, disabled=False, max_upload_size=20, **_):
        identity, value = current.get().register('file', label, key, None, extensions=type or [], disabled=disabled,
            multiple=accept_multiple_files, max_size=max_upload_size*1024*1024)
        inner = '<input' + attributes(type='file', id=identity, name=identity, accept=','.join('.'+t for t in (type or [])),
            multiple='' if accept_multiple_files else None, disabled='' if disabled else None, data_upload=identity,
            data_max_size=max_upload_size*1024*1024, data_auto='1' if not current.get().group else None) + '>'
        if value:
            inner += '<small>' + escape(value.name if not isinstance(value,list) else ', '.join(f.name for f in value)) + '</small>'
        self._label(identity, label, inner, 'FileUploader')
        return value

    def download_button(self, label, data, file_name='SCENA', mime='application/octet-stream', key=None, **_):
        from .storage import download_url
        self.link_button(label, download_url(data, file_name, mime))
        return False

    def image(self, image, width=None, caption=None, **_):
        from .media import display_image
        source = display_image(image)
        max_width = f'max-width:{int(width)}px;' if isinstance(width, (int,float)) else ''
        from scena_i18n import tr
        alternative = caption or tr(self.session_state.get('scena_ui_locale', 'ru'), 'Фотография', 'Fotografie', 'Photo')
        current.get().add(f'<figure class="scena-image" style="{max_width}"><img src="{escape(source)}" alt="{escape(alternative)}" loading="lazy" decoding="async">' + (f'<figcaption>{escape(caption)}</figcaption>' if caption else '') + '</figure>')

    def iframe(self, src, height=600, width='stretch', **_):
        # Existing scene/portfolio scripts remain isolated; no framework runtime.
        value = 'srcdoc' if str(src).lstrip().startswith('<') else 'src'
        from scena_urls import enabled, rewrite_links
        settings = current.get().seo_settings or {}
        if value == 'srcdoc' and enabled(settings):
            src = rewrite_links(src, settings.get('public_base_url', ''))
        current.get().add('<iframe class="scena-embed"' + attributes(**{value:src}, title='SCENA', height=height,
            style=f'width:{int(width)}px;max-width:100%' if isinstance(width,int) else 'width:100%',
            sandbox='allow-scripts allow-same-origin allow-popups allow-downloads allow-popups-to-escape-sandbox',
            loading='eager') + '></iframe>')

    def dataframe(self, rows, **_):
        if hasattr(rows, 'to_dict'):
            rows = rows.to_dict(orient='records')
        if not rows:
            return
        names = list(rows[0])
        current.get().add('<div class="scena-table-wrap"><table><thead><tr>' + ''.join('<th>'+escape(k)+'</th>' for k in names) +
            '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+escape(row.get(k,''))+'</td>' for k in names)+'</tr>' for row in rows) + '</tbody></table></div>')

    def chat_input(self, placeholder='Сообщение', key=None, max_chars=4000, **_):
        from scena_i18n import translate_literaltext
        locale = self.session_state.get('scena_ui_locale', 'ru')
        value = self.text_input(translate_literaltext(locale, placeholder) if placeholder == 'Сообщение' else placeholder, key=key, max_chars=max_chars)
        if self.button(translate_literaltext(locale, 'Отправить'), key=str(key)+'_send'):
            self.session_state.pop(key, None)
            return value
        return None


st = WebUI()
