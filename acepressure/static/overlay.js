'use strict';
const query=new URLSearchParams(location.search),kind=document.body.dataset.kind;
const key=query.get('key')||sessionStorage.getItem('ace-overlay-key')||'';
if(key)sessionStorage.setItem('ace-overlay-key',key);
query.delete('key');history.replaceState(null,'',location.pathname+(query.size?'?'+query:'')+location.hash);
const channel=query.get('layout')==='vertical'?'vertical':'horizontal',audioOn=query.get('audio')==='1'||(query.get('audio')===null&&channel==='horizontal'),owner=crypto.randomUUID(),stage=$('#stage');
// OBS gets the alerts: a normal browser tab with the same link waits while OBS is connected, unless it has &claim=always.
const isOBS=typeof window.obsstudio==='object'||/\bOBS\/\d/.test(navigator.userAgent),forced=query.get('claim')==='always',clientType=isOBS?'obs':forced?'forced':'browser';
const O=(path,body)=>api('/api/overlay/'+path,body,{'X-Overlay-Token':key}).then(d=>{if(path==='claim')standby(d.standby);return d;});
// AcePressure makes the audio for these engines itself, so OBS needs no installed voice.
const SERVER_TTS=['windows','azure','edge','piper'];
let busy=false,currentAudio=null,skipVersion=null,muted=false,ttsCancel=null,speechGeneration=0,failures=0;
// 1.6.4: soundCancel stops the alert sound and ttsFetch the voice still being made; alertNow is the alert on screen, for Skip alert.
let soundCancel=null,ttsFetch=null,alertNow=null,skipping=false;
function reportSpeech(code){O('tts-status',{code}).catch(()=>{});}
function stopSpeech(){speechGeneration++;if('speechSynthesis'in window)speechSynthesis.cancel();if(currentAudio){currentAudio.pause();currentAudio=null;}if(ttsCancel){ttsCancel(false);ttsCancel=null;}if(ttsFetch){ttsFetch.abort();ttsFetch=null;}}
function stopSound(){if(soundCancel){soundCancel();soundCancel=null;}}
/* 1.6.4: when OBS goes live, a stream session starts (Admin → OBS can switch that off). The page asks OBS once it loads
   ("Read access to OBS status information", the default permission) and then listens; a report that didn't reach
   AcePressure (no answer, a server error or too many reports) is sent again 10 s later. Stopping only tells the dashboard: the overlay key never ends a session. */
