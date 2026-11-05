import {type CardDraft, loadImage, palette, photoCrop, profession} from "./card";
import {personalCardCss} from "./card-presentation";

export const cardFontUrl="/fonts/manrope-regular.woff2";
const escapeHtml=(s:string)=>s.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]!));
export function saveBlob(blob:Blob,name:string){
  const url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
}
async function fontData(){
  if(cardFontUrl.startsWith("data:"))return cardFontUrl;
  const response=await fetch(cardFontUrl);if(!response.ok)throw new Error("Не удалось подготовить шрифт. Проверьте соединение и попробуйте ещё раз.");
  const blob=await response.blob();
  return new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=reject;reader.readAsDataURL(blob);});
}
export async function cardHtml(element:HTMLElement,draft:CardDraft):Promise<string>{
  const clone=element.cloneNode(true) as HTMLElement;clone.classList.remove("personal-card--compact");
  clone.querySelector<HTMLElement>(".personal-card-front")!.hidden=false;clone.querySelector<HTMLElement>(".personal-card-back")!.hidden=true;
  clone.dataset.motion=draft.motion?"on":"off";
  const pause=clone.querySelector("[data-card-action=pause]");if(pause){pause.setAttribute("aria-pressed","false");pause.setAttribute("aria-label","Приостановить движение фото");pause.innerHTML="Пауза";}
  const font=await fontData();
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${escapeHtml(draft.name)} · SCENA</title><style>@font-face{font-family:Manrope;src:url('${font}') format('woff2');font-display:swap}*{box-sizing:border-box}body{margin:0;min-height:100svh;display:grid;place-items:center;background:#100e14;padding:28px 20px;font-family:Manrope,Arial,sans-serif}main{width:min(100%,400px)}.local-note{color:#cbbdca;font-size:12px;line-height:1.5;text-align:center;margin:18px 0 0}.personal-card-motion{font-size:10px!important}${personalCardCss}</style></head><body><main>${clone.outerHTML}<p class="local-note">Личная визитка · сохранённая копия</p></main><script>(()=>{const card=document.querySelector('.personal-card'),front=card.querySelector('.personal-card-front'),back=card.querySelector('.personal-card-back');let paused=false;card.addEventListener('click',e=>{const control=e.target.closest('[data-card-action]');if(!control)return;const action=control.dataset.cardAction;if(action==='contact'||action==='front'){const show=action==='contact';front.hidden=show;back.hidden=!show;card.querySelector(show?'[data-card-action=front]':'[data-card-action=contact]').focus();}if(action==='pause'){paused=!paused;card.dataset.motion=paused?'off':'on';control.setAttribute('aria-pressed',String(paused));control.setAttribute('aria-label',paused?'Продолжить движение фото':'Приостановить движение фото');control.textContent=paused?'Пуск':'Пауза';}});card.addEventListener('keydown',e=>{if(e.key==='Escape'&&!back.hidden)card.querySelector('[data-card-action=front]').click();});document.addEventListener('visibilitychange',()=>{card.dataset.motion=${draft.motion?"true":"false"}&&!paused&&!document.hidden?'on':'off';});})();<\/script></body></html>`;
}
function textLines(ctx:CanvasRenderingContext2D,text:string,maxWidth:number){
  const lines:string[]=[];let line="";
  for(const word of text.trim().split(/\s+/)){
    const candidate=line?`${line} ${word}`:word;
    if(ctx.measureText(candidate).width<=maxWidth){line=candidate;continue;}
    if(line){lines.push(line);line="";}
    for(const char of word){if(ctx.measureText(line+char).width>maxWidth&&line){lines.push(line);line="";}line+=char;}
  }
  if(line)lines.push(line);return lines;
}
export async function cardPng(draft:CardDraft):Promise<Blob>{
  await document.fonts?.ready;
  const canvas=document.createElement("canvas");canvas.width=1080;canvas.height=1512;
  const ctx=canvas.getContext("2d");if(!ctx)throw new Error("Браузер не смог сохранить изображение. Попробуйте скачать HTML-визитку.");
  const colors=palette(draft),W=1080,H=1512,pad=76,inner=W-pad*2;
  ctx.fillStyle=colors.surface;ctx.fillRect(0,0,W,H);
  if(draft.photo){const img=await loadImage(draft.photo);const r=photoCrop(img.naturalWidth,img.naturalHeight,W,H*.9,draft.photoScale,draft.photoY);ctx.save();ctx.beginPath();ctx.rect(0,0,W,H*.9);ctx.clip();ctx.drawImage(img,r.x,r.y,r.w,r.h);ctx.restore();}
  else{ctx.fillStyle=colors.accent;ctx.globalAlpha=.3;ctx.font="italic 620px Georgia";ctx.textAlign="center";ctx.fillText(draft.name.trim().slice(0,1)||"S",W/2,H*.53);ctx.textAlign="left";ctx.globalAlpha=1;}
  const fade=ctx.createLinearGradient(0,0,0,H);fade.addColorStop(0,draft.photo?"#08080c40":colors.surface+"00");fade.addColorStop(.3,colors.surface+"00");fade.addColorStop(.36,colors.surface+"00");fade.addColorStop(.82,colors.surface);fade.addColorStop(1,colors.surface);ctx.fillStyle=fade;ctx.fillRect(0,0,W,H);
  ctx.fillStyle=draft.photo?"#fff":colors.ink;ctx.font="700 32px Manrope,Arial";ctx.fillText("SCENA.LIVE",60,85);
  const starX=74+ctx.measureText("SCENA.LIVE").width;ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=2;for(let i=0;i<4;i++){const a=i*Math.PI/4;ctx.beginPath();ctx.moveTo(starX-Math.cos(a)*9,66-Math.sin(a)*9);ctx.lineTo(starX+Math.cos(a)*9,66+Math.sin(a)*9);ctx.stroke();}
  const contact=draft.contact.trim();let footer=58;
  ctx.font="34px Manrope,Arial";const contactLines=contact?textLines(ctx,`${draft.contactType} · ${contact}`,inner):[];
  if(contactLines.length)footer+=36+contactLines.length*44;
  const nameSize=draft.name.length>30?97:119;ctx.font=`${nameSize}px Georgia`;const names=textLines(ctx,draft.name.trim(),inner);
  ctx.font="600 38px Manrope,Arial";const roles=textLines(ctx,profession(draft),inner);
  ctx.font="35px Manrope,Arial";const cities=draft.city.trim()?textLines(ctx,draft.city.trim(),inner):[],tags=draft.tagline.trim()?textLines(ctx,draft.tagline.trim(),inner):[];
  const height=names.length*nameSize*1.08+30+roles.length*48+(cities.length?24+cities.length*44:0)+(tags.length?32+tags.length*50:0);
  let y=H-footer-height;ctx.textBaseline="top";ctx.fillStyle=colors.ink;ctx.font=`${nameSize}px Georgia`;
  for(const line of names){ctx.fillText(line,pad,y);y+=nameSize*1.08;}y+=30;
  ctx.font="600 38px Manrope,Arial";for(const line of roles){ctx.fillText(line,pad,y);y+=48;}
  ctx.fillStyle=colors.accent;ctx.font="35px Manrope,Arial";
  if(cities.length){y+=24;for(const line of cities){ctx.fillText(line,pad,y);y+=44;}}
  if(tags.length){y+=32;for(const line of tags){ctx.fillText(line,pad,y);y+=50;}}
  if(contactLines.length){const top=H-footer+26;ctx.fillStyle=colors.accent;ctx.globalAlpha=.35;ctx.fillRect(pad,top,inner,2);ctx.globalAlpha=1;ctx.fillStyle=colors.ink;ctx.font="34px Manrope,Arial";contactLines.forEach((line,i)=>ctx.fillText(line,pad,top+28+i*44));}
  return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error("Не удалось сохранить изображение. Попробуйте ещё раз.")),"image/png"));
}
