from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import html
from types import SimpleNamespace
from urllib.parse import urlencode

current: ContextVar['RenderContext'] = ContextVar('scena_web_render')


class Rerun(Exception):
    pass


class Stop(Exception):
    pass


class FormError(ValueError):
    pass


class Query(dict):
    def from_dict(self, value):
        self.clear()
        self.update(value)


@dataclass
class Node:
    tag: str = 'div'
    attributes: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    group: str | None = None

    def render(self):
        attrs = ''.join(' ' + k + '="' + html.escape(str(v), quote=True) + '"'
                        for k, v in self.attributes.items() if v is not None)
        body = ''.join(c.render() if isinstance(c, Node) else c for c in self.children)
        return f'<{self.tag}{attrs}>{body}</{self.tag}>'

    def __enter__(self):
        current.get().stack.append(self)
        return self

    def __exit__(self, *_):
        current.get().stack.pop()

    def __getattr__(self, name):
        from .widgets import st
        function = getattr(st, name)
        def bound(*args, **kwargs):
            with self:
                return function(*args, **kwargs)
        return bound


@dataclass
class RenderContext:
    state: dict
    query: Query
    headers: dict
    session_id: str = ''
    action: str = ''
    submitted: bool = False
    private: bool = False
    fragment: bool = False
    title: str = 'SCENA — Моя Сцена'
    widgets: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    attachments: dict = field(default_factory=dict)
    styles: list = field(default_factory=list)
    stack: list = field(default_factory=list)
    manifest: dict | None = None
    document: str | None = None
    seo_settings: dict | None = None
    seo: dict | None = None

    def reset(self):
        self.root = Node(attributes={'class': 'stVerticalBlock', 'data-testid': 'stVerticalBlock'})
        self.stack = [self.root]
        self.widgets = {}
        self.counts = {}
        self.styles = []
        self.document = None
        self.seo = None

    @property
    def group(self):
        return next((n.group for n in reversed(self.stack) if n.group), '')

    @property
    def route(self):
        return '&'.join(f'{k}={self.query.get(k, "")}' for k in ('page', 'section', 'view', 'lang'))

    @property
    def url(self):
        from scena_urls import enabled, public_path
        if enabled(self.seo_settings or {}):
            return public_path(self.query)
        return '/?' + urlencode(self.query)

    def add(self, node):
        self.stack[-1].children.append(node)
        return node

    def identity(self, kind, label, key=None):
        seed = self.route + '|' + self.group + '|' + (('key:' + str(key)) if key is not None else kind + ':' + str(label))
        ordinal = self.counts.get(seed, 0)
        self.counts[seed] = ordinal + 1
        return 'w_' + hashlib.sha256((seed + ':' + str(ordinal)).encode()).hexdigest()[:20]

    def register(self, kind, label, key=None, default=None, **meta):
        identity = self.identity(kind, label, key)
        values = self.state.setdefault('_web_values', {})
        value = self.state[key] if key is not None and key in self.state else values.get(identity, default)
        if key is not None:
            self.state[key] = value
        self.widgets[identity] = {'kind': kind, 'label': str(label), 'key': key,
                                  'group': self.group, 'value': value, **meta}
        return identity, value

    def browser_context(self):
        return SimpleNamespace(headers=self.headers, locale=self.headers.get('Accept-Language', 'ru').split(',')[0])
