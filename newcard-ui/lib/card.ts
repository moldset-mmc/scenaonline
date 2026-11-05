export const cardSpecialties = ["Визажист", "Стилист", "Бьюти-мастер", "Модель", "Салон / студия", "Своё направление"] as const;
export const cardThemes = [
  {id:"air", name:"Воздух", description:"Светлая, тёплая, мягкая", surface:"#f0e7df", ink:"#352630", accent:"#765262"},
  {id:"wine", name:"Акцент", description:"Винная, выразительная, тёплая", surface:"#65283d", ink:"#fff1e5", accent:"#edc7b9"},
  {id:"night", name:"Вечер", description:"Тёмная, спокойная, глубокая", surface:"#181b24", ink:"#f6eade", accent:"#d0b8c3"},
] as const;
export const contactTypes = ["Instagram", "Telegram", "Телефон", "Email"] as const;
export type CardDraft = {
  name:string; specialty:string; customSpecialty:string; city:string; tagline:string;
  theme:typeof cardThemes[number]["id"]; photo:string; photoScale:number; photoY:number; motion:boolean;
  contactType:typeof contactTypes[number]; contact:string;
};
export const emptyCard:CardDraft = {name:"",specialty:"",customSpecialty:"",city:"",tagline:"",theme:"air",photo:"",photoScale:1,photoY:40,motion:true,contactType:"Instagram",contact:""};
export const CARD_DRAFT_KEY = "scena-personal-card-v1";
export const profession = (d:CardDraft) => d.specialty === "Своё направление" ? d.customSpecialty.trim() : d.specialty;
export const palette = (d:CardDraft) => cardThemes.find(t=>t.id===d.theme) || cardThemes[0];
export function contactLink(type:CardDraft["contactType"], raw:string):string|null {
  const value=raw.trim(); if(!value)return null;
  if(type==="Instagram" && /^@?[a-zA-Z0-9._]{1,30}$/.test(value))return `https://www.instagram.com/${value.replace(/^@/,"")}/`;
  if(type==="Telegram" && /^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$/.test(value))return `https://t.me/${value.replace(/^@/,"")}`;
  if(type==="Телефон" && /^\+?[\d ()-]{7,30}$/.test(value) && value.replace(/\D/g,"").length>=7 && value.replace(/\D/g,"").length<=15)return `tel:${value.replace(/[^\d+]/g,"")}`;
  if(type==="Email" && /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(value))return `mailto:${encodeURIComponent(value)}`;
  return null;
}
export function validateCard(d:CardDraft, step:number):Record<string,string> {
  const errors:Record<string,string>={};
  if(step===0){
    if(d.name.trim().length<2)errors.name="Напишите имя или название — хотя бы 2 символа.";
    if(!cardSpecialties.includes(d.specialty as typeof cardSpecialties[number]))errors.specialty="Выберите своё направление.";
    if(d.specialty==="Своё направление" && d.customSpecialty.trim().length<2)errors.customSpecialty="Напишите, чем вы занимаетесь.";
  }
  if(step===2 && d.contact.trim() && !contactLink(d.contactType,d.contact))errors.contact=d.contactType==="Телефон"?"Введите номер с кодом страны, например +373 600 00 000.":d.contactType==="Email"?"Проверьте адрес email, например name@example.com.":`Укажите имя в ${d.contactType}, например @your_name, без ссылки.`;
  return errors;
}
export function restoreCard(raw:string|null):{draft:CardDraft;step:number;completed:number[]}|null {
  if(!raw)return null;
  try{
    const saved=JSON.parse(raw);if(saved.version!==1 || !saved.draft || typeof saved.draft!=="object")return null;
    const d={...emptyCard}, source=saved.draft;
    const limits={name:60,specialty:40,customSpecialty:50,city:60,tagline:100,contact:160};
    for(const key of Object.keys(limits) as (keyof typeof limits)[])if(typeof source[key]==="string")d[key]=source[key].slice(0,limits[key]);
    if(cardThemes.some(t=>t.id===source.theme))d.theme=source.theme;
    if(contactTypes.includes(source.contactType))d.contactType=source.contactType;
    if(typeof source.photo==="string" && source.photo.length<1600000 && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(source.photo))d.photo=source.photo;
    if(typeof source.photoScale==="number" && Number.isFinite(source.photoScale))d.photoScale=Math.max(1,Math.min(1.6,source.photoScale));
    if(typeof source.photoY==="number" && Number.isFinite(source.photoY))d.photoY=Math.max(0,Math.min(100,source.photoY));
    if(typeof source.motion==="boolean")d.motion=source.motion;
    const completed:number[] = Array.isArray(saved.completed)?[...new Set<number>(saved.completed.filter((n:unknown)=>typeof n==="number"&&Number.isInteger(n)&&n>=0&&n<3&&Object.keys(validateCard(d,n)).length===0))]:[];
    let step=Number.isInteger(saved.step)?Math.max(0,Math.min(3,saved.step)):0;
    for(let i=0;i<step;i++)if(Object.keys(validateCard(d,i)).length){step=i;break;}
    return {draft:d,step,completed};
  }catch{return null;}
}
export function serializeCard(draft:CardDraft,step:number,completed:number[]){return JSON.stringify({version:1,draft,step,completed});}
export async function readPortrait(file:File):Promise<string>{
  if(!["image/jpeg","image/png","image/webp"].includes(file.type))throw new Error("Выберите JPG, PNG или WebP. Фото HEIC сначала сохраните как JPG.");
  if(!file.size || file.size>12*1024*1024)throw new Error("Выберите фотографию до 12 МБ.");
  const data=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error("Не удалось прочитать фото. Попробуйте другой файл."));reader.readAsDataURL(file);});
  const img=await loadImage(data);
  if(img.naturalWidth*img.naturalHeight>60000000)throw new Error("Фотография слишком большая. Уменьшите её до 60 мегапикселей.");
  const ratio=Math.min(1,1400/Math.max(img.naturalWidth,img.naturalHeight));
  const canvas=document.createElement("canvas");canvas.width=Math.round(img.naturalWidth*ratio);canvas.height=Math.round(img.naturalHeight*ratio);
  const ctx=canvas.getContext("2d");if(!ctx)throw new Error("Браузер не смог обработать фото. Попробуйте открыть страницу в другом браузере.");
  ctx.fillStyle="#efe6de";ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);
  const result=canvas.toDataURL("image/jpeg",.86);
  if(result.length>1500000)throw new Error("Не удалось уменьшить фото. Выберите другой снимок.");
  return result;
}
export function loadImage(src:string):Promise<HTMLImageElement>{return new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error("Не удалось открыть фотографию. Выберите другой файл."));img.src=src;});}
export function photoCrop(iw:number,ih:number,w:number,h:number,scale:number,y:number){
  const fit=Math.max(w/iw,h/ih)*scale, dw=iw*fit, dh=ih*fit;
  return {x:(w-dw)/2,y:(h-dh)*y/100,w:dw,h:dh};
}
