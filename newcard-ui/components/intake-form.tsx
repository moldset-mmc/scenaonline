"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, ArrowRight, ArrowLeft, Check, Plus, X, Send, LockKeyhole, ImagePlus, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { answerSchema, Answers, blankAnswers, features, languages, MAX_PHOTOS, MAX_PHOTO_BYTES, readiness, specialties, styles } from "@/lib/intake";
const steps = ["Знакомство", "Ваш сайт", "Услуги", "Стиль и фото", "Домен и аккаунты", "Связь и отправка"];
const headings = ["Начнём с вас.", "Что будет на вашей сцене?", "Красота — ваша работа.", "Покажите свой стиль.", "Ваше место в интернете.", "Осталось познакомиться."];
const descriptions = ["Расскажите немного о себе. Мы соберём сайт, в котором узнают именно вас.", "Выберите, что нужно вашему бизнесу. Остальное можно добавить позже.", "Расскажите, на что к вам приходят. Детальный прайс можно подготовить позже.", "Пара ориентиров поможет почувствовать вас. Идеально подготовленные материалы не нужны.", "Если пока ничего нет — всё настроим вместе. Здесь нужны только общие сведения.", "Оставьте контакт, и мы обсудим запуск. По кнопке анкета сразу уйдёт в SCENA.LIVE."];
const fieldSteps: Record<string,number> = {name:0,specialty:0,brand:0,city:0,features:1,languages:1,services:2,booking:2,style:3,about:3,inspiration:3,domainStatus:4,domain:4,github:4,vercel:4,accountEmail:4,contact:5,timing:5,notes:5,consent:5};
type Photo = {file:File;url:string;key:string};
function clientId(){
  if(typeof crypto.randomUUID === "function")return crypto.randomUUID();
  const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,b=>b.toString(16).padStart(2,"0")).join("");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
