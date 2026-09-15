"""Validate POST data against the controls emitted by the server."""
from datetime import date, time
import importlib
import math
import re

from .context import FormError


CALLBACKS = {'_choose_day', '_choose_time', '_service_changed', '_move_month', '_edit_selection', '_new_booking'}


def apply(ctx, previous, values, files):
    action = ctx.action
    changed = values.get('_changed', [''])[0]
    trigger = previous.get(action or changed)
    if not trigger or trigger.get('disabled'):
        raise FormError('Действие недоступно. Обновите страницу.')
    if action and trigger['kind']!='button':
        raise FormError('Некорректная кнопка действия.')
    group = trigger['group']
    callbacks = []
    for identity, widget in previous.items():
        if widget.get('disabled') or widget['kind']=='button' or widget['group'] != group:
            continue
        kind = widget['kind']
        present = identity in values or identity in files
        if not present and kind not in ('bool','multiple'):
            continue
        raw = values.get(identity, [''])[0]
        value = widget.get('value')
        try:
            if kind=='text':
                if len(raw)>widget['max_chars']: raise ValueError()
                value = raw
            elif kind=='bool': value = raw=='1'
            elif kind in ('choice','multiple'):
                if kind=='choice':
                    value = widget['options'][int(raw)] if raw!='' else None
                    if raw and int(raw)<0: raise ValueError()
                else:
                    indexes=[int(v) for v in values.get(identity,[])]
                    if any(v<0 or v>=len(widget['options']) for v in indexes):raise ValueError()
                    value=[widget['options'][v] for v in indexes]
            elif kind=='number':
                value = float(raw)
                if not math.isfinite(value):raise ValueError()
                if widget.get('integer'):
                    if value!=int(value):raise ValueError()
                    value=int(value)
                if widget.get('minimum') is not None and value<widget['minimum']:raise ValueError()
                if widget.get('maximum') is not None and value>widget['maximum']:raise ValueError()
            elif kind in ('date','time'):
                value=(date if kind=='date' else time).fromisoformat(raw)
                if widget.get('minimum') and value<widget['minimum']:raise ValueError()
                if widget.get('maximum') and value>widget['maximum']:raise ValueError()
            elif kind=='color':
                if not re.fullmatch(r'#[0-9a-fA-F]{6}',raw):raise ValueError()
                value=raw
            elif kind=='file':
                if identity not in files: continue
                value=files[identity]
                uploads=value if isinstance(value,list) else [value]
                if not widget.get('multiple') and len(uploads)!=1:raise ValueError()
                for upload in uploads:
                    if upload.size>widget['max_size']:raise ValueError()
                    if widget['extensions'] and upload.name.rsplit('.',1)[-1].lower() not in widget['extensions']:raise ValueError()
            else:raise ValueError()
        except (ValueError,TypeError,IndexError,OverflowError):
            raise FormError('Проверьте поле «'+widget['label']+'».') from None
        ctx.state.setdefault('_web_values',{})[identity]=value
        if widget.get('key') is not None:
            ctx.state[widget['key']]=value
        if widget.get('callback') and value!=widget.get('value'):
            callbacks.append(widget['callback'])
    if action and trigger.get('callback'):
        callbacks.append(trigger['callback'])
    for module, name, args, kwargs in callbacks:
        if module!='scena_booking_ui' or name not in CALLBACKS:
            raise FormError('Unsupported web callback')
        getattr(importlib.import_module(module),name)(*args,**kwargs)

    # Browser-local day/time selection is accepted only through registered choices.
    # Continue re-renders fresh availability before revealing the contact form.
    if trigger.get('key') in {'booking_continue','booking_month_previous','booking_month_next'} and '_booking_local_date' in ctx.state:
        ctx.state['booking_date'] = ctx.state['_booking_local_date']
        ctx.state['booking_time'] = ctx.state.get('_booking_local_time')
