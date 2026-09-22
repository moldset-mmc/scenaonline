import {createRequire} from 'node:module';
import {readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.dirname(fileURLToPath(import.meta.url));
const require=createRequire(import.meta.url);
const {build}=createRequire(require.resolve('drizzle-kit'))('esbuild');
const cssRequire=createRequire(require.resolve('@tailwindcss/postcss'));
const postcss=cssRequire('postcss');
const tailwind=cssRequire('@tailwindcss/postcss');
const output=path.resolve(root,'../public/newcard');
const digest=bytes=>createHash('sha256').update(bytes).digest('hex').slice(0,16);
const assets=[];
async function asset(name,bytes){
  const ext=path.extname(name),stem=path.basename(name,ext);
  const filename=`${stem}.${digest(bytes)}${ext}`;
  assets.push([filename,bytes]);
  return `/newcard/assets/${filename}`;
}
const result=await build({absWorkingDir:root,entryPoints:['entry.tsx'],bundle:true,write:false,minify:true,
  format:'iife',platform:'browser',jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'},tsconfig:'tsconfig.json'});
let js=result.outputFiles[0].text;
for(const name of ['scena-stage.webp','sofi-site.jpg']){
  js=js.replaceAll(`/images/${name}`,await asset(name,await readFile(path.join(root,'public/images',name))));
}
const css=await postcss([tailwind({base:root})]).process(await readFile(path.join(root,'app/globals.css'),'utf8'),{from:path.join(root,'app/globals.css')});
const jsUrl=await asset('app.js',Buffer.from(js));
const cssUrl=await asset('style.css',Buffer.from(css.css));
const faviconUrl=await asset('favicon.svg',await readFile(path.join(root,'public/favicon.svg')));
const html=`<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,follow"><title>SCENA.LIVE — ваш выход</title><meta name="description" content="Большая сцена для вашего таланта. Визитка проекта SCENA.LIVE, пример персонального сайта и анкета."><link rel="canonical" href="https://scena.life/newcard"><meta property="og:title" content="SCENA.LIVE — ваш выход"><meta property="og:description" content="Мастера. Модели. Студии. Ваша сцена начинается здесь."><meta property="og:type" content="website"><meta property="og:url" content="https://scena.life/newcard"><link rel="icon" href="${faviconUrl}"><link rel="stylesheet" href="${cssUrl}"><script src="${jsUrl}" defer></script></head><body><div id="root"></div><noscript>Для просмотра визитки и заполнения анкеты включите JavaScript.</noscript></body></html>`;
await mkdir(output,{recursive:true});
await rm(path.join(output,'assets'),{recursive:true,force:true});
await mkdir(path.join(output,'assets'));
for(const [name,bytes] of assets)await writeFile(path.join(output,'assets',name),bytes);
await writeFile(path.join(output,'index.html'),html);
console.log(JSON.stringify({output,assets:assets.length,bytes:assets.reduce((n,[,b])=>n+b.length,Buffer.byteLength(html))}));
