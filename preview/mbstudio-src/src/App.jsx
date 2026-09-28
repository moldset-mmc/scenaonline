import { useEffect, useRef, useState } from 'react';
import { ArrowRight, InstagramLogo, List, X } from '@phosphor-icons/react';

const base = 'https://mbstudio.scena.life/en';
const links = [
  ['My Scene', `${base}/`],
  ['Services and courses', `${base}/makeup/`],
  ['Shopping', `${base}/market/`],
  ['Portfolio', `${base}/portfolio/professional/`],
  ['Become a model', `${base}/become-a-model/`],
];
const booking = `${base}/booking/`;
const portrait = `${import.meta.env.BASE_URL}assets/maria-noir.webp`;

function ExternalLink({ href, children, className, onClick, ...props }) {
  return <a href={href} target="_blank" rel="noopener noreferrer" className={className} onClick={onClick} {...props}>{children}</a>;
}

export function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuTrigger = useRef(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    function onKeyDown(event) {
      if (event.key === 'Escape') {
        setMenuOpen(false);
        menuTrigger.current?.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [menuOpen]);

  return (
    <div className="site-shell">
      <main>
        <section className="hero" aria-labelledby="hero-title">
          <img className="hero-photo" src={portrait} alt="Maria Cravcenco in an editorial makeup portrait" />
          <div className="hero-shade" aria-hidden="true" />
          <header className="site-header">
            <ExternalLink href={`${base}/`} className="brand" aria-label="MBStudio, My Scene home">
              <span className="brand-name">MBStudio.</span>
              <span className="brand-credit">SCENA.live</span>
            </ExternalLink>
            <nav className="desktop-nav" aria-label="Main navigation">
              {links.map(([label, href]) => <ExternalLink href={href} key={label}>{label}</ExternalLink>)}
              <a href="/cabinet/">Cabinet preview</a>
            </nav>
            <button className="language-button" type="button" onClick={event => { menuTrigger.current = event.currentTarget; setMenuOpen(true); }} aria-label="Choose language and open menu" aria-expanded={menuOpen} aria-controls="mobile-menu">EN</button>
            <button className="menu-button" type="button" onClick={event => { menuTrigger.current = event.currentTarget; setMenuOpen(true); }} aria-label="Open menu" aria-expanded={menuOpen} aria-controls="mobile-menu">
              <List size={30} weight="light" aria-hidden="true" />
            </button>
          </header>

          <div className="hero-content">
            <div className="accent-rule" aria-hidden="true" />
            <h1 id="hero-title">Maria<br />Cravcenco</h1>
            <p className="role">Model &amp; Makeup Artist</p>
            <p className="intro">I combine beauty,<br className="small-only" /> character, and movement—<br className="small-only" /> from precise makeup to a<br className="small-only" /> striking stage presence.</p>
            <ExternalLink href={booking} className="book-button">Book <ArrowRight size={25} weight="light" aria-hidden="true" /></ExternalLink>
            <ExternalLink href="https://www.instagram.com/masha_cravcenco/" className="instagram-link"><InstagramLogo size={24} weight="regular" aria-hidden="true" />Instagram</ExternalLink>
          </div>
        </section>

        <section className="publications" aria-labelledby="publications-title">
          <div className="section-heading"><span className="section-rule" aria-hidden="true" /><div><h2 id="publications-title">Publications</h2><p>Stories and offers</p></div></div>
          <ExternalLink href={`${base}/publications/scene/`} className="publication-card" aria-label="See all publications on MBstudio">
            <img src={portrait} alt="Editorial portrait of Maria" />
            <span className="publication-card-caption">Explore the scene <ArrowRight size={20} aria-hidden="true" /></span>
          </ExternalLink>
          <ExternalLink href={`${base}/publications/scene/`} className="all-publications">All publications <ArrowRight size={19} aria-hidden="true" /></ExternalLink>
        </section>

        <footer className="site-footer">
          <span>MBStudio. <span className="footer-muted">by SCENA.live</span></span>
          <ExternalLink href={booking}>Book a session <ArrowRight size={17} aria-hidden="true" /></ExternalLink>
        </footer>
      </main>

      {menuOpen && <div className="menu-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />}
      <div id="mobile-menu" className={`menu-panel ${menuOpen ? 'is-open' : ''}`} role="dialog" aria-modal={menuOpen ? 'true' : undefined} aria-label="Navigation" aria-hidden={!menuOpen}>
        <div className="menu-head"><span className="brand-name">MBStudio.</span><button type="button" className="menu-close" onClick={() => { setMenuOpen(false); menuTrigger.current?.focus(); }} aria-label="Close menu"><X size={28} weight="light" aria-hidden="true" /></button></div>
        <nav aria-label="Mobile navigation">
          {links.map(([label, href], index) => <ExternalLink href={href} key={label} onClick={() => setMenuOpen(false)}><small>0{index + 1}</small>{label}<ArrowRight size={20} aria-hidden="true" /></ExternalLink>)}
          <a href="/cabinet/" onClick={() => setMenuOpen(false)}><small>06</small>Cabinet preview<ArrowRight size={20} aria-hidden="true" /></a>
        </nav>
        <ExternalLink href={booking} className="menu-book" onClick={() => setMenuOpen(false)}>Book <ArrowRight size={22} aria-hidden="true" /></ExternalLink>
        <div className="menu-languages" aria-label="Language versions"><span>EN</span><ExternalLink href="https://mbstudio.scena.life/ru/">RU</ExternalLink><ExternalLink href="https://mbstudio.scena.life/ro/">RO</ExternalLink></div>
      </div>
    </div>
  );
}