const DRAFT_KEY = "scena-intake-draft-v1";
type ModelContext = {registerTool:(tool:Record<string,unknown>,options?:{signal:AbortSignal})=>void};
export default function IntakeForm({previewOnly=false,onBack}:{previewOnly?:boolean;onBack?:()=>void}) {
  const [a,setA]=useState<Answers>({...blankAnswers});
  const [step,setStep]=useState(0);
  const [photos,setPhotos]=useState<Photo[]>([]);
  const [errors,setErrors]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState("");
  const [restored,setRestored]=useState(false);
  const [loaded,setLoaded]=useState(false);
  const [receipt,setReceipt]=useState<{id:string;delivered:boolean}|null>(null);
  const [deliveryReady,setDeliveryReady]=useState<boolean|null>(null);
  const [website,setWebsite]=useState("");
  const id=useRef("");
  const titleRef=useRef<HTMLHeadingElement>(null);
  const photoRef=useRef<Photo[]>([]);
  const stateRef=useRef({a,step,photos,busy});
  stateRef.current={a,step,photos,busy};photoRef.current=photos;
  useEffect(()=>{
    try {
      const raw=localStorage.getItem(DRAFT_KEY);
      if(raw){const parsed=JSON.parse(raw);if(typeof parsed.submissionId === "string" && /^[0-9a-f-]{36}$/.test(parsed.submissionId))id.current=parsed.submissionId;const saved:Record<string,unknown>={};
        if(parsed.answers && typeof parsed.answers === "object")for(const [key,value] of Object.entries(parsed.answers)){
          if(key === "consent" || !(key in answerSchema.shape))continue;
          if(typeof value === "string" && value.length <= 500 && typeof blankAnswers[key as keyof Answers] === "string")saved[key]=value;
          if(Array.isArray(value) && Array.isArray(blankAnswers[key as keyof Answers]) && value.length <= 6 && value.every(v=>typeof v === "string" && v.length <= 100))saved[key]=value;
        }
        if(Object.keys(saved).length){setA({...blankAnswers,...saved,consent:false} as Answers);setStep(Math.min(5,Math.max(0,Number(parsed.step)||0)));setRestored(true);}}
    }catch{}
    setLoaded(true);
    if(previewOnly)setDeliveryReady(false);else fetch("/api/intake/status").then(r=>r.json() as Promise<{ready?:boolean}>).then(d=>setDeliveryReady(d.ready===true)).catch(()=>setDeliveryReady(false));
    return ()=>photoRef.current.forEach(p=>URL.revokeObjectURL(p.url));
  },[]);
  useEffect(()=>{
    if(!loaded||receipt)return;
    const hasChanges=Object.keys(blankAnswers).some(k=>k!=="consent" && JSON.stringify(a[k as keyof Answers])!==JSON.stringify(blankAnswers[k as keyof Answers]));
    if(!hasChanges){try{localStorage.removeItem(DRAFT_KEY);}catch{}return;}
    const timer=setTimeout(()=>{try{const {consent:_,...answers}=a;localStorage.setItem(DRAFT_KEY,JSON.stringify({answers,step,submissionId:id.current}));}catch{}},350);
    return ()=>clearTimeout(timer);
  },[a,step,loaded,receipt]);
  useEffect(()=>{
    const context=(document as Document&{modelContext?:ModelContext}).modelContext;
    if(!context)return;const controller=new AbortController();
    try{
      context.registerTool({name:"get_intake_progress",title:"Read questionnaire progress",description:"Current step and photo count, without personal answers.",inputSchema:{type:"object",properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:false},execute:async(input:unknown)=>{
        if(!input||typeof input!=="object"||Object.keys(input).length)throw new Error("No parameters expected");
        return {step:stateRef.current.step+1,totalSteps:6,photoCount:stateRef.current.photos.length};
      }},{signal:controller.signal});
      context.registerTool({name:"navigate_intake",title:"Go to questionnaire step",description:"Changes form step. Does not submit answers.",inputSchema:{type:"object",properties:{step:{type:"integer",minimum:1,maximum:6}},required:["step"],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},execute:async(input:unknown)=>{
        const n=(input as {step?:unknown})?.step;
        if(!input||typeof input!=="object"||Object.keys(input).length!==1||typeof n!=="number"||!Number.isInteger(n)||n<1||n>6)throw new Error("Step must be between 1 and 6");
        if(stateRef.current.busy)throw new Error("Submission in progress");window.location.hash="anketa";setStep(n-1);return {step:n};
      }},{signal:controller.signal});
    }catch{}
    return ()=>controller.abort();
  },[]);
  function update<K extends keyof Answers>(key:K,value:Answers[K]){setA(prev=>({...prev,[key]:value}));setErrors(prev=>({...prev,[key]:""}));setNotice("");}
  function go(n:number){if(busy)return;setStep(n);setNotice("");setTimeout(()=>titleRef.current?.focus(),30);}
  function validate(currentOnly:boolean){
    const result=answerSchema.safeParse(a);const nextErrors:Record<string,string>={};
    if(!result.success)result.error.issues.forEach(issue=>{const key=String(issue.path[0]);if((!currentOnly||fieldSteps[key]===step)&&!nextErrors[key])nextErrors[key]=issue.message;});
    setErrors(nextErrors);const first=Object.keys(nextErrors)[0];
    if(first){if(!currentOnly)go(fieldSteps[first]??0);setNotice("Проверьте отмеченные поля.");return false;}return true;
  }
  function clearDraft(){ photos.forEach(p=>URL.revokeObjectURL(p.url));setPhotos([]);setA({...blankAnswers});setStep(0);setErrors({});setNotice("");setRestored(false);id.current="";try{localStorage.removeItem(DRAFT_KEY);}catch{} }
  function next(){if(validate(true))go(Math.min(5,step+1));}
  function addPhotos(files:FileList|null){
    if(!files)return;const incoming=Array.from(files);
    if(incoming.length+photos.length>MAX_PHOTOS){setNotice("Можно добавить до 6 фотографий. Удалите лишние и попробуйте снова.");return;}
    if(incoming.some(f=>!["image/jpeg","image/png","image/webp"].includes(f.type)||f.size>MAX_PHOTO_BYTES||!f.size)){setNotice("Подойдут JPG, PNG или WebP до 4 МБ. HEIC сначала сохраните как JPG.");return;}
    setPhotos(prev=>[...prev,...incoming.map(file=>({file,url:URL.createObjectURL(file),key:clientId()}))]);setNotice("");
  }
  async function submit(){
    if(busy||!validate(false))return;if(deliveryReady!==true){setNotice("Приём заявок ещё не подключён.");return;}setBusy(true);setNotice("");id.current||=clientId();
    try{const {consent:_,...answers}=a;localStorage.setItem(DRAFT_KEY,JSON.stringify({answers,step,submissionId:id.current}));}catch{}
    try{
      type Result={stored?:boolean;delivered?:boolean;error?:string;uploadToken?:string};
      const request=async(url:string,options:RequestInit)=>{
        const res=await fetch(url,options);const result=await res.json() as Result;
        if(!res.ok){if(res.status===409&&url.endsWith("/start"))id.current="";throw new Error(result.error||"Не удалось отправить. Повторите попытку.");}
        return result;
      };
      const manifest=[];
      for(const p of photos){
        const digest=await crypto.subtle.digest("SHA-256",await p.file.arrayBuffer());
        manifest.push({sha256:Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join(""),bytes:p.file.size,type:p.file.type});
      }
      let data=await request("/api/intake/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id.current,answers:a,website,photos:manifest})});
      if(!data.stored){
        if(!data.uploadToken)throw new Error("Сервер не подтвердил начало отправки.");
        const authorization=`Bearer ${data.uploadToken}`;
        for(let i=0;i<photos.length;i++){
          setNotice(`Загружаем фотографии: ${i+1} из ${photos.length}…`);
          await request(`/api/intake/${id.current}/photos/${i}`,{method:"PUT",headers:{Authorization:authorization,"Content-Type":photos[i].file.type},body:photos[i].file});
        }
        setNotice("Отправляем анкету…");
        data=await request(`/api/intake/${id.current}/send`,{method:"POST",headers:{Authorization:authorization},body:""});
      }
      if(data.stored){setReceipt({id:id.current,delivered:data.delivered===true});try{localStorage.removeItem(DRAFT_KEY);}catch{}photos.forEach(p=>URL.revokeObjectURL(p.url));setPhotos([]);setNotice("");}
      else setNotice("Нет подтверждения сохранения. Ответы и фотографии остались в форме.");
    }catch(error){setNotice(error instanceof Error&&error.message!=="Failed to fetch"?error.message:"Нет подтверждения от сервера. Ответы остались в форме. Проверьте интернет и повторите отправку — повторная заявка не создастся.");}finally{setBusy(false);}
  }

  function field(key:keyof Answers,label:string,placeholder:string,max:number,required=false,type="text"){
    return <div className="field"><label htmlFor={key}>{label}{required&&<span className="required"> *</span>}</label><Input id={key} name={key} value={String(a[key])} onChange={e=>update(key,e.target.value as never)} placeholder={placeholder} maxLength={max} type={type} autoComplete={key==="name"?"name":key==="accountEmail"?"email":"off"} aria-invalid={!!errors[key]} aria-describedby={errors[key]?`${key}-error`:undefined}/>{errors[key]&&<p className="field-error" id={`${key}-error`}>{errors[key]}</p>}</div>;
  }
  function area(key:"services"|"about"|"notes",label:string,placeholder:string,max:number){return <div className="field"><label htmlFor={key}>{label}<span className="optional">необязательно</span></label><Textarea id={key} value={a[key]} onChange={e=>update(key,e.target.value)} placeholder={placeholder} maxLength={max} rows={4}/><span className="counter">{a[key].length} / {max}</span></div>;}
  function choices(key:keyof Answers,values:readonly string[],multi=false,design=false){
    return <div className={`choices ${design?"style-choices":""}`} role="group" aria-label={({specialty:"Специализация",features:"Возможности сайта",languages:"Языки сайта",style:"Стиль",booking:"Способ записи",domainStatus:"Готовность домена",github:"Аккаунт GitHub",vercel:"Аккаунт Vercel",timing:"Сроки"} as Record<string,string>)[key]||key}>{values.map((v,i)=>{const selected=multi?(a[key] as string[]).includes(v):a[key]===v;
      return <Button type="button" key={v} variant="outline" className={`choice ${selected?"selected":""} ${design?`style-${i}`:""}`} aria-pressed={selected} onClick={()=>update(key,(multi?selected?(a[key] as string[]).filter(x=>x!==v):[...a[key] as string[],v]:v) as never)}>{design&&<span className="style-swatch" aria-hidden="true"><span>Aa</span><i/><i/></span>}<span>{v}</span><span className="choice-mark" aria-hidden="true">{selected?<Check size={14}/>:multi?<Plus size={14}/>:null}</span></Button>;
    })}{errors[key]&&<p className="field-error">{errors[key]}</p>}</div>;
  }
  return <div className="site-shell">
    <header className="topbar"><a className="wordmark" href="#" onClick={e=>{e.preventDefault();if(onBack)onBack();else window.location.hash="";}} aria-label="SCENA.LIVE — начало">SCENA.LIVE<span>✳</span></a><a className="form-cover-back" href="#" onClick={e=>{if(onBack){e.preventDefault();onBack();}}}><ArrowLeft size={16}/> К визитке</a><a className="demo-link" href="https://sofileroux.scena.life/ru/" target="_blank" rel="noreferrer">Пример сайта <ArrowUpRight size={16}/></a></header>
    <main className="workspace"><aside className="sidebar"><div className="eyebrow"><span className="small-dot"/> ВАШ НОВЫЙ САЙТ</div><h1>Ваша история.<br/><em>Ваша сцена.</em></h1><p className="intro">Первый шаг к сайту,<br/>который работает на вас.</p><nav className="step-list" aria-label="Шаги анкеты">{steps.map((s,i)=><Button type="button" variant="ghost" key={s} disabled={busy||!!receipt} aria-label={`Шаг ${i+1}: ${s}`} className={`step-link ${i===step&&!receipt?"active":""}`} aria-current={i===step?"step":undefined} onClick={()=>go(i)}><span className="step-number">{i<step||receipt?<Check size={14}/>:String(i+1).padStart(2,"0")}</span><span>{s}</span>{i===step&&!receipt&&<ArrowRight size={15}/>}</Button>)}</nav><div className="side-note"><div className="asterisk" aria-hidden="true">✳</div><p>Не нужно знать всё.<br/><strong>Нужное придумаем вместе.</strong></p></div></aside>
    <section className="form-panel" aria-label="Анкета на создание сайта">{receipt?<div className="receipt" role="status"><div className={`receipt-symbol ${receipt.delivered?"":"pending"}`}>{receipt.delivered?<Check size={40}/>:<Send size={36}/>}</div><div className="eyebrow">{receipt.delivered?"ДОСТАВЛЕНО В SCENA.LIVE":"АНКЕТА СОХРАНЕНА"}</div><h2>{receipt.delivered?"Ваша история начинается.":"Спасибо. Всё сохранили."}</h2><p>{receipt.delivered?"Анкета и ссылка на фотографии уже отправлены в Telegram команды SCENA.LIVE. Мы свяжемся с вами по указанному контакту.":"Анкета и фотографии сохранены, но Telegram пока не подтвердил уведомление. Повторно заполнять ничего не нужно."}</p><span className="receipt-id">Номер анкеты: {receipt.id}</span><a className="receipt-link" href="https://sofileroux.scena.life/ru/" target="_blank" rel="noreferrer">Посмотреть пример сайта <ArrowUpRight size={18}/></a></div>:<>
      <div className="form-top"><span className="eyebrow">ДАВАЙТЕ ЗНАКОМИТЬСЯ</span><span className="step-count">{String(step+1).padStart(2,"0")} <span>/ 06</span></span></div><div className="progress-track" role="progressbar" aria-label="Шаг анкеты" aria-valuenow={step+1} aria-valuemin={1} aria-valuemax={6}><span style={{width:`${((step+1)/6)*100}%`}}/></div><div className="step-heading"><h2 ref={titleRef} tabIndex={-1}>{headings[step]}</h2><p>{descriptions[step]}</p></div>
      {restored&&<div className="draft-restored">Восстановили текст вашего черновика. Фотографии нужно добавить заново.<Button type="button" variant="ghost" onClick={()=>setRestored(false)} aria-label="Закрыть уведомление"><X size={16}/></Button></div>}
      <form onSubmit={e=>{e.preventDefault();if(step<5)next();else void submit();}} noValidate><fieldset disabled={busy} className="step-fields">
      {step===0&&<><div className="two-columns">{field("name","Как вас зовут?","Ваше имя",70,true)}{field("brand","Название бренда","Имя или название студии",80)}</div><div className="field"><span className="field-label">Чем вы занимаетесь? <span className="required">*</span></span>{choices("specialty",specialties)}</div>{field("city","В каком городе вы работаете?","Например, Кишинёв",80)}<div className="quiet-tip"><span>01 — 06</span><p>Можно отвечать коротко и своими словами.<br/>Это знакомство, а не экзамен.</p></div></>}
      {step===1&&<><div className="field"><span className="field-label">Что нужно на сайте? <span className="required">*</span></span><p className="field-hint">Можно выбрать несколько вариантов</p>{choices("features",features,true)}</div><div className="field"><span className="field-label">На каких языках?</span>{choices("languages",languages,true)}</div></>}
      {step===2&&<>{area("services","Ваши основные услуги и цены","Например: вечерний макияж — 900 MDL, 1 час.\nУкладка — 600 MDL, 45 минут.",450)}<div className="field"><span className="field-label">Как клиенту удобнее записаться?</span>{choices("booking",["Заявка на сайте","Через мессенджер","Обсудим вместе"])}</div></>}
      {step===3&&<><div className="field"><span className="field-label">Какое настроение вам ближе?</span>{choices("style",styles,false,true)}</div>{field("inspiration","Сайт или Instagram, который нравится","Ссылка, @профиль или несколько слов",200)}{area("about","Пара слов о вас","Ваш опыт, подход и то, за что вас любят клиенты",220)}<div className="field"><label htmlFor="photos">Ваши фотографии<span className="optional">необязательно</span></label><p className="field-hint">Портрет, работы, студия или логотип. До 6 файлов JPG, PNG, WebP по 4 МБ.</p><label className="upload-zone" htmlFor="photos"><ImagePlus size={27}/><span><strong>Добавить фотографии</strong><small>С телефона или компьютера</small></span><Plus size={20}/></label><Input id="photos" className="file-input" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e=>{addPhotos(e.target.files);e.target.value="";}}/><div className="photo-grid">{photos.map((p,i)=><div className="photo" key={p.key}><img src={p.url} alt={`Выбранная фотография ${i+1}`}/><Button type="button" size="icon" variant="secondary" aria-label={`Удалить фотографию ${i+1}`} onClick={()=>{URL.revokeObjectURL(p.url);setPhotos(prev=>prev.filter(x=>x.key!==p.key));}}><X size={16}/></Button><small>{(p.file.size/1024/1024).toFixed(1)} МБ</small></div>)}</div><p className="field-hint">Фотографии передадутся вместе с анкетой. Автоматически на сайте они не публикуются.</p></div></>}
      {step===4&&<><div className="field"><span className="field-label">Есть свой домен — адрес сайта?</span>{choices("domainStatus",readiness)}</div>{field("domain","Домен или желаемое название","Например, yourname.com",120)}<div className="account-row"><div><strong>GitHub</strong><p>Аккаунт для кода вашего сайта</p></div>{choices("github",readiness)}</div><div className="account-row"><div><strong>Vercel</strong><p>Аккаунт для размещения сайта</p></div>{choices("vercel",readiness)}</div>{field("accountEmail","Email для новых аккаунтов","Если уже определились",160,false,"email")}<div className="info-note"><LockKeyhole size={18}/><p>Пароли и ключи доступа здесь не нужны. Подключение аккаунтов обсудим лично.</p></div></>}
      {step===5&&<>{field("contact","Как с вами связаться?","@telegram, телефон или email",160,true)}<div className="field"><span className="field-label">Когда хотели бы запустить сайт?</span>{choices("timing",["Как можно скорее","В течение месяца","Без спешки"])}</div>{area("notes","Что ещё нам стоит знать?","Пожелания, бюджет или вопрос, который хотите обсудить",250)}<div className="consent-row"><Checkbox id="consent" checked={a.consent} onCheckedChange={v=>update("consent",v===true)} aria-invalid={!!errors.consent}/><label htmlFor="consent">Согласен(-на) передать контакты, ответы и приложенные фото команде SCENA.LIVE для подготовки сайта. У меня есть разрешение на использование этих материалов.</label></div>{errors.consent&&<p className="field-error">{errors.consent}</p>}<p className="privacy-note">Анкета и фото сохранятся в закрытом хранилище. Команда получит ответы и приватную ссылку на фото в Telegram. Материалы не публикуются; удалить их можно, обратившись к специалисту, который прислал анкету.</p>{deliveryReady===false&&<p className="connection-note">Это предпросмотр. Приём заявок появится после подключения Telegram.</p>}</>}
      <div className="honeypot" aria-hidden="true"><label htmlFor="website">Website</label><Input id="website" value={website} onChange={e=>setWebsite(e.target.value)} tabIndex={-1} autoComplete="off"/></div></fieldset>
      {notice&&<p className="notice" role="alert">{notice}</p>}<div className="form-actions"><div>{step>0&&<Button type="button" variant="ghost" disabled={busy} className="back-button" onClick={()=>go(step-1)}><ArrowLeft size={18}/>Назад</Button>}</div><Button type="submit" className="primary-button" disabled={busy||(step===5&&deliveryReady!==true)}>{busy?<><LoaderCircle className="spin" size={18}/>Сохраняем и отправляем…</>:step===5?<>Отправить анкету <Send size={18}/></>:<>Продолжить <ArrowRight size={18}/></>}</Button></div><div className="form-footnote"><LockKeyhole size={13}/><span>{step===5?"Нажатие сразу отправляет анкету. Дополнительного подтверждения нет.":"Текст черновика сохраняется только на этом устройстве."}</span><Button type="button" variant="link" disabled={busy} className="clear-draft" onClick={clearDraft}>Очистить</Button></div></form>
    </>}</section></main><footer className="footer"><span>SCENA.LIVE — пространство вашего бренда</span><span>Сделано с вниманием к вам <span className="footer-star">✳</span></span></footer>
  </div>;
}