let liveReport=null,liveTried=0;
function tellLive(streaming,reason){if(kind!=='alert')return;liveReport={streaming,reason};liveTried=Date.now();O('live',liveReport).then(()=>{liveReport=null;}).catch(e=>{if(e&&e.status>=400&&e.status<500&&e.status!==429)liveReport=null;});}  // an older server (404) or a wrong key: don't retry
if(kind==='alert'&&typeof window.obsstudio==='object'&&window.obsstudio){
    window.addEventListener('obsStreamingStarted',()=>tellLive(true,'event'));
    window.addEventListener('obsStreamingStopped',()=>tellLive(false,'event'));
    try{if(typeof window.obsstudio.getStatus==='function')window.obsstudio.getStatus(st=>{if(st&&st.streaming)tellLive(true,'load');});}catch(_){}
}
// A single failed poll never shows on stream: the error waits for 3 in a row, except a rejected key.
function fail(e){if(++failures<3&&!String(e.message).includes('Overlay key rejected'))return;$('#error').textContent='AcePressure overlay: '+e.message;$('#error').hidden=false;}
function clearError(){failures=0;$('#error').hidden=true;}
function standby(on){let n=$('.overlay-standby');if(!n&&on)n=document.body.appendChild(el('p','Preview only: OBS is taking alerts for this layout. Close this tab, or add &claim=always to use it.','overlay-standby'));if(n)n.hidden=!on;}
async function update(){try{const s=await O('state?period='+encodeURIComponent(query.get('period')||'week'));clearError();if((skipVersion!==null&&skipVersion!==s.skip_version)||s.muted)stopSpeech();skipVersion=s.skip_version;muted=s.muted;if(alertNow&&Array.isArray(s.dismissed)&&s.dismissed.includes(alertNow.id))alertNow.stop();if(liveReport&&Date.now()-liveTried>10000)tellLive(liveReport.streaming,liveReport.reason);const v=applyVisuals(s.visuals);if(kind==='alert')return;if(kind==='goal'&&stage.dataset.snapshot===JSON.stringify([s.goals,v]))return;stage.dataset.snapshot=JSON.stringify([s.goals,v]);stage.replaceChildren();if(kind==='goal'){let gs=s.goals;if(query.get('goal'))gs=gs.filter(g=>g.id===query.get('goal'));for(const g of gs){stage.append(goalCard(g,v));}}else{const large=query.get('design')==='large',w=el('section',undefined,'widget '+(large?'large':''));const period=query.get('period')||'week';w.append(el('h2',kind==='top3'?'Top supporters · '+({stream:'This stream',today:'Today',week:'This week',month:'This month',year:'This year',lifetime:'All time'}[period]||period):'Recent support'));const items=kind==='top3'?s.top:s.recent;if(!items.length)w.append(el('p','Your support goes a long way.','empty'));items.forEach((p,i)=>{const row=el('div',undefined,'board-row');row.append(el('span',String(i+1).padStart(2,'0'),'rank'),el('strong',p.name),el('b',INR(p.total??p.display_paise)));w.append(row);});stage.append(w);}}catch(e){fail(e);}}
const pause=ms=>new Promise(r=>setTimeout(r,ms));
// Without autoplay permission (a browser tab nobody clicked) resume() never settles: give up after 1 s so the alert still finishes.
async function sound(name,volume=1){if(!audioOn||!name||name==='none'||skipping)return true;if(name==='chime'||name==='pulse'){const Context=window.AudioContext||window.webkitAudioContext;if(!Context)return false;const c=new Context();try{await Promise.race([c.resume(),pause(1000)]);if(c.state!=='running')return false;const gain=c.createGain();gain.connect(c.destination);soundCancel=()=>{try{gain.disconnect();}catch(_){}};gain.gain.setValueAtTime(.12*volume,c.currentTime);gain.gain.exponentialRampToValueAtTime(.001,c.currentTime+.6);const o=c.createOscillator();o.type='sine';o.frequency.setValueAtTime(name==='chime'?660:220,c.currentTime);o.frequency.setValueAtTime(name==='chime'?880:330,c.currentTime+.15);o.connect(gain);o.start();o.stop(c.currentTime+.6);await pause(650);soundCancel=null;return true;}catch(_){soundCancel=null;return false;}finally{await c.close();}}return playAudio('/media/'+encodeURIComponent(name),31000,false,volume);}
// A sound file gets 10 s to start, then `timeout` from its first 'playing'. Once it has played it counts as played, so the default never follows it.
async function playAudio(url,timeout=40000,isSpeech=true,volume=1){return new Promise(resolve=>{const a=new Audio(url);try{a.volume=volume;}catch(_){}if(isSpeech)currentAudio=a;let settled=false,started=false,timer=setTimeout(()=>finish(false),isSpeech?timeout:10000);function finish(ok){if(settled)return;settled=true;clearTimeout(timer);a.pause();if(currentAudio===a)currentAudio=null;if(isSpeech)ttsCancel=null;else soundCancel=null;resolve(ok);}if(!isSpeech)soundCancel=()=>finish(false);if(isSpeech)ttsCancel=finish;else a.addEventListener('playing',()=>{started=true;clearTimeout(timer);timer=setTimeout(()=>finish(true),timeout);},{once:true});a.onended=()=>finish(true);a.onerror=()=>finish(started);a.play().catch(()=>finish(false));});}
// 1.6.2 servers send the copy the voice reads (p.speech: pronunciations applied, emoji dropped); older servers send only the message.
async function speak(p,engine,volume=1){const text=typeof p.speech==='string'?p.speech:p.message;if(!audioOn||!p.tts||muted||!text||engine==='off')return false;
if(SERVER_TTS.includes(engine)){const generation=speechGeneration,ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),20000);ttsFetch=ctl;const r=await fetch('/api/overlay/tts/'+p.event_id,{headers:{'X-Overlay-Token':key},signal:ctl.signal}).catch(()=>null);const blob=r&&r.ok?await r.blob().catch(()=>null):null;clearTimeout(timer);if(ttsFetch===ctl)ttsFetch=null;if(generation!==speechGeneration||muted)return false;if(!blob){reportSpeech('provider_failed');return false;}const url=URL.createObjectURL(blob);try{const ok=await playAudio(url,50000,true,volume);if(!ok&&generation===speechGeneration)reportSpeech('playback_failed');return ok;}finally{URL.revokeObjectURL(url);}}
if(!('speechSynthesis'in window)){reportSpeech('unavailable');return false;}
if(!speechSynthesis.getVoices().length){const generation=speechGeneration;await pause(700);if(generation!==speechGeneration||muted)return false;}
const available=speechSynthesis.getVoices();if(!available.some(v=>v.name===p.voice||v.lang.toLowerCase()===p.voice.toLowerCase())){reportSpeech('voice_missing');return false;}
return new Promise(resolve=>{const voices=speechSynthesis.getVoices();
/* Hinglish-aware voice pick: if message contains Hindi tokens and chosen voice is English-only,
   switch to any available Hindi voice so Hindi words aren't butchered. */
const voice=pickVoiceForText(text,p.voice,voices,p.hinglish);
/* A Hindi-capable voice reads Roman Hindi as Devanagari: given raw "bhai" it says "bai". 1.6.2 servers send that copy
   (p.speech_hi), made by the same rules as the server voices; for older servers the overlay converts it itself. */
const hindiVoice=!!voice&&typeof voice==='object'&&voiceHandlesHindi(voice);
const textToSpeak=hindiVoice?(typeof p.speech_hi==='string'?p.speech_hi:maybeTransliterate(text,voice)):text;
const u=new SpeechSynthesisUtterance(textToSpeak);u.volume=volume;
if(voice&&typeof voice==='object')u.voice=voice;u.lang=voice&&voice.lang?voice.lang:(typeof voice==='string'?voice:p.voice);
let done=false;const timer=setTimeout(()=>{speechSynthesis.cancel();finish(false);},50000);function finish(ok){if(done)return;done=true;clearTimeout(timer);ttsCancel=null;resolve(ok);}ttsCancel=finish;u.onend=()=>finish(true);u.onerror=e=>{if(!['interrupted','canceled'].includes(e&&e.error))reportSpeech('playback_failed');finish(false);};speechSynthesis.speak(u);});}
/* Which sound an alert plays. 1.6.0 servers resolve the pick and the default into the payload:
   1. the viewer's pick (p.soundboard_clip)
   2. a fixed Design Studio sound, which only servers older than 1.6.0 send (visuals.alert_sound)
   3. p.sound: the streamer's default, or the sound saved with a tip made before 1.6.0 */
