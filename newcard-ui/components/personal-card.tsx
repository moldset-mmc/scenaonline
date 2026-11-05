"use client";
import {useEffect,useRef,useState, type CSSProperties} from "react";
import {ArrowLeft,ArrowUpRight,Pause,Play,RotateCw,MapPin} from "lucide-react";
import {type CardDraft, contactLink, palette, profession} from "@/lib/card";
import {personalCardCss} from "@/lib/card-presentation";

export default function PersonalCard({draft,compact=false,interactive=true,cardRef}:{draft:CardDraft;compact?:boolean;interactive?:boolean;cardRef?:React.RefObject<HTMLElement|null>}){
  const [back,setBack]=useState(false),[paused,setPaused]=useState(false),[visible,setVisible]=useState(true);
  const ownRef=useRef<HTMLElement>(null),returnRef=useRef<HTMLButtonElement>(null),contactRef=useRef<HTMLButtonElement>(null);
  const ref=cardRef||ownRef,colors=palette(draft),href=contactLink(draft.contactType,draft.contact);
  useEffect(()=>{const target=ref.current;if(!target)return;let inView=true;const sync=()=>setVisible(inView&&document.visibilityState!=="hidden");const observer=new IntersectionObserver(([entry])=>{inView=entry.isIntersecting;sync();});observer.observe(target);document.addEventListener("visibilitychange",sync);return()=>{observer.disconnect();document.removeEventListener("visibilitychange",sync);};},[ref]);
  useEffect(()=>{if(!href)setBack(false);},[href]);
  function flip(next:boolean){setBack(next);requestAnimationFrame(()=>{(next?returnRef:contactRef).current?.focus({preventScroll:true});});}
  const css={"--card-surface":colors.surface,"--card-ink":colors.ink,"--card-accent":colors.accent,"--photo-scale":draft.photoScale,"--photo-y":`${draft.photoY}%`} as CSSProperties;
  return <><style>{personalCardCss}</style><article ref={ref} className={`personal-card${compact?" personal-card--compact":""}${draft.name.length>30?" has-long-name":""}`} style={css} data-theme={draft.theme} data-motion={draft.motion&&!paused&&visible?"on":"off"} aria-label={`Визитка: ${draft.name.trim()||"ваше имя"}`}>
    <div className="personal-card-front" hidden={back}>
      <div className="personal-card-art" aria-hidden="true">{draft.photo?<img src={draft.photo} alt=""/>:<div className="personal-card-monogram">{draft.name.trim().slice(0,1)||"S"}</div>}</div>
      <div className="personal-card-wash" aria-hidden="true"/>
      <div className="personal-card-top"><span className="personal-card-brand">SCENA.LIVE<span>✳</span></span>{interactive&&draft.photo&&draft.motion&&<button className="personal-card-motion" type="button" data-card-action="pause" aria-label={paused?"Продолжить движение фото":"Приостановить движение фото"} aria-pressed={paused} onClick={()=>setPaused(p=>!p)}>{paused?<Play size={15}/>:<Pause size={15}/>}</button>}</div>
      <div className="personal-card-copy"><h3>{draft.name.trim()||"Ваше имя"}</h3><p className="personal-card-profession">{profession(draft)||"Ваше направление"}</p>{draft.city.trim()&&<p className="personal-card-city"><MapPin size={14}/>{draft.city.trim()}</p>}{draft.tagline.trim()&&<p className="personal-card-tagline">{draft.tagline.trim()}</p>}</div>
      {href&&<div className="personal-card-contact">{interactive?<button ref={contactRef} type="button" data-card-action="contact" onClick={()=>flip(true)}><RotateCw size={16}/> Контакт <ArrowUpRight size={17}/></button>:<span>{draft.contact.trim()}</span>}</div>}
    </div>
    <div className="personal-card-back" hidden={!back} onKeyDown={e=>{if(e.key==="Escape")flip(false);}}>
      <div className="personal-card-top"><span className="personal-card-brand">SCENA.LIVE<span>✳</span></span><button ref={returnRef} type="button" data-card-action="front" onClick={()=>flip(false)} aria-label="Вернуться к фотографии"><ArrowLeft size={20}/></button></div>
      <div className="personal-card-back-copy"><h3>{draft.name.trim()}</h3><p>{profession(draft)}</p><p className="personal-card-back-label">Будем на связи</p>{href&&<a href={href} target={href.startsWith("https:")?"_blank":undefined} rel="noreferrer"><span><small>{draft.contactType}</small><strong>{draft.contact.trim()}</strong></span><ArrowUpRight size={22}/></a>}</div>
      <p className="personal-card-signature">Ваше имя. Ваша сцена.</p>
    </div>
  </article></>;
}
