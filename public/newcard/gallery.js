(async()=>{
  const status=document.getElementById('status'), container=document.getElementById('photos');
  const id=location.pathname.split('/').pop(),token=location.hash.slice(1);
  const urls=[];
  addEventListener('pagehide',()=>urls.forEach(url=>URL.revokeObjectURL(url)),{once:true});
  if(!/^[a-f0-9-]{36}$/.test(id)||!/^[a-f0-9]{64}$/.test(token)){status.textContent='Откройте полную ссылку из сообщения Telegram.';return;}
  try{
    const headers={Authorization:`Bearer ${token}`};
    const response=await fetch(`/api/intake/${id}/gallery`,{headers,cache:'no-store'});
    if(!response.ok)throw new Error('Ссылка недоступна или срок её действия истёк.');
    const {count}=await response.json();
    for(let i=0;i<count;i++){
      status.textContent=`Загружаем фотографии: ${i+1} из ${count}…`;
      const res=await fetch(`/api/intake/${id}/photos/${i}`,{headers,cache:'no-store'});
      if(!res.ok)throw new Error('Не удалось загрузить фотографию. Обновите страницу.');
      const blob=await res.blob(),url=URL.createObjectURL(blob);urls.push(url);
      const figure=document.createElement('figure'),img=document.createElement('img'),link=document.createElement('a');
      img.src=url;img.alt=`Фотография ${i+1} из анкеты`;link.href=url;
      link.download=`scena-${i+1}.${({'image/jpeg':'jpg','image/png':'png','image/webp':'webp'})[blob.type]||'jpg'}`;
      link.textContent='Скачать фотографию';figure.append(img,link);container.append(figure);
    }
    status.textContent=count?'Доступ по этой ссылке действует 30 дней с момента отправки анкеты. Не пересылайте её посторонним.':'К анкете не приложены фотографии.';
  }catch(error){status.textContent=error.message||'Не удалось открыть фотографии.';}
})();
