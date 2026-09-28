import { useEffect, useState } from 'react';
import { ArrowRight, CalendarBlank, Camera, CaretRight, CirclesFour, GearSix, House, Images, List, Megaphone, Question, ShoppingBag, Sparkle, X } from '@phosphor-icons/react';

const navigation = [
  { id: 'overview', label: 'Обзор', icon: House, group: 'Кабинет' },
  { id: 'requests', label: 'Заявки', icon: CirclesFour, group: 'Работа' },
  { id: 'services', label: 'Услуги', icon: Sparkle, group: 'Работа' },
  { id: 'schedule', label: 'График', icon: CalendarBlank, group: 'Работа' },
  { id: 'pages', label: 'Страницы', icon: Images, group: 'Профиль' },
  { id: 'photos', label: 'Фото', icon: Camera, group: 'Профиль' },
  { id: 'promotion', label: 'Продвижение', icon: Megaphone, group: 'Профиль' },
  { id: 'shop', label: 'shopping', icon: ShoppingBag, group: 'Профиль' },
  { id: 'settings', label: 'Настройки', icon: GearSix, group: 'Система' },
  { id: 'pro', label: 'PRO', icon: Sparkle, group: 'Система' },
  { id: 'help', label: 'Помощь', icon: Question, group: 'Система' },
];

const descriptions = {
  requests: 'Обращения клиентов, статусы и детали в одном месте.',
  services: 'Группы услуг, цены и способы записи.',
  schedule: 'Рабочие дни, свободное время и исключения.',
  pages: 'Содержание публичных страниц MBstudio.',
  photos: 'Библиотека изображений и места их использования.',
  promotion: 'Публикации, поиск и QR-коды.',
  shop: 'Товары, рекомендации и заказы.',
  settings: 'Подключения и управление данными.',
  pro: 'Подписка и возможности PRO.',
  help: 'Поддержка и SCENA Ассистент.',
};

function DemoNotice() {
  return <p className="cab-demo"><span className="cab-demo-dot" /> Концепт интерфейса · данные и действия здесь демонстрационные</p>;
}

function ActionCard({ number, title, detail, onClick, icon: Icon }) {
  return <button type="button" className="cab-action-card" onClick={onClick}>
    <span className="cab-card-top"><span>{number}</span><Icon size={24} weight="light" aria-hidden="true" /></span>
    <strong>{title}</strong><span className="cab-card-bottom">{detail}<ArrowRight size={19} aria-hidden="true" /></span>
  </button>;
}

function Overview({ navigate }) {
  return <>
    <div className="cab-eyebrow"><span>MBSTUDIO / WORKSPACE</span><span>01 — ОБЗОР</span></div>
    <section className="cab-welcome"><div><p className="cab-kicker">Ваша сцена сегодня</p><h1>Добрый день,<br /><em>Мария.</em></h1><p>Всё важное для работы и творчества — на одной странице.</p></div><div className="cab-welcome-monogram" aria-hidden="true">M.</div></section>
    <div className="cab-section-title"><div><span className="cab-red-line" /><h2>Быстрый доступ</h2></div><small>01 / 02</small></div>
    <div className="cab-actions">
      <ActionCard number="01" title="Заявки" detail="Обращения и статусы" icon={CirclesFour} onClick={() => navigate('requests')} />
      <ActionCard number="02" title="Заказы" detail="Покупатели и товары" icon={ShoppingBag} onClick={() => navigate('shop')} />
      <ActionCard number="03" title="График" detail="Рабочие часы" icon={CalendarBlank} onClick={() => navigate('schedule')} />
      <ActionCard number="04" title="Услуги" detail="Цены и запись" icon={Sparkle} onClick={() => navigate('services')} />
    </div>
    <div className="cab-section-title cab-section-title-lower"><div><span className="cab-red-line" /><h2>Мои страницы</h2></div><small>02 / 02</small></div>
    <div className="cab-page-strip">
      <div className="cab-page-image" role="img" aria-label="Портрет Марии Кравченко" />
      <div><span className="cab-overline">ВИЗИТНАЯ КАРТОЧКА</span><h3>Ваша история<br />начинается здесь.</h3><p>Моя Сцена · Professional · Model · shopping</p><button type="button" onClick={() => navigate('pages')}>Редактировать страницы <ArrowRight size={19} /></button></div>
    </div>
  </>;
}

