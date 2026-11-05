import {useEffect,useRef,useState} from "react";
import {ArrowRight,Check} from "lucide-react";
import {type CardDraft,profession} from "@/lib/card";
import {answerSchema,blankAnswers,specialties,styles} from "@/lib/intake";

export default function CardRequest({draft,previewOnly}:{draft:CardDraft;previewOnly:boolean}){
  const [contact,setContact]=useState(""),[consent,setConsent]=useState(false),[ready,setReady]=useState<boolean|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(""),[receipt,setReceipt]=useState<{id:string;delivered:boolean}|null>(null);
  const id=useRef("");const payloadFingerprint=useRef("");const contactRef=useRef<HTMLInputElement>(null),consentRef=useRef<HTMLInputElement>(null);
  useEffect(()=>{if(previewOnly){setReady(false);return;}const controller=new AbortController();fetch("/api/intake/status",{signal:controller.signal}).then(r=>r.json()).then(d=>setReady(d.ready===true)).catch(()=>setReady(false));return()=>controller.abort();},[previewOnly]);
  async function submit(e:React.FormEvent){
    e.preventDefault();if(busy||ready!==true)return;setError("");
    const parsed=answerSchema.safeParse({...blankAnswers,name:draft.name.trim(),specialty:specialties.includes(draft.specialty as typeof specialties[number])?draft.specialty:"Другое",city:draft.city,features:["Визитка и QR"],style:draft.theme==="air"?styles[0]:draft.theme==="wine"?styles[1]:styles[2],about:draft.tagline,inspiration:draft.contact.trim()?`Контакт на визитке (${draft.contactType}): ${draft.contact.trim()}`:"",notes:`Простая визитка без записи и других модулей. Направление: ${profession(draft)}. Кадр: ${draft.photoScale}×, высота ${draft.photoY}%. Движение: ${draft.motion?"да":"нет"}.`,contact,consent});
    if(!parsed.success){const issue=parsed.error.issues[0];setError(issue.message);if(issue.path[0]==="consent")consentRef.current?.focus();else contactRef.current?.focus();return;}
    const fingerprint=JSON.stringify({answers:parsed.data,photo:draft.photo});
    if(payloadFingerprint.current!==fingerprint){id.current=crypto.randomUUID();payloadFingerprint.current=fingerprint;}
    setBusy(true);
    try{
      type Result={stored?:boolean;delivered?:boolean;uploadToken?:string;error?:string};
      const request=async(url:string,options:RequestInit)=>{const response=await fetch(url,options),body=await response.json() as Result;if(!response.ok){if(response.status===409&&url.endsWith("/start"))payloadFingerprint.current="";throw new Error(body.error||"Не удалось отправить. Попробуйте ещё раз.");}return body;};
      let photo:Blob|undefined,manifest:{sha256:string;bytes:number;type:string}[]=[];
      if(draft.photo){const bytes=Uint8Array.from(atob(draft.photo.split(",")[1]),c=>c.charCodeAt(0));const mime=draft.photo.slice(5,draft.photo.indexOf(";"));photo=new Blob([bytes],{type:mime});const hash=await crypto.subtle.digest("SHA-256",bytes);manifest=[{sha256:Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,"0")).join(""),bytes:photo.size,type:photo.type}];}
      let result=await request("/api/intake/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id.current,answers:parsed.data,website:"",photos:manifest})});
      if(!result.stored){if(!result.uploadToken)throw new Error("Сервер не подтвердил начало отправки.");const headers={Authorization:`Bearer ${result.uploadToken}`};if(photo)await request(`/api/intake/${id.current}/photos/0`,{method:"PUT",headers:{...headers,"Content-Type":photo.type},body:photo});result=await request(`/api/intake/${id.current}/send`,{method:"POST",headers,body:""});}
      if(!result.stored)throw new Error("Нет подтверждения сохранения. Попробуйте ещё раз.");
      setReceipt({id:id.current,delivered:result.delivered===true});
    }catch(reason){setError(reason instanceof Error?reason.message:"Не удалось отправить. Визитка осталась у вас.");}finally{setBusy(false);}
  }
  if(receipt)return <div className="request-receipt" role="status"><Check size={24}/><div><h3>{receipt.delivered?"Заявка доставлена в SCENA.":"Заявка сохранена."}</h3><p>{receipt.delivered?"Команда свяжется с вами по указанному контакту.":"Уведомление команде пока не подтверждено. Повторно отправлять не нужно."}</p><small>Номер: {receipt.id}</small></div></div>;
  return <form className="card-request" onSubmit={submit} noValidate><p>Передадим команде SCENA ваше имя, направление, оформление и фотографию. Публичная ссылка появится после отдельного согласования запуска.</p><div className="journey-field"><label htmlFor="request-contact">Контакт для команды SCENA</label><input ref={contactRef} id="request-contact" value={contact} onChange={e=>{setContact(e.target.value);setError("");}} placeholder="Телефон, Telegram или email" maxLength={160} required aria-describedby={error?"request-error":undefined}/><p className="journey-hint">Этот контакт не добавляется на визитку.</p></div><label className="journey-check"><input ref={consentRef} id="request-consent" type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)} required aria-describedby={error?"request-error":undefined}/><span>Разрешаю передать команде SCENA указанные данные и фото для обсуждения запуска.</span></label>{error&&<p className="journey-error" id="request-error" role="alert">{error}</p>}{ready===false&&<p className="journey-hint">{previewOnly?"В этой копии заявки не отправляются. Визитку можно сохранить.":"Приём заявок сейчас недоступен. Сохраните визитку — к запуску можно вернуться позже."}</p>}<button className="journey-primary" type="submit" disabled={ready!==true||busy}>{busy?"Отправляем…":ready===null?"Проверяем возможность отправки…":"Отправить заявку"}<ArrowRight size={18}/></button></form>;
}
