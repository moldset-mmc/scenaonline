"use client";
import {useEffect,useRef,useState} from "react";
import {ArrowLeft,ArrowRight,Check,Download,FileDown,LockKeyhole,RotateCcw,X} from "lucide-react";
import PersonalCard from "./personal-card";
import CardFields from "./card-fields";
import CardRequest from "./card-request";
import {CARD_DRAFT_KEY,type CardDraft,emptyCard,palette,readPortrait,restoreCard,serializeCard,validateCard} from "@/lib/card";
import {cardHtml,cardPng,saveBlob} from "@/lib/card-export";

const steps=["Вы","Фото","Оформление","Визитка"];
const titles=["Начнём с вашего имени.","Теперь — ваш взгляд.","Примерьте настроение.","Это вы. Ваша SCENA."];
const descriptions=["Напишите, как вас представить. Ваша визитка меняется сразу.","Один портрет расскажет о вас больше. Выберите тот, в котором нравитесь себе.","Выберите цвет и, если хотите, добавьте пару слов и контакт.","Сохраните визитку себе или отправьте её близкому человеку."];
function initial(){try{return restoreCard(localStorage.getItem(CARD_DRAFT_KEY));}catch{return null;}}
export default function CardJourney({onBack,previewOnly=false}:{onBack:()=>void;previewOnly?:boolean}){
  const [saved]=useState(initial),[draft,setDraft]=useState<CardDraft>(saved?.draft||{...emptyCard}),[step,setStep]=useState(saved?.step||0),[completed,setCompleted]=useState<number[]>(saved?.completed||[]);
  const [errors,setErrors]=useState<Record<string,string>>({}),[notice,setNotice]=useState(""),[restored,setRestored]=useState(!!saved),[storageError,setStorageError]=useState(false),[photoBusy,setPhotoBusy]=useState(false),[exporting,setExporting]=useState(false),[resetting,setResetting]=useState(false),[requestOpen,setRequestOpen]=useState(false),[focus,setFocus]=useState<{field?:string}|null>(null);
  const title=useRef<HTMLHeadingElement>(null),finalCard=useRef<HTMLElement>(null),photoVersion=useRef(0);
  const latest=useRef({draft,step,completed});latest.current={draft,step,completed};
  const isComplete=(i:number)=>completed.includes(i)&&!Object.keys(validateCard(draft,i)).length;
  useEffect(()=>{if(!focus)return;const timer=requestAnimationFrame(()=>{const target=focus.field?document.getElementById(focus.field):title.current;target?.focus({preventScroll:true});if(focus.field)target?.scrollIntoView({block:"center"});else document.querySelector(".journey-header")?.scrollIntoView({block:"start"});});return()=>cancelAnimationFrame(timer);},[focus]);
  function persist(){const {draft:d,step:s,completed:c}=latest.current;try{if(JSON.stringify(d)===JSON.stringify(emptyCard)){localStorage.removeItem(CARD_DRAFT_KEY);}else localStorage.setItem(CARD_DRAFT_KEY,serializeCard(d,s,c.filter(i=>!Object.keys(validateCard(d,i)).length)));setStorageError(false);}catch{setStorageError(true);}}
  useEffect(()=>{const timer=setTimeout(persist,250);return()=>clearTimeout(timer);},[draft,step,completed]);
  useEffect(()=>{const flush=()=>persist();window.addEventListener("pagehide",flush);return()=>{window.removeEventListener("pagehide",flush);photoVersion.current++;};},[]);
  function update<K extends keyof CardDraft>(key:K,value:CardDraft[K]){setDraft(prev=>({...prev,[key]:value}));setErrors(prev=>({...prev,[key]:""}));if(key==="theme")setNotice(`Настроение «${palette({...draft,theme:value as CardDraft["theme"]}).name}» уже на вашей визитке.`);else setNotice("");}
  function go(target:number){
    if(photoBusy||exporting)return;
    if(target>step){for(let i=0;i<target;i++){const found=validateCard(draft,i);if(Object.keys(found).length){setErrors(found);setStep(i);setFocus({field:Object.keys(found)[0]});return;}}}
    setStep(target);setErrors({});setNotice("");setFocus({});setResetting(false);
  }
  function next(){const found=validateCard(draft,step);if(Object.keys(found).length){setErrors(found);setFocus({field:Object.keys(found)[0]});return;}setCompleted(prev=>prev.includes(step)?prev:[...prev,step]);go(Math.min(3,step+1));}
  async function upload(file:File|undefined){if(!file)return;const version=++photoVersion.current;setPhotoBusy(true);setNotice("");try{const photo=await readPortrait(file);if(version!==photoVersion.current)return;setDraft(d=>({...d,photo,photoScale:1,photoY:40}));setNotice("Ваше фото уже на визитке. Если нужно, поправьте кадр ниже.");}catch(reason){if(version===photoVersion.current)setNotice(reason instanceof Error?reason.message:"Не удалось открыть фото.");}finally{if(version===photoVersion.current)setPhotoBusy(false);}}
  function removePhoto(){photoVersion.current++;setPhotoBusy(false);setDraft(d=>({...d,photo:"",photoScale:1,photoY:40}));setNotice("Оставили вашу инициалу. Фото можно добавить снова.");}
  async function download(format:"png"|"html"){
    if(exporting||!finalCard.current)return;setExporting(true);setNotice("");
    try{const blob=format==="png"?await cardPng(draft):new Blob([await cardHtml(finalCard.current,draft)],{type:"text/html;charset=utf-8"});saveBlob(blob,`My-SCENA.${format}`);setNotice(format==="png"?"Файл PNG подготовлен. Проверьте загрузки браузера — оттуда его можно отправить или сохранить в фото.":"HTML-визитка подготовлена. Сохраните файл и откройте его в браузере: движение фото и контакт работают без сайта.");}
    catch(reason){setNotice(reason instanceof Error?reason.message:"Не удалось сохранить. Попробуйте ещё раз.");}finally{setExporting(false);}
  }
  function reset(){photoVersion.current++;setPhotoBusy(false);setDraft({...emptyCard});setStep(0);setCompleted([]);setErrors({});setNotice("");setRestored(false);setResetting(false);setRequestOpen(false);setFocus({});try{localStorage.removeItem(CARD_DRAFT_KEY);}catch{setStorageError(true);}}
  return <div className="card-journey">
    <header className="journey-header"><a className="journey-wordmark" href="#" onClick={e=>{e.preventDefault();onBack();}} aria-label="SCENA.LIVE — начало">SCENA.LIVE<span>✳</span></a><button className="form-cover-back" type="button" onClick={onBack}><ArrowLeft size={17}/> К началу</button></header>
    <main className={`journey-main${step===3?" is-finale":""}`}>
      <div className="journey-intro"><h1>{step===3?"Ваша первая сцена.":<>Собираем <em>вашу визитку.</em></>}</h1><p>{step===3?"Уже можно сохранить. Дальше — по вашему желанию.":"Четыре шага. Один образ — ваш."}</p></div>
      <nav className="journey-progress" aria-label="Шаги создания визитки">{steps.map((label,index)=><button type="button" key={label} aria-label={`Шаг ${index+1}: ${label}${isComplete(index)?", заполнено":""}`} aria-current={index===step?"step":undefined} className={index===step?"is-current":""} onClick={()=>go(index)} disabled={photoBusy||exporting}><span>{isComplete(index)?<Check size={14}/>:index+1}</span><strong>{label}</strong></button>)}</nav>
      {restored&&<div className="journey-restored"><span>Восстановили вашу визитку и пройденные шаги.</span><button type="button" aria-label="Закрыть уведомление" onClick={()=>setRestored(false)}><X size={17}/></button></div>}
      <div className="journey-body">
        <aside className="journey-preview" aria-label="Результат вашего выбора"><div className="journey-preview-caption"><span>{step===3?"Ваша визитка":"Меняется вместе с вами"}</span><span>{step===3?"Готова к сохранению":`${step+1} / 4`}</span></div><PersonalCard draft={draft} compact={step!==3} interactive={step===3} cardRef={finalCard}/>{step!==3&&<p className="journey-preview-note">{draft.photo?"В центре — вы.":"Сначала ваше имя. Затем ваша фотография."}</p>}</aside>
        <section className="journey-editor" aria-labelledby="journey-title"><div className="journey-heading"><h2 ref={title} id="journey-title" tabIndex={-1}>{titles[step]}</h2><p>{descriptions[step]}</p></div>
          {step<3?<form onSubmit={e=>{e.preventDefault();next();}} noValidate><CardFields draft={draft} step={step} errors={errors} update={update} upload={upload} removePhoto={removePhoto} photoBusy={photoBusy}/><div className="journey-actions">{step>0?<button type="button" className="journey-back" onClick={()=>go(step-1)} disabled={photoBusy}><ArrowLeft size={18}/> Назад</button>:<span className="journey-no-signup"><LockKeyhole size={15}/> Без регистрации</span>}<button type="submit" className="journey-primary" disabled={photoBusy}>{step===0?"Выбрать фотографию":step===1?draft.photo?"Примерить оформление":"Продолжить без фото":"Увидеть свою визитку"}<ArrowRight size={18}/></button></div></form>:<div className="journey-result"><button className="journey-primary" type="button" onClick={()=>void download("png")} disabled={exporting}><Download size={19}/>{exporting?"Готовим файл…":"Сохранить визитку · PNG"}</button><p className="journey-hint">Изображение для телефона и мессенджеров.{draft.contact.trim()?" Ваш контакт будет на изображении.":""}</p><button className="journey-secondary" type="button" onClick={()=>void download("html")} disabled={exporting}><FileDown size={19}/> Скачать живую визитку · HTML</button><p className="journey-hint">Файл с движением фото и оборотом для контакта. Открывается в браузере.</p><button className="journey-text-button" type="button" onClick={()=>go(0)}><RotateCcw size={16}/> Изменить визитку</button><div className="journey-next"><h3>Хотите свою ссылку?</h3><p>Следующий шаг — обсудить публикацию вашей визитки в SCENA.</p><button className="journey-text-button" type="button" aria-expanded={requestOpen} onClick={()=>setRequestOpen(p=>!p)}>{requestOpen?"Свернуть заявку":"Обсудить запуск"}<ArrowRight size={17}/></button>{requestOpen&&<CardRequest draft={draft} previewOnly={previewOnly}/>}</div><p className="journey-publication-note">Визитка пока не опубликована. Сохранение файла не создаёт сайт или публичную ссылку.</p></div>}
          <div className="journey-feedback" role="status" aria-live="polite">{notice}</div>
          {storageError&&<p className="journey-error" role="alert">Браузер не сохранил черновик. Не закрывайте страницу до скачивания визитки.</p>}
        </section>
      </div>
      <footer className="journey-footer"><span>Данные и фото сохраняются только в этом браузере до отправки заявки.</span>{resetting?<div className="journey-reset-confirm"><span>Удалить эту визитку из браузера?</span><button type="button" onClick={reset}>Да, начать заново</button><button type="button" onClick={()=>setResetting(false)}>Отмена</button></div>:<button type="button" disabled={photoBusy||exporting} onClick={()=>setResetting(true)}>Начать заново</button>}</footer>
    </main>
  </div>;
}
