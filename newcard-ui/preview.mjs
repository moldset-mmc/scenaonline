// Package the exact production build for private offline review. No publication.
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../public/newcard');
const target=process.argv[2];if(!target)throw new Error('Pass the output HTML filename.');
let html=await readFile(path.join(root,'index.html'),'utf8');
const script=html.match(/<script src="([^"]+)" defer><\/script>/)[1],style=html.match(/<link rel="stylesheet" href="([^"]+)">/)[1];
let js=await readFile(path.join(root,script.replace('/newcard/','')),'utf8'),css=await readFile(path.join(root,style.replace('/newcard/','')),'utf8');
const sha=value=>createHash('sha256').update(value).digest('hex');
const evidence={js:sha(js),css:sha(css)};
const mime={'.webp':'image/webp','.jpg':'image/jpeg','.svg':'image/svg+xml','.woff2':'font/woff2'};
const urls=[...new Set((js+' '+css+' '+html).match(/\/newcard\/assets\/[\w.-]+\.(?:webp|jpg|svg|woff2)/g)||[])];
for(const url of urls){const data=`data:${mime[path.extname(url)]};base64,${(await readFile(path.join(root,url.replace('/newcard/','')))).toString('base64')}`;js=js.replaceAll(url,data);css=css.replaceAll(url,data);html=html.replaceAll('https://scena.life'+url,data).replaceAll(url,data);}
// Inline scripts do not inherit the deferred execution of the external build.
// Run the unchanged bundle after its root element has been parsed.
const inlineScript=`<script>window.__SCENA_PREVIEW__=true;window.fetch=async function(url){if(url==='/api/intake/status')return {ok:true,json:async()=>({ready:false})};throw new Error('Offline preview: network disabled')};${js.replace(/<\/script/gi,'<\\/script')}</script>`;
html=html.replace(/<link rel="stylesheet"[^>]+>/,()=>`<style>${css}</style>`).replace(/<script src="[^"]+" defer><\/script>/,'').replace('</body>',()=>`${inlineScript}</body>`);
html=html.replace('<head>',`<head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"><meta name="scena-build" content='${JSON.stringify(evidence)}'>`);
await writeFile(target,html);console.log(JSON.stringify({target,bytes:Buffer.byteLength(html),sha256:sha(html),build:evidence}));
