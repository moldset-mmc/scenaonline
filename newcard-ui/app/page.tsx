"use client";
import {useEffect,useRef,useState} from "react";
import {ArrowUpRight,ArrowRight,Share2,Check,ChevronDown,Pause,Play} from "lucide-react";
import {Button} from "@/components/ui/button";
import IntakeForm from "@/components/intake-form";

export default function Home({previewOnly=false,allowPreviewSharing=false}:{previewOnly?:boolean;allowPreviewSharing?:boolean}){
  const [view,setView]=useState<"cover"|"form">("cover");
  const [formOpened,setFormOpened]=useState(false);
  const [shareNotice,setShareNotice]=useState("");
  const [copied,setCopied]=useState(false);
  const [motionPaused,setMotionPaused]=useState(false);
  const [reducedMotion,setReducedMotion]=useState(false);
  const [sceneVisible,setSceneVisible]=useState(true);
  const sceneRef=useRef<HTMLElement>(null);
  const formTop=useRef<HTMLDivElement>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  useEffect(()=>{
    const preference=window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync=()=>setReducedMotion(preference.matches);
    sync();preference.addEventListener("change",sync);
    const observer=new IntersectionObserver(([entry])=>setSceneVisible(entry.isIntersecting));
    if(sceneRef.current)observer.observe(sceneRef.current);
    return()=>{preference.removeEventListener("change",sync);observer.disconnect();};
  },[]);
  useEffect(()=>{
    function followHash(){
      const isForm=window.location.hash==="#anketa";
      if(isForm)setFormOpened(true);
      setView(isForm?"form":"cover");
      if(isForm || !window.location.hash)window.scrollTo(0,0);
      if(isForm)requestAnimationFrame(()=>formTop.current?.focus({preventScroll:true}));
    }
    followHash();window.addEventListener("hashchange",followHash);window.addEventListener("popstate",followHash);
    return()=>{window.removeEventListener("hashchange",followHash);window.removeEventListener("popstate",followHash);if(timer.current)clearTimeout(timer.current);};
  },[]);
  function navigate(fragment:string){
    window.history.pushState(null,"",fragment);
    const isForm=fragment==="#anketa";
    if(isForm)setFormOpened(true);
    setView(isForm?"form":"cover");
    requestAnimationFrame(()=>{
      if(fragment==="#example")document.getElementById("example")?.scrollIntoView({block:"start"});
      else window.scrollTo(0,0);
      if(isForm)formTop.current?.focus({preventScroll:true});
    });
  }
  function internalLink(event:React.MouseEvent<HTMLDivElement>){
    const link=(event.target as Element).closest('a[href^="#"]');
    if(!link||event.defaultPrevented)return;
    const href=link.getAttribute("href");if(href==="#"||href==="#anketa"||href==="#example"){event.preventDefault();navigate(href);}
  }
  async function shareCard(){
    setCopied(false);
    if((previewOnly&&!allowPreviewSharing)||window.location.protocol!=="https:"){
      setShareNotice("Ссылка для пересылки появится после публикации визитки.");return;
    }
    const url=new URL(window.location.pathname,window.location.origin).href;
    const data={title:"SCENA.LIVE — ваш выход",text:"Мастера. Модели. Студии. Познакомьтесь с проектом SCENA.LIVE и создайте свою сцену.",url};
    try{
      if(navigator.share){await navigator.share(data);setShareNotice("");return;}
      await navigator.clipboard.writeText(url);setCopied(true);setShareNotice("Ссылка скопирована. Её можно отправить в любой мессенджер.");
    }catch(error){if((error as {name?:string}).name==="AbortError")return;setShareNotice("Скопируйте адрес этой страницы из строки браузера и отправьте его в мессенджер.");}
    if(timer.current)clearTimeout(timer.current);
    timer.current=setTimeout(()=>{setCopied(false);setShareNotice("");},6000);
  }
  return <>
    <div className="cover" hidden={view!=="cover"} onClick={internalLink}>
      <header className="cover-header">
        <a className="cover-logo" href="#" aria-label="SCENA.LIVE — визитка платформы">SCENA.LIVE<span>✳</span></a>
        <span className="cover-header-caption">FASHION · BEAUTY · PEOPLE</span>
        <Button type="button" variant="ghost" className="cover-share" onClick={shareCard}>{copied?<Check size={18}/>:<Share2 size={18}/>}<span>Поделиться</span></Button>
      </header>
      <main>
        <section ref={sceneRef} className={`cover-hero${motionPaused||reducedMotion||!sceneVisible||view!=="cover"?" is-paused":""}${reducedMotion?" reduced-motion":""}`} aria-labelledby="cover-title">
          <div className="stage-art"><img className="stage-image" src="/images/scena-stage.webp" alt="Большой подиум SCENA.LIVE: светящийся выход, софиты и модель в глубине сцены" width={1536} height={1024} fetchPriority="high"/><div className="stage-light stage-light-left"/><div className="stage-light stage-light-right"/></div>
          <div className="stage-shade" aria-hidden="true"/>
          <div className="stage-brand"><p>МИР КРАСОТЫ. ЛЮДИ. ВОЗМОЖНОСТИ.</p><h1 id="cover-title">SCENA.LIVE</h1></div>
          <div className="stage-bottom">
            <div className="stage-statement"><p className="stage-eyebrow">ВАШ ТАЛАНТ В ЦЕНТРЕ ВНИМАНИЯ</p><h2>Ваш выход.</h2><p className="stage-description">Платформа для мастеров, моделей и студий.<br/> Место, где начинается ваша сцена.</p></div>
            <div className="cover-actions"><Button asChild className="cover-primary"><a href="#example">Открыть SCENA.LIVE <ArrowUpRight size={20}/></a></Button><Button asChild variant="outline" className="cover-secondary"><a href="#anketa">Хочу свою сцену <ArrowRight size={20}/></a></Button></div>
          </div>
          <div className="stage-controls"><a href="#example" className="stage-explore"><ChevronDown size={18}/><span>Познакомиться с проектом</span></a><Button type="button" variant="ghost" className="stage-motion" aria-label={reducedMotion?"Анимация выключена настройками устройства":motionPaused?"Продолжить анимацию":"Приостановить анимацию"} aria-pressed={motionPaused||reducedMotion} disabled={reducedMotion} onClick={()=>setMotionPaused(p=>!p)}>{motionPaused||reducedMotion?<Play size={16}/>:<Pause size={16}/>}<span>{reducedMotion?"Без анимации":motionPaused?"Продолжить":"Пауза"}</span></Button></div>
        </section>
        <div className="cover-ribbon" aria-label="Для кого SCENA.LIVE"><span>МАСТЕРА</span><i aria-hidden="true">✳</i><span>МОДЕЛИ</span><i aria-hidden="true">✳</i><span>СТУДИИ</span></div>
        <section className="cover-example" id="example" aria-labelledby="example-title">
          <div className="example-heading"><p className="cover-kicker">ПЕРСОНАЛЬНЫЙ САЙТ В МИРЕ SCENA.LIVE</p><h2 id="example-title">Большая сцена.<br/><em>Ваша история.</em></h2><p className="example-intro">Начните со своего пространства: работы, услуги и запись к вам — по одной ссылке. Посмотрите, как это может выглядеть.</p></div>
          <div className="example-layout">
            <a className="example-image-link" href="https://sofileroux.scena.life/ru/" target="_blank" rel="noreferrer" aria-label="Открыть демонстрационный сайт Софи Леру в новой вкладке">
              <div className="example-browser-bar"><span className="browser-lights" aria-hidden="true"><i/><i/><i/></span><span>sofileroux.scena.life</span><ArrowUpRight size={16}/></div>
              <img src="/images/sofi-site.jpg" alt="Предпросмотр сайта Софи Леру: портрет, услуги и кнопка записи на макияж" width={1348} height={926} loading="lazy"/>
            </a>
            <div className="example-copy"><span className="example-tag">ДЕМОНСТРАЦИОННЫЙ САЙТ</span><h3>Sofi Leroux</h3><p>Визажист. Модель. Своя студия.<br/>И одна ссылка, чтобы познакомиться,<br className="desktop-break"/> посмотреть работы и записаться.</p><div className="example-links"><a className="example-live-link" href="https://sofileroux.scena.life/ru/" target="_blank" rel="noreferrer">Открыть сайт <ArrowUpRight size={18}/></a><a className="example-live-link" href="https://sofileroux.scena.life/card/" target="_blank" rel="noreferrer">Визитка Sofi Leroux <ArrowUpRight size={18}/></a></div><p className="example-disclaimer">Софи — вымышленная героиня. Образ создан с помощью ИИ для показа возможностей сайта.</p></div>
          </div>
        </section>
        <section className="cover-invitation" aria-labelledby="invitation-title"><span className="invitation-star" aria-hidden="true">✳</span><div><p className="cover-kicker">В ЦЕНТРЕ — ВЫ</p><h2 id="invitation-title">Займите свою сцену.</h2><p>Расскажите о себе и добавьте фотографии.<br/>Начнём с короткой анкеты.</p></div><Button asChild className="cover-primary"><a href="#anketa">Заполнить анкету <ArrowRight size={19}/></a></Button></section>
      </main>
      <footer className="cover-footer"><span>SCENA.LIVE · FASHION · BEAUTY · PEOPLE</span><Button type="button" variant="link" onClick={shareCard}><Share2 size={16}/>Переслать визитку</Button></footer>
      {shareNotice&&<div className="share-notice" role="status">{shareNotice}<Button type="button" variant="ghost" onClick={()=>setShareNotice("")}>Понятно</Button></div>}
    </div>
    {formOpened&&<div hidden={view!=="form"} id="anketa" ref={formTop} tabIndex={-1} className="intake-view"><IntakeForm previewOnly={previewOnly} onBack={()=>navigate("#")}/></div>}
  </>;
}