function Detail({ view, navigate }) {
  const [name, setName] = useState('Maria Cravcenco');
  const [tagline, setTagline] = useState('Model & Makeup Artist');
  const [pageTab, setPageTab] = useState('Моя Сцена');
  const [requestFilter, setRequestFilter] = useState('Все');
  const title = navigation.find(item => item.id === view)?.label || view;
  return <>
    <div className="cab-eyebrow"><span>MBSTUDIO / WORKSPACE</span><span>{title.toUpperCase()}</span></div>
    <div className="cab-detail-head"><button type="button" className="cab-back" onClick={() => navigate('overview')}>← Обзор</button><h1>{title}<span className="cab-period">.</span></h1><p>{descriptions[view]}</p></div>
    {view === 'pages' ? <div className="cab-editor-grid"><section className="cab-panel"><span className="cab-overline">СТРАНИЦЫ / {pageTab.toUpperCase()}</span><h2>Ваш профиль</h2><div className="cab-tabs">{['Моя Сцена','Professional','Model'].map(tab=><button type="button" key={tab} className={pageTab===tab?'active':''} aria-pressed={pageTab===tab} onClick={()=>setPageTab(tab)}>{tab}</button>)}</div><label>Публичное имя<input value={name} onChange={event => setName(event.target.value)} maxLength={80} /></label><label>{pageTab==='Моя Сцена'?'Роль':'Описание направления'}<input value={tagline} onChange={event => setTagline(event.target.value)} maxLength={80} /></label><p className="cab-helper">Изменения видны только в этом макете. Публикация на живом сайте не происходит.</p></section><section className="cab-live-card"><img src="/assets/maria-noir.webp" alt="Редакционный портрет Марии" /><span>ПРЕДПРОСМОТР / {pageTab.toUpperCase()}</span><h3>{name || 'Ваше имя'}</h3><p>{tagline || 'Ваша роль'}</p><a href="/">Открыть концепт сайта <ArrowRight size={17} /></a></section></div> : null}
    {view === 'requests' ? <div className="cab-panel cab-wide"><div className="cab-panel-top"><div><span className="cab-overline">РАБОТА / ЗАЯВКИ</span><h2>Входящие обращения</h2></div><span className="cab-pill">Пример состояния</span></div><div className="cab-tabs">{['Все','Новые','В работе','Завершённые'].map(filter=><button type="button" key={filter} className={requestFilter===filter?'active':''} aria-pressed={requestFilter===filter} onClick={()=>setRequestFilter(filter)}>{filter}</button>)}</div><div className="cab-empty"><CirclesFour size={36} weight="light" /><h3>Заявки будут здесь</h3><p>Статусы и действия сохраняют привычный порядок кабинета MBstudio. В этом концепте реальные обращения не загружаются.</p></div></div> : null}
    {view === 'services' ? <div className="cab-panel cab-wide"><span className="cab-overline">РАБОТА / УСЛУГИ</span><h2>Направления и услуги</h2><p className="cab-panel-lead">Та же структура каталога: группы, услуга, цена и способ записи.</p><div className="cab-list"><div><Sparkle size={23} /><strong>Макияж</strong><span>Группа услуг</span><CaretRight size={19} /></div><div><Images size={23} /><strong>Курсы</strong><span>Обучение</span><CaretRight size={19} /></div><div><Camera size={23} /><strong>Модельная работа</strong><span>Съёмки и проекты</span><CaretRight size={19} /></div></div></div> : null}
    {view === 'schedule' ? <div className="cab-panel cab-wide"><span className="cab-overline">РАБОТА / ГРАФИК</span><h2>Рабочая неделя</h2><p className="cab-panel-lead">Временные слоты здесь показаны как визуальный пример.</p><div className="cab-week">{['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС'].map((day,index)=><div key={day} className={index>4?'off':''}><span>{day}</span><strong>{index>4?'—':'10:00'}</strong><small>{index>4?'Выходной':'до 18:00'}</small></div>)}</div><p className="cab-helper">В рабочем кабинете сохраняются существующие исключения и правила записи.</p></div> : null}
    {['photos','promotion','shop','settings','pro','help'].includes(view) ? <div className="cab-panel cab-wide"><span className="cab-overline">MBSTUDIO / {title.toUpperCase()}</span><h2>{title} в новом оформлении</h2><p className="cab-panel-lead">Раздел остаётся в навигации кабинета. Здесь показаны его визуальный язык, иерархия и состояния до переноса реальных данных и действий.</p><div className="cab-list">{(view==='promotion'?['Публикации','Поиск и индексация','QR-коды']:view==='settings'?['Подключения','SMS','Резервная копия']:view==='photos'?['Библиотека фотографий','Обложки страниц','Места использования']:view==='help'?['SCENA Ассистент','Команда SCENA','Подписка PRO']:view==='pro'?['Подписка PRO','Возможности','История заявок']:['Товары','Рекомендации','Заказы']).map((item,index)=><div key={item}><span className="cab-list-number">0{index+1}</span><strong>{item}</strong><span>Раздел</span><CaretRight size={19} /></div>)}</div></div> : null}
  </>;
}

