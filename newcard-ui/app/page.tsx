"use client";
import {useEffect,useRef,useState} from "react";
import {ArrowUpRight,ArrowRight,Share2,Check,ChevronDown,Pause,Play} from "lucide-react";
import {Button} from "@/components/ui/button";
import CardJourney from "@/components/card-journey";
import PersonalCard from "@/components/personal-card";
import {emptyCard} from "@/lib/card";

export default function Home({previewOnly=false,allowPreviewSharing=false}:{previewOnly?:boolean;allowPreviewSharing?:boolean}){
  const [view,setView]=useState<"cover"|"form">("cover");
  const [formOpened,setFormOpened]=useState(false);
  const [shareNotice,setShareNotice]=useState("");
  const [copied,setCopied]=useState(false);
  const [motionPaused,setMotionPaused]=useState(false);
  const [reducedMotion,setReducedMotion]=useState(false);
  const [sceneVisible,setSceneVisible]=useState(true);
  const [pageVisible,setPageVisible]=useState(true);
  const sceneRef=useRef<HTMLElement>(null);
  const formTop=useRef<HTMLDivElement>(null);
  const coverTitle=useRef<HTMLHeadingElement>(null);
  const formOpener=useRef<HTMLElement|null>(null);
  const currentView=useRef(view);
  currentView.current=view;
  const [navigation,setNavigation]=useState<{fragment:string;opener:HTMLElement|null}|null>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  useEffect(()=>{
    const preference=window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync=()=>setReducedMotion(preference.matches);
    sync();preference.addEventListener("change",sync);
    const observer=new IntersectionObserver(([entry])=>setSceneVisible(entry.isIntersecting));
    if(sceneRef.current)observer.observe(sceneRef.current);
    const visibility=()=>setPageVisible(!document.hidden);visibility();document.addEventListener("visibilitychange",visibility);
    return()=>{preference.removeEventListener("change",sync);observer.disconnect();document.removeEventListener("visibilitychange",visibility);};
  },[]);
  useEffect(()=>{
    function followHash(){
      showView(window.location.hash);
    }
    // Leave focus alone on a normal landing; direct section links still need navigation.
    if(window.location.hash==="#anketa"||window.location.hash==="#example")followHash();
    // Hash changes also cover browser Back/Forward; one listener avoids duplicate focus moves.
    window.addEventListener("hashchange",followHash);
    return()=>{window.removeEventListener("hashchange",followHash);if(timer.current)clearTimeout(timer.current);};
  },[]);
  useEffect(()=>{
    if(!navigation)return;
    if(navigation.fragment==="#anketa"){
      window.scrollTo(0,0);formTop.current?.focus({preventScroll:true});
    }else if(navigation.fragment==="#example"){
      document.getElementById("example")?.scrollIntoView({block:"start"});
      document.getElementById("example-title")?.focus({preventScroll:true});
    }else if(navigation.opener?.isConnected){
      navigation.opener.focus({preventScroll:true});
      navigation.opener.scrollIntoView({block:"center"});
    }else{
      window.scrollTo(0,0);coverTitle.current?.focus({preventScroll:true});
    }
  },[navigation]);
  function showView(fragment:string){
    const isForm=fragment==="#anketa";
    const opener=currentView.current==="form"&&!isForm?formOpener.current:null;
    if(isForm)setFormOpened(true);
    setView(isForm?"form":"cover");
    setNavigation({fragment,opener});
  }
  function navigate(fragment:string){
    window.history.pushState(null,"",fragment);
    showView(fragment);
  }
  function internalLink(event:React.MouseEvent<HTMLDivElement>){
    if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    const link=(event.target as Element).closest('a[href^="#"]');
    if(!link||event.defaultPrevented)return;
    const href=link.getAttribute("href");if(href==="#"||href==="#anketa"||href==="#example"){
      if(href==="#anketa")formOpener.current=link as HTMLElement;
      event.preventDefault();navigate(href);
    }
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
        <section ref={sceneRef} className={`cover-hero${motionPaused||reducedMotion||!sceneVisible||!pageVisible||view!=="cover"?" is-paused":""}${reducedMotion?" reduced-motion":""}`} aria-labelledby="cover-title">
          <div className="stage-art"><img className="stage-image" src="/images/scena-stage.webp" alt="Большой подиум SCENA.LIVE: светящийся выход, софиты и модель в глубине сцены" width={1536} height={1024} fetchPriority="high"/><div className="stage-light stage-light-left"/><div className="stage-light stage-light-right"/></div>
          <div className="stage-shade" aria-hidden="true"/>
          <div className="stage-brand"><p>МИР КРАСОТЫ. ЛЮДИ. ВОЗМОЖНОСТИ.</p><h1 id="cover-title" ref={coverTitle} tabIndex={-1}>SCENA.LIVE</h1></div>
          <div className="stage-bottom">
            <div className="stage-statement"><h2>Ваш выход.</h2><p className="stage-description">Ваше имя. Ваша фотография. Ваш характер.<br/> Соберите визитку, которую хочется показать.</p></div>
            <div className="cover-actions"><Button asChild className="cover-primary"><a href="#anketa">Собрать свою визитку <ArrowRight size={20}/></a></Button><Button asChild variant="outline" className="cover-secondary"><a href="#example">Посмотреть пример <ArrowUpRight size={20}/></a></Button></div>
          </div>
          <div className="stage-controls"><a href="#example" className="stage-explore"><ChevronDown size={18}/><span>Познакомиться с проектом</span></a><Button type="button" variant="ghost" className="stage-motion" aria-label={reducedMotion?"Анимация выключена настройками устройства":motionPaused?"Продолжить анимацию":"Приостановить анимацию"} aria-pressed={motionPaused||reducedMotion} disabled={reducedMotion} onClick={()=>setMotionPaused(p=>!p)}>{motionPaused||reducedMotion?<Play size={16}/>:<Pause size={16}/>}<span>{reducedMotion?"Без анимации":motionPaused?"Продолжить":"Пауза"}</span></Button></div>
        </section>
        <div className="cover-ribbon" aria-label="Для кого SCENA.LIVE"><span>МАСТЕРА</span><i aria-hidden="true">✳</i><span>МОДЕЛИ</span><i aria-hidden="true">✳</i><span>СТУДИИ</span></div>
        <section className="cover-example" id="example" aria-labelledby="example-title">
          <div className="example-heading"><h2 id="example-title" tabIndex={-1}>Всё начинается<br/><em>с вас.</em></h2><p className="example-intro">Сначала — простая личная визитка: фотография, имя и контакт. Свой сайт можно обсудить позже.</p></div>
          <div className="example-layout">
            <div className="example-personal-card"><PersonalCard draft={{...emptyCard,name:"Ваше имя",specialty:"Ваше направление",tagline:"Несколько слов, в которых узнают вас.",photo:"/images/scena-stage.webp",theme:"night"}} interactive={false}/></div>
            <div className="example-copy"><h3>Первое впечатление.<br/>Личное.</h3><p>Фотография, которая нравится вам. Имя, которое запомнят. Контакт, по которому легко найти.</p><p>Примерьте три настроения и заберите готовую визитку — без регистрации.</p><div className="example-links"><a className="example-live-link" href="#anketa">Создать свою <ArrowRight size={18}/></a><a className="example-live-link" href="https://makeup.scena.life/card/" target="_blank" rel="noreferrer">Посмотреть действующую визитку <ArrowUpRight size={18}/></a></div><p className="example-disclaimer">Здесь показан пример с изображением сцены. В вашей визитке будет выбранное вами фото.</p></div>
          </div>
        </section>
        <section className="cover-invitation" aria-labelledby="invitation-title"><span className="invitation-star" aria-hidden="true">✳</span><div><h2 id="invitation-title">Узнайте себя в SCENA.</h2><p>Выберите фото и настроение.<br/>Готовую визитку можно сразу сохранить.</p></div><Button asChild className="cover-primary"><a href="#anketa">Собрать свою визитку <ArrowRight size={19}/></a></Button></section>
      </main>
      <footer className="cover-footer"><span>SCENA.LIVE · FASHION · BEAUTY · PEOPLE</span><Button type="button" variant="link" onClick={shareCard}><Share2 size={16}/>Переслать визитку</Button></footer>
      {shareNotice&&<div className="share-notice" role="status">{shareNotice}<Button type="button" variant="ghost" onClick={()=>setShareNotice("")}>Понятно</Button></div>}
    </div>
    {formOpened&&<div hidden={view!=="form"} id="anketa" ref={formTop} tabIndex={-1} className="intake-view"><CardJourney previewOnly={previewOnly} onBack={()=>navigate("#")}/></div>}
  </>;
}