function resolveAlertSound(visuals,p){
    if(p&&p.soundboard_clip)return p.soundboard_clip;
    if(visuals&&visuals.alert_sound&&visuals.alert_sound!=='viewer')return visuals.alert_sound;
    return (p&&p.sound)||'none';
}
async function runQueue(){if(busy||kind!=='alert'||(!isOBS&&!forced&&document.visibilityState==='hidden'))return;busy=true;skipping=false;let p,shown=false,spoken=false;try{const result=await O('claim',{channel,owner,client:clientType});p=result.alert;if(!p)return;await update();const gen=speechGeneration;clearError();stage.className='alert-stage '+channel;const visuals=applyVisuals(result.visuals);const card=alertCard(p,visuals);stage.replaceChildren(card);shown=true;const start=Date.now();
    // Skip alert (1.6.4): the next state poll lists this alert as dismissed. Sound, voice and video stop and the card leaves now.
    let skipped=false,wake;const skip=new Promise(r=>{wake=r;});
    alertNow={id:p.event_id,stop(){if(skipped)return;skipped=skipping=true;stopSpeech();stopSound();for(const v of card.querySelectorAll('video')){v.muted=true;v.pause();}wake();}};
    // The alert video's own sound plays only when the server says so for this alert, never under a viewer's pick.
    const videoEl=card.querySelector('video.alert-art');
    const wantVideo=!!(videoEl&&visuals.alert_video_has_audio&&audioOn&&!p.soundboard_clip);
    let useVideoAudio=false;
    if(wantVideo){
        videoEl.muted=false;
        try{await videoEl.play();useVideoAudio=!videoEl.paused&&!videoEl.muted;}catch(_){videoEl.muted=true;videoEl.play().catch(()=>{});}
    }
    // 1.6.2 servers send each sound file's library volume in % (p.volumes) and the voice volume; without them everything plays as uploaded.
    const vol=name=>volumeLevel((p.volumes||{})[name]);
    if(!useVideoAudio){const first=wantVideo?'chime':resolveAlertSound(visuals,p);await sound(first,vol(first)).then(ok=>{if(!ok&&p.soundboard_clip&&p.sound!==p.soundboard_clip)return sound(p.sound,vol(p.sound));});}
    // Skip TTS pressed while the sound played (it bumps speechGeneration) cancels the readout before it starts. A Skip pressed before the
    // claim was already absorbed by the update() right after it, so it can't cancel this alert's readout.
    try{spoken=gen===speechGeneration&&await speak(p,result.tts_engine,volumeLevel(result.tts_volume));if(spoken)reportSpeech('played');}catch(_){reportSpeech('playback_failed');}await Promise.race([pause(Math.max(0,p.seconds*1000-(Date.now()-start))),skip]);card.classList.add('exit');await pause(450);stage.replaceChildren();alertNow=null;await O('ack',{event_id:p.event_id,channel,owner,tts_played:spoken,client:clientType,skipped});}catch(e){fail(e);alertNow=null;if(shown&&p){stage.replaceChildren();try{await O('ack',{event_id:p.event_id,channel,owner,tts_played:spoken,client:clientType});}catch(_){} }}finally{busy=false;}}
update();setInterval(update,1500);runQueue();setInterval(runQueue,1000);window.addEventListener('beforeunload',stopSpeech);