export function Cabinet() {
  const [view, setView] = useState('overview');
  const [menuOpen, setMenuOpen] = useState(false);
  function navigate(next) { setView(next); setMenuOpen(false); window.scrollTo({ top: 0, behavior: 'auto' }); }
  useEffect(() => { function escape(event) { if (event.key === 'Escape') setMenuOpen(false); } document.addEventListener('keydown', escape); return () => document.removeEventListener('keydown', escape); }, []);
  return <div className="cab-shell">
    <aside className={`cab-sidebar ${menuOpen?'cab-sidebar-open':''}`} aria-label="Разделы кабинета">
      <div className="cab-sidebar-head"><a href="/" className="cab-logo">MBStudio<span>.</span><small>SCENA.live</small></a><button type="button" className="cab-menu-close" onClick={() => setMenuOpen(false)} aria-label="Закрыть меню"><X size={26}/></button></div>
      <p className="cab-workspace-label">WORKSPACE <span> / DESIGN STUDY</span></p>
      <nav>{navigation.map((item,index) => { const Icon=item.icon; return <div key={item.id}>{(index===0 || item.group!==navigation[index-1].group) && <p className="cab-nav-group">{item.group}</p>}<button type="button" aria-current={view===item.id?'page':undefined} className={view===item.id?'cab-nav-active':''} onClick={() => navigate(item.id)}><Icon size={19} weight="light" /><span>{item.label}</span>{view===item.id?<span className="cab-active-mark"/>:null}</button></div>; })}</nav>
      <div className="cab-sidebar-foot"><span className="cab-avatar">MC</span><div><strong>Maria Cravcenco</strong><small>MBstudio · концепт</small></div></div>
    </aside>
    {menuOpen && <button type="button" className="cab-overlay" onClick={() => setMenuOpen(false)} aria-label="Закрыть меню" />}
    <div className="cab-main-wrap"><header className="cab-topbar"><button type="button" className="cab-menu-trigger" onClick={() => setMenuOpen(true)} aria-label="Открыть меню" aria-expanded={menuOpen}><List size={26}/></button><span className="cab-mobile-logo">MBStudio.</span><span className="cab-topbar-title">Кабинет / {navigation.find(item=>item.id===view)?.label}</span><a href="/" className="cab-site-link">Публичная страница <ArrowRight size={17}/></a></header><main className="cab-main"><DemoNotice />{view==='overview'?<Overview navigate={navigate}/>:<Detail key={view} view={view} navigate={navigate}/>}<footer className="cab-footer"><span>MBStudio. <i>by SCENA.live</i></span><span>Концепт кабинета · 2026</span></footer></main></div>
  </div>;
}
