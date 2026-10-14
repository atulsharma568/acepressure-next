'use strict';
// 1.6.7: a Design studio file shows the name it was uploaded with, next to its stored name (files uploaded before 1.6.7 have none).
const assetLabel=(name,original)=>original?original+' · '+name:name;
// 1.6.7: the upload still running, so a redraw of Design studio during it draws the upload form busy and the batch adds its
// files and its list to the form on screen; a list that finished while you were on another tab waits here and shows once.
let artBatch=null,artReport=null;
async function designer(root){
 const d=await A('visuals'),p=panel('OBS design studio'),f=el('form');
 p.append(note('Preview changes here before saving. Previews are silent and never queue OBS alerts or change totals. Styles apply to all goals; each goal keeps its own title, target, period and progress style.'));
 p.append(note('Alert sounds live in Sound library: upload your memes, choose what viewers can pick, and set your default sound.','fine'),button('Open Sound library',()=>{tab='Sound library';draw();}));
 const specs=[['Design','theme','select',[{value:'frame',label:'Frame'},{value:'minimal',label:'Minimal'},{value:'spotlight',label:'Spotlight'}]],['Accent color','accent','color'],['Text color','text','color'],['Background color','background','color'],['Corner radius · 0–40','radius','number'],['Progress thickness · 6–40','bar_height','number'],['Horizontal alert width · 400–1400','alert_width','number'],['Goal width · 320–1400','goal_width','number'],['Alert art size · 48–240','image_size','number'],['Show goal percentage','show_percent','checkbox'],['Entry animation','animation','select',[{value:'slide',label:'Slide in'},{value:'fade',label:'Fade in'},{value:'none',label:'No animation'}]]];
 for(const [label,key,type,items] of specs)field(f,label,key,type,d.visuals[key],items);
 const assets=[{value:'',label:'None'},...d.assets.map(x=>({value:x,label:assetLabel(x,d.asset_labels?.[x])})).sort((a,b)=>a.label.localeCompare(b.label,undefined,{numeric:true,sensitivity:'base'}))];  // by the name you know
 for(const [key,label] of [['alert_image','Alert image / GIF / video'],['goal_image','Goal background image'],['logo','Goal logo']])field(f,label,key,'select',d.visuals[key],key==='alert_image'?assets:assets.filter(x=>!x.value.endsWith('.webm')));
 const previews=el('div',undefined,'design-previews'),frames=[];
 // Alerts render at the OBS source size (2560×1440 / 1080×1920) and are scaled down, so text wraps exactly as on stream.
 const fit=new ResizeObserver(list=>{for(const {target} of list){const frame=target.firstChild;frame.style.transform='scale('+(target.clientWidth/parseInt(frame.style.width))+')';}});
 for(const kind of ['alert','goal'])for(const layout of ['horizontal','vertical']){const box=el('div',undefined,'design-preview '+layout);box.append(el('h3',({alert:'Alert',goal:'Goal'})[kind]+' · '+({horizontal:'Horizontal',vertical:'Vertical'})[layout]));const frame=el('iframe');frame.title=kind+' '+layout+' preview';frame.src='/admin/visual-preview?kind='+kind+'&layout='+layout;if(kind==='alert'){const [w,h]=layout==='vertical'?[1080,1920]:[2560,1440],clip=el('div',undefined,'preview-clip');clip.style.aspectRatio=w+' / '+h;frame.style.width=w+'px';frame.style.height=h+'px';clip.append(frame);box.append(clip);fit.observe(clip);}else{frame.style.width=layout==='vertical'?'270px':'100%';frame.style.height=layout==='vertical'?'320px':'230px';box.append(frame);}previews.append(box);frames.push(frame);}
 function preview(){for(const frame of frames)frame.contentWindow?.postMessage({type:'ace-preview',visuals:formData(f)},location.origin);}
 f.addEventListener('input',preview);f.append(button('Preview again',preview),el('button','Save appearance','primary'));
 f.onsubmit=async e=>{e.preventDefault();try{const r=await A('visuals',formData(f));toast(r.default_reset?'Appearance saved. Your default sound went back to Chime because the new alert visual has no sound of its own.':'Appearance saved. OBS will update automatically.');}catch(e){toast(e.message);}};
 p.append(f);root.append(p,previews);
 const upload=panel('Upload your artwork'),uf=el('form'),input=field(uf,'PNG / WebP / GIF (8 MB) or MP4 / WebM (24 MB, 20 seconds) · choose several to upload them all','file','file');input.accept='.png,.webp,.gif,.mp4,.webm';input.required=true;input.multiple=true;
 upload.append(note('Transparent images and animated GIF/WebP are supported. Images are resized and metadata removed. Upload, then select the new file above and save. MP4/WebM require FFmpeg; their embedded audio is removed. To keep a video’s own sound, upload it as an alert bundle in Sound library. SVG is not supported.','fine'));
 // 1.6.7: several files at once, uploaded one after another; one that fails is listed and the rest still go up. A sign-out, or
 // AcePressure not answering, stops the batch and lists the files not tried. A second click while files upload is ignored (a
 // video can take a while to convert, and each click would upload it again).
 const go=el('button','Upload image','primary'),report=el('div');report.hidden=true;uf.append(go,report);
 input.onchange=()=>{const n=input.files.length;go.textContent=n>1?'Upload '+n+' files':'Upload image';};
 if(artBatch){Object.assign(artBatch,{f,go,input,report});go.disabled=input.disabled=true;go.textContent=artBatch.text;}  // redrawn while a batch uploads
 if(artReport){report.className=artReport.className;report.replaceChildren(...artReport.childNodes);report.hidden=false;artReport=null;}
 const addAsset=(form,name,original)=>{for(const select of form.querySelectorAll('select[name$="image"],select[name="logo"]')){if(name.endsWith('.webm')&&select.name!=='alert_image')continue;const opt=el('option',assetLabel(name,original));opt.value=name;select.append(opt);}};
 uf.onsubmit=async e=>{e.preventDefault();if(go.disabled)return;go.disabled=input.disabled=true;const files=[...input.files],done=[],failed=[];let left=[],stop='',maybe='';report.hidden=true;
  const batch=artBatch={f,go,input,report,text:''},hold=e=>{e.preventDefault();e.returnValue='';};addEventListener('beforeunload',hold);  // leaving would drop the rest
  try{for(const [i,pick] of files.entries()){batch.go.textContent=batch.text=files.length>1?'Uploading '+(i+1)+' of '+files.length+'…':'Uploading…';
    try{tooBig(pick,/\.(mp4|webm)$/i.test(pick.name)?24:8,files.length>1?'This file':'That file');const ud=new FormData();ud.set('file',pick,pick.name);
     const r=await fetch('/api/admin/visual-assets',{method:'POST',headers:{'X-CSRF-Token':csrf},body:ud});const result=await readJSON(r);
     if(r.status>=502&&r.status<=504)throw TypeError(result.error);  // Funnel reached this PC but not AcePressure
     if(!r.ok){if(files.length>1&&(r.status===401||r.status===403)){failed.push([pick.name,result.error]);stop='sign';left=files.slice(i+1).map(y=>y.name);break;}throw Error(result.error);}
     addAsset(batch.f,result.name,result.original_name||pick.name);done.push(assetLabel(result.name,result.original_name||pick.name));}  // as the menus show it
    catch(err){if(files.length===1)throw err;if(!(err instanceof TypeError)){failed.push([pick.name,err.message]);continue;}
     maybe=pick.name;stop='down';left=files.slice(i+1).map(y=>y.name);break;}}  // no answer: it may have been stored before the drop
   if(files.length===1)toast('Uploaded '+done[0]+'. Select it above, then save.');
   else{const missed=failed.length+left.length+(maybe?1:0),count=done.length?'Uploaded '+done.length+(missed?' of '+files.length:'')+' files':'No files were uploaded';
    const out=batch.report;out.className=missed?'notice upload-report':'fine upload-report';out.replaceChildren(el('p',count+(done.length?': '+done.join(', ')+'. Select one above, then save.':'.')));
    if(failed.length){const ul=el('ul');for(const [n,why] of failed)ul.append(el('li',n+': '+(why||'the upload failed.')));out.append(el('p','Not uploaded:'),ul);}
    if(maybe)out.append(el('p','The connection dropped while '+maybe+' was uploading, so it may have been uploaded: check the menus above before uploading it again.'));
    if(left.length)out.append(el('p',(stop==='sign'?'Not tried, so sign in again and upload them: ':'Not tried, because AcePressure didn’t answer. Check that it is running and this device is online, then upload them again: ')+left.join(', ')));
    // You left Design studio meanwhile, or were signed out (signing in again redraws it): shown when it's drawn next.
    out.hidden=false;if(!out.isConnected||stop==='sign')artReport=out;
    toast(done.length?count+'.'+(missed?' '+missed+' not uploaded: see the list under Upload your artwork.':''):'No files were uploaded: see the list under Upload your artwork.');}
   batch.input.value='';}
  catch(err){toast(err.message);}
  finally{removeEventListener('beforeunload',hold);artBatch=null;batch.go.disabled=batch.input.disabled=false;batch.go.textContent='Upload image';}};
 upload.append(uf);root.append(upload);
}
// Keep the private preview draft in this tab only; never write it to donation settings.
const voicePreviewDraft={text:'GG bhai, kya clutch tha! Thanks for the stream.',voice:null};
async function voiceStudio(root){
 const p=panel('Find and test real voices'),f=el('form'),defaultEngine=['edge','piper','azure','windows'].includes(state.settings.tts_engine)?state.settings.tts_engine:'edge',engine=field(f,'Voice source','source','select',defaultEngine,[{value:'edge',label:'Edge TTS · FREE Microsoft Neural voices (no key, no account)'},{value:'piper',label:'Piper · FREE local offline voices (from data/piper-voices/)'},{value:'windows',label:'Windows SAPI · local, no Hinglish'},{value:'azure',label:'Azure Speech · requires your account/key'}]);
 p.append(note('A voice in this list isn’t necessarily installed. Detect voices, tick the ones that work, save, then press Listen to sample. Your sample stays here until you reload this tab. For Hindi voices, Roman Hindi is converted to Devanagari when the sentence is Hindi; “The voice reads” shows exactly what will be spoken. Try English and Hinglish before you choose. Azure sends the message to Microsoft and may cost money.'));
 const results=el('div'),status=el('p','','fine');
 f.append(button('Detect available voices',async()=>{status.textContent='Checking voices…';try{const d=await A('tts/catalog?engine='+engine.value);results.replaceChildren();for(const v of d.voices)field(results,v.label,v.id,'checkbox',state.settings.voices.includes(v.id));status.textContent=d.voices.length+' voices found. Select the ones viewers may use.';}catch(e){status.textContent=e.message;}}));
 f.append(button('Use selected voices',async()=>{try{const selected=Array.from(results.querySelectorAll('input:checked')).map(x=>x.name);await A('tts/configure',{engine:engine.value,voices:selected});await refresh(false);toast('Voice choices saved. Reload this panel to preview your selection.');tab='TTS';await draw();}catch(e){status.textContent=e.message;}},'primary'));f.append(status,results);p.append(f);
 const sample=field(p,'Try English or Hinglish','sample','text',voicePreviewDraft.text);sample.maxLength=Math.min(500,Math.max(20,Number(state.settings.tts_limit)||180));sample.addEventListener('input',()=>{voicePreviewDraft.text=sample.value;});
 const select=field(p,'Saved voice','preview_voice','select',state.settings.voices.includes(voicePreviewDraft.voice)?voicePreviewDraft.voice:state.settings.voices[0],state.settings.voices.map(v=>({value:v,label:state.settings.voice_labels?.[v]||v})));select.addEventListener('change',()=>{voicePreviewDraft.voice=select.value;});
 // What the voice will say for the sample (pronunciations, emoji skipped, Hinglish converted), without making audio.
 const reads=el('p','','fine voice-reads');p.append(reads);let readsTimer=0;
 const showReads=()=>{clearTimeout(readsTimer);readsTimer=setTimeout(async()=>{const text=sample.value,voice=select.value;if(!text.trim()||!voice){reads.textContent='';return;}try{const d=await A('tts/spoken',{text,voice});if(text!==sample.value||voice!==select.value)return;reads.textContent=d.reads?'The voice reads: '+d.reads+(d.hindi?'  ·  A Hindi voice reads: '+d.hindi:'')+(d.shortened?'  ·  Cut short: “Read whole messages” is off':''):'Nothing to read aloud: the voice skips emoji and the words you set to be skipped.';}catch(_){reads.textContent='';}},300);};
 sample.addEventListener('input',showReads);select.addEventListener('change',showReads);showReads();const player=el('audio');player.preload='none';let blob,heard='';
 const listen=button('Listen to sample',async()=>{try{player.pause();const want=[select.value,sample.value,JSON.stringify([state.settings.pronunciations,state.settings.tts_cleanup,state.settings.hide_links,state.settings.banned_words,state.settings.tts_read_full,state.settings.tts_short_limit])].join('\n');player.volume=volumeLevel(state.settings.tts_volume);if(blob&&want===heard){player.currentTime=0;await player.play();return;}if(blob)URL.revokeObjectURL(blob);blob=null;const r=await fetch('/api/admin/tts/preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({voice:select.value,text:sample.value})});if(!r.ok)throw Error((await readJSON(r)).error);blob=URL.createObjectURL(await r.blob());heard=want;player.src=blob;await player.play();}catch(e){status.textContent=e.message;}});
 const health=el('p','','fine'),check=async()=>{try{health.textContent=ttsHealthText(await A('tts/health'),state.settings.tts_engine);}catch(e){health.textContent=e.message;}},checkHealth=button('Check last OBS TTS result',check);// 1.6.4: the same words as a test alert in OBS, to hear the cut on stream. Tests never change totals.
  const toOBS=button('Send to OBS as a test alert',()=>action(async()=>{if(!sample.value.trim())throw Error('Type a sample message first.');testToast((await A('alerts',{action:'test',message:sample.value})).overlays||{},'Test alert sent. ');}));
  const actions=el('div',undefined,'row voice-actions');actions.append(listen,toOBS,checkHealth);p.append(actions,player,health);root.append(p);check();
}
function ttsHealthText(d,engine){const last=d.last;if(!last)return 'No OBS TTS result reported yet. Trigger a test alert on the horizontal source.';
 if(last.code==='played'&&d.backup_used)return 'The backup voice read the last OBS alert ('+date(last.at)+')'+(d.provider_error?' because the main voice failed: '+d.provider_error.message:'.');  // 1.6.4
 // These engines need no browser voice: voice_missing comes from an OBS source still on the pre-1.6.0 overlay page, or from before the engine changed.
 if(last.code==='voice_missing'&&['edge','piper','windows','azure'].includes(engine))return 'The last OBS report ('+date(last.at)+') found no voice. If you’ve already chosen an Edge, Piper, Windows or Azure voice, OBS is probably still running the old overlay page: in OBS, right-click the alert source → Properties → “Refresh cache of current page” (or restart OBS), then send a test alert.';
 return {played:'Last OBS readout played ('+date(last.at)+').',voice_missing:'OBS doesn’t have that browser voice, so nothing was read. Choose an Edge, Piper, Windows or Azure voice above and save.',provider_failed:d.provider_error?'AcePressure couldn’t make the audio: '+d.provider_error.message:'AcePressure couldn’t make the audio. Check the engine is installed (Install_Edge_TTS.bat / Install_Piper.bat) and, for Edge, that this PC is online.',playback_failed:'OBS received the audio but couldn’t play it. In OBS, check the source isn’t muted and that Control audio via OBS is routed to your stream track.',unavailable:'This OBS browser has no speech engine. Use an Edge, Piper, Windows or Azure voice.'}[last.code]||last.code+' · '+date(last.at);}
