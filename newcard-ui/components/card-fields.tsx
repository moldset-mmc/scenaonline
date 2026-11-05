import {useEffect,useState} from "react";
import {ImagePlus,Check,Trash2} from "lucide-react";
import {type CardDraft,cardSpecialties,cardThemes,contactTypes} from "@/lib/card";
type Props={draft:CardDraft;step:number;errors:Record<string,string>;photoBusy:boolean;update:<K extends keyof CardDraft>(key:K,value:CardDraft[K])=>void;upload:(file:File|undefined)=>void;removePhoto:()=>void};
export default function CardFields({draft:d,step,errors,photoBusy,update,upload,removePhoto}:Props){
  const [contactOpen,setContactOpen]=useState(false);
  useEffect(()=>{if(errors.contact)setContactOpen(true);},[errors.contact]);
  function field(key:"name"|"customSpecialty"|"city"|"tagline"|"contact",label:string,placeholder:string,maxLength:number,required=false){
    return <div className="journey-field"><label htmlFor={key}>{label}{!required&&<span>необязательно</span>}</label><input id={key} name={key} value={d[key]} maxLength={maxLength} required={required} autoComplete={key==="name"?"name":key==="city"?"address-level2":"off"} type={key==="contact"&&d.contactType==="Email"?"email":key==="contact"&&d.contactType==="Телефон"?"tel":"text"} placeholder={placeholder} aria-invalid={!!errors[key]} aria-describedby={errors[key]?`${key}-error`:undefined} onChange={e=>update(key,e.target.value)}/>{errors[key]&&<p className="journey-error" id={`${key}-error`}>{errors[key]}</p>}</div>;
  }
  if(step===0)return <>
    {field("name","Имя на визитке","Ваше имя или название студии",60,true)}
    <fieldset id="specialty" className="journey-options" tabIndex={-1} aria-invalid={!!errors.specialty} aria-describedby={errors.specialty?"specialty-error":undefined}><legend>Ваше направление</legend><div className="role-options">{cardSpecialties.map(value=><label key={value} className={d.specialty===value?"is-selected":""}><input type="radio" name="specialty" value={value} checked={d.specialty===value} onChange={()=>update("specialty",value)}/><span>{value}</span>{d.specialty===value&&<Check size={17} aria-hidden="true"/>}</label>)}</div>{errors.specialty&&<p id="specialty-error" className="journey-error">{errors.specialty}</p>}</fieldset>
    {d.specialty==="Своё направление"&&field("customSpecialty","Как подписать ваше направление?","Например, фотограф",50,true)}
    {field("city","Город","Например, Кишинёв",60)}
  </>;
  if(step===1)return <>
    <div className="portrait-upload"><label htmlFor="portrait"><ImagePlus size={25}/><span><strong>{photoBusy?"Готовим фотографию…":d.photo?"Выбрать другое фото":"Добавить свою фотографию"}</strong><small>JPG, PNG или WebP · до 12 МБ</small></span></label><input id="portrait" type="file" accept="image/jpeg,image/png,image/webp" disabled={photoBusy} onChange={e=>{upload(e.target.files?.[0]);e.target.value="";}}/></div>
    <p className="journey-hint">Лучше всего подойдёт портрет с пространством вокруг лица. Можно продолжить без фото — останется ваша инициала.</p>
    {d.photo&&<><details className="journey-details"><summary>Поправить кадр</summary><div className="crop-fields"><label htmlFor="photoScale">Приблизить <output>{Math.round(d.photoScale*100)}%</output></label><input id="photoScale" type="range" min="1" max="1.6" step="0.02" value={d.photoScale} onChange={e=>update("photoScale",Number(e.target.value))}/><label htmlFor="photoY">Положение по высоте</label><input id="photoY" type="range" min="0" max="100" step="1" value={d.photoY} onChange={e=>update("photoY",Number(e.target.value))}/></div></details><label className="journey-check"><input type="checkbox" checked={d.motion} onChange={e=>update("motion",e.target.checked)}/><span>Лёгкое движение фотографии<small>В живой визитке фото будет плавно приближаться.</small></span></label><button type="button" className="journey-text-button" onClick={removePhoto}><Trash2 size={16}/> Убрать фотографию</button></>}
  </>;
  if(step===2)return <>
    <fieldset className="journey-options"><legend>Какое настроение ближе вам?</legend><div className="theme-options">{cardThemes.map(theme=><label key={theme.id} className={d.theme===theme.id?"is-selected":""}><input type="radio" name="theme" value={theme.id} checked={d.theme===theme.id} onChange={()=>update("theme",theme.id)}/><span className="theme-sample" style={{background:theme.surface,color:theme.ink}} aria-hidden="true">{d.name.trim().slice(0,1)||"S"}</span><span><strong>{theme.name}</strong><small>{theme.description}</small></span>{d.theme===theme.id&&<Check size={19} aria-hidden="true"/>}</label>)}</div></fieldset>
    {field("tagline","Одна фраза о вас","Например, макияж, в котором вы узнаёте себя",100)}
    <details className="journey-details" open={contactOpen} onToggle={e=>setContactOpen(e.currentTarget.open)}><summary>Добавить контакт на визитку<span>необязательно</span></summary><p className="journey-hint">Он будет виден каждому, кому вы передадите визитку.</p><label className="contact-type-label" htmlFor="contactType">Где с вами связаться?</label><select id="contactType" value={d.contactType} onChange={e=>update("contactType",e.target.value as CardDraft["contactType"])}>{contactTypes.map(type=><option key={type}>{type}</option>)}</select>{field("contact",d.contactType,d.contactType==="Телефон"?"+373 …":d.contactType==="Email"?"name@example.com":"@your_name",160)}</details>
  </>;
  return null;
}
