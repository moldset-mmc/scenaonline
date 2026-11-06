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
            <div className="stage-statement"><h2>Ваш выход.</h2><p className="stage-description">Ваше фото, имя и контакт.<br/> Создайте визитку и сохраните её себе.</p></div>
            <div className="cover-actions"><Button asChild className="cover-primary"><a href="#anketa">Собрать свою визитку <ArrowRight size={20}/></a></Button></div>
          </div>
          <div className="stage-controls"><a href="#example" className="stage-explore"><ChevronDown size={18}/><span>Посмотреть пример</span></a><Button type="button" variant="ghost" className="stage-motion" aria-label={reducedMotion?"Анимация выключена настройками устройства":motionPaused?"Продолжить анимацию":"Приостановить анимацию"} aria-pressed={motionPaused||reducedMotion} disabled={reducedMotion} onClick={()=>setMotionPaused(p=>!p)}>{motionPaused||reducedMotion?<Play size={16}/>:<Pause size={16}/>}<span>{reducedMotion?"Без анимации":motionPaused?"Продолжить":"Пауза"}</span></Button></div>
        </section>
        <section className="cover-example" id="example" aria-labelledby="example-title">
          <div className="example-layout">
            <div className="example-heading"><h2 id="example-title" tabIndex={-1}>Ваша визитка.</h2><p className="example-intro">Три оформления. Без регистрации.</p></div>
            <figure className="example-personal-card"><PersonalCard draft={{...emptyCard,name:"Ваше имя",specialty:"Ваше направление",photo:"/images/scena-stage.webp",theme:"night"}} interactive={false}/><figcaption>На визитке будет ваше фото.</figcaption></figure>
            <div className="example-links"><Button asChild className="cover-primary"><a href="#anketa">Собрать свою визитку <ArrowRight size={20}/></a></Button><a className="example-live-link" href="https://makeup.scena.life/card/" target="_blank" rel="noreferrer">Действующая визитка <ArrowUpRight size={18}/></a></div>
          </div>
        </section>
      </main>
      <footer className="cover-footer">SCENA.LIVE · FASHION · BEAUTY · PEOPLE</footer>
      {shareNotice&&<div className="share-notice" role="status">{shareNotice}<Button type="button" variant="ghost" onClick={()=>setShareNotice("")}>Понятно</Button></div>}
    </div>
    {formOpened&&<div hidden={view!=="form"} id="anketa" ref={formTop} tabIndex={-1} className="intake-view"><CardJourney previewOnly={previewOnly} onBack={()=>navigate("#")}/></div>}
  </>;
}
