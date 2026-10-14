'use strict';
let current=null,poll=null,config,checking=false,lastCheck=0,failures=0;
const POLL_MS=20000;
// 1.6.4: after the payment window closes the page keeps checking, once a minute for 2 hours, so a payment the creator
// approves later still shows up here.
const LATE_MS=60000,LATE_FOR=7200000;
$('#pay-button').disabled=true;  // until the server says viewers can tip
// Storage can be missing or blocked (private windows, strict cookie settings): the page must work without it.
const safeStore={get(k,area='localStorage'){try{return window[area].getItem(k);}catch(_){return null;}},set(k,v,area='localStorage'){try{window[area].setItem(k,v);}catch(_){}},remove(k,area='localStorage'){try{window[area].removeItem(k);}catch(_){}}};
// availability: 'open', 'demo', 'paused' or 'setup'. Older servers send only ready and accepting_tips.
function availability(){return config.availability||(!config.accepting_tips?'paused':config.demo?'demo':config.ready?'open':'setup');}
function setPayEnabled(){$('#pay-button').disabled=!config||!['open','demo'].includes(availability());}
function showAvailability(){const a=availability(),n=$('#availability');n.hidden=a==='open';n.textContent=a==='demo'?'DEMO — no money is accepted. Payments are simulated in the private dashboard.':a==='paused'?config.creator+' isn’t taking new tips right now. Please check back soon.':'Tips open soon — '+config.creator+' is finishing payment setup.';setPayEnabled();}
// Only the notice and the pay button change: the form and any payment in progress are left alone.
async function refreshConfig(){try{const d=await api('/api/public/config');configAt=Date.now();for(const k of ['availability','ready','accepting_tips','tts_read_full','tts_short_limit','tts_full_from'])config[k]=d[k];showAvailability();voiceNote();}catch(_){}}
function recheckConfig(){if(config&&!document.hidden&&['paused','setup'].includes(availability()))refreshConfig();}
let configAt=0;  // a viewer coming back to the tab gets the creator's latest settings, at most every 30 s (1.6.4)
function returnCheck(){if(config&&Date.now()-configAt>30000)refreshConfig();else recheckConfig();}
// How much of the message the voice reads for the amount chosen: with “Read whole messages” off, only the start, unless
// the tip reaches the creator's “read the whole message from” amount (1.6.4).
function voiceNote(){let n=$('#tts-short-note');if(config.tts_read_full===false){if(!n){n=document.createElement('p');n.className='fine';n.id='tts-short-note';$('#tts-min').closest('label').after(n);}const from=+config.tts_full_from||0,whole=from>0&&(+$('#amount').value||0)>=from;n.textContent=whole?'The voice reads your whole message (tips from '+INR(from*100)+').':'The voice reads the first '+config.tts_short_limit+' characters of your message'+(from>0?' · all of it for tips from '+INR(from*100):'')+'.';}else if(n)n.remove();}
setInterval(recheckConfig,60000);
function scheduleCheck(){clearTimeout(poll);if(!current||document.hidden||current.final)return;if(!current.closed&&Date.now()<current.expires*1000)poll=setTimeout(check,Math.min(120000,POLL_MS*2**failures));else if(Date.now()<current.expires*1000+LATE_FOR)poll=setTimeout(check,Math.min(300000,LATE_MS*2**failures));}
function manualCheck(){if(Date.now()-lastCheck>=5000)check();else scheduleCheck();}
document.addEventListener("visibilitychange",()=>{if(document.hidden)clearTimeout(poll);else{if(current)manualCheck();returnCheck();}});
async function init(){
    // Fill skeleton rows into Top supporters immediately so the slot never looks blank.
    const topHost=$('#top');topHost.replaceChildren(...Array.from({length:3},()=>{const r=el('div',undefined,'skeleton-row');r.append(el('div',undefined,'skeleton-bar rank'),el('div',undefined,'skeleton-bar name'),el('div',undefined,'skeleton-bar amount'));return r;}));
    try{config=await api('/api/public/config');configAt=Date.now();}catch(e){const n=$('#availability');n.hidden=false;n.replaceChildren(document.createTextNode('Couldn’t load the tip form. Check your connection. '),button('Retry',init,'subtle'));return;}
    try{$('#welcome').textContent=config.welcome;$('#creator-name').textContent=config.creator;$('#minimum-note').textContent='Minimum tip: '+INR(config.minimum*100);if(config.avatar){$('#avatar').src=config.avatar;$('#avatar').hidden=false;$('#creator-mark').hidden=true;}
$('#amount').min=config.minimum;$('#amount').max=config.maximum;$('#amount').value=Math.min(config.maximum,Math.max(100,config.minimum));$('textarea').maxLength=config.tts_limit;$('#tts-min').textContent='from '+INR(config.tts_minimum*100);voiceNote();options($('#voice'),config.voices.map(v=>({value:v,label:config.voice_labels?.[v]||({'en-IN':'English · India','hi-IN':'Hindi · India'})[v]||v})));buildVoices();buildSoundboard();const message=$('textarea');const count=()=>$('#message-count').textContent=message.value.length+' / '+config.tts_limit;message.addEventListener('input',count);count();
$$('[data-amount]').forEach(b=>{b.disabled=+b.dataset.amount<config.minimum||+b.dataset.amount>config.maximum;b.classList.toggle('selected',+b.dataset.amount===+$('#amount').value);b.onclick=()=>{$('#amount').value=b.dataset.amount;$$('[data-amount]').forEach(x=>x.classList.toggle('selected',x===b));$('#amount').dispatchEvent(new Event('input'));};});
showAvailability();
// Tier badge: lights up with the current amount, respects admin-defined tiers from /api/public/config.
const tierBadge=el('div',undefined,'tier-badge');tierBadge.id='tier-badge';
tierBadge.append(el('span','✦','tier-icon'),el('span','Supporter','tier-label'));
$('#minimum-note').after(tierBadge);
function renderTierBadge(){
    const rupees=Math.floor(+$('#amount').value||0);const tiers=(config.tiers||[1,50,200,500]).slice().sort((a,b)=>a-b);
    let level=0;for(const t of tiers)if(rupees>=t)level++;
    const names=['Starter','Supporter','Big fan','Legend','Icon'];const icons=['✦','★','⚡','👑','🏆'];const idx=Math.max(0,Math.min(level,names.length-1));
    tierBadge.className='tier-badge tier-'+Math.min(level,3);
    tierBadge.children[0].textContent=icons[idx];tierBadge.children[1].textContent=names[idx]+' · ₹'+rupees;
}
$('#amount').addEventListener('input',()=>{$$('[data-amount]').forEach(b=>b.classList.toggle('selected',+b.dataset.amount===+$('#amount').value));renderTierBadge();voiceNote();});
$$('[data-amount]').forEach(b=>b.addEventListener('click',()=>{renderTierBadge();voiceNote();}));renderTierBadge();
// 1.6.4: a payment in progress comes back first, so a slow Top supporters list can't hold it up.
const saved=safeStore.get('ace-tip','sessionStorage');if(saved){current=JSON.parse(saved);if(current.closed){showPayment();closePayment(current.review,current.final);}else showPayment();check();}
const top=await api('/api/public/top').catch(()=>({supporters:[]}));if(top.supporters.length){$('#top').replaceChildren(...top.supporters.map((p,i)=>{const row=el('div',undefined,'supporter-row');row.append(el('span','0'+(i+1),'rank'),el('strong',p.name),el('b',INR(p.total)));return row;}));}else{$('#top').replaceChildren(note('Be the first to support the stream.','empty'));}
}catch(e){$('#form-error').textContent=e.message;}}
// A pick the amount doesn't cover is never dropped silently: the viewer raises the tip or picks again (the server checks too).
$('#tip-form').onsubmit=async e=>{e.preventDefault();$('#form-error').textContent='';const short=unaffordablePick();if(short){refusePick(short);return;}$('#pay-button').disabled=true;let sbId='';try{const fd=new FormData(e.target);const payload={amount:fd.get('amount'),name:fd.get('name'),email:fd.get('email'),remember:fd.get('remember')==='on',message:fd.get('message'),tts:fd.get('tts')==='on',voice:fd.get('voice')};sbId=fd.get('soundboard_id');if(sbId)payload.soundboard_id=sbId;current=await api('/api/public/tips',payload);showPayment();scheduleCheck();safeStore.set('ace-remember',fd.get('remember')==='on'?'yes':'no');safeStore.set('ace-tip',JSON.stringify(current),'sessionStorage');}catch(err){$('#form-error').textContent=err.message;if(err.status===503)refreshConfig();if(sbId)await buildSoundboard();}finally{setPayEnabled();}};
// The refusal sits just above Pay: Enter in the amount box (or a phone's Go key) scrolls it into view instead of leaving the screen unchanged.
function refusePick(it){const n=$('#form-error'),seen=x=>{const r=x.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;};
    pickRefusal=n.textContent='“'+it.name+'” needs a tip of at least '+INR(it.min_paise)+'. Raise your tip or choose another sound.';
    if(!seen(n))n.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});else if(seen($('#amount')))$('#amount').focus({preventScroll:true});  // focus opens a phone keyboard, which would scroll the message away
    setPayEnabled();}
function reset(){clearTimeout(poll);failures=0;current=null;safeStore.remove('ace-tip','sessionStorage');$('#payment').hidden=true;$('#tip-form-wrap').hidden=false;revealCard();}
// After the form/payment swap the page shrinks; bring the card's top (amount, QR) back into view.
function revealCard(){const card=$('.tip-card');if(card&&card.getBoundingClientRect().top<80)card.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
function renderCelebration(box,d){
    box.replaceChildren();
    const wrap=el('div',undefined,'celebration');
    const ring=el('div','🎉','celebrate-ring');
    const eyebrow=el('div','PAYMENT CONFIRMED','eyebrow');
    const heading=el('h2','Thank you, '+d.name+'!');
    const sub=note(d.alert_queued?'Your '+INR(d.display_paise)+' support is on its way to the stream. Watch for your alert!':'Thank you! '+config.creator+' has received your '+INR(d.display_paise)+' support.','');
    const receipt=el('div',undefined,'receipt-card');
    receipt.append(document.createTextNode('TIP ID'),el('b',d.id));
    const share=el('div',undefined,'share-row');
    const copyBtn=button('Copy receipt',()=>{navigator.clipboard?.writeText('AcePressure tip '+d.id+' · '+INR(d.display_paise)).then(()=>{copyBtn.textContent='Copied ✓';setTimeout(()=>copyBtn.textContent='Copy receipt',2000);}).catch(()=>{copyBtn.textContent='Copy failed';});},'subtle');
    const again=button('Send another tip',reset,'primary');
    share.append(copyBtn,again);
    wrap.append(ring,eyebrow,heading,sub,receipt,share);
    box.append(wrap);
    revealCard();
}
function showPayment(){$('#tip-form-wrap').hidden=true;const box=$('#payment');box.hidden=false;delete box.dataset.closed;const heading=el('h2','Pay exactly ','pay-heading');heading.append(el('span',INR(current.requested_paise),'pay-amount'));box.replaceChildren(el('div','ONE LAST STEP','eyebrow'),heading,note('Your support appears as '+INR(current.display_paise)+'. The extra paise identifies this payment. Do not round the amount.'));
if(current.upi_uri){
 // 1.6.8: the app buttons come first and stay visible; the QR and copy controls are the fallback.
 const exact=(current.requested_paise/100).toFixed(2),apps=el('div',undefined,'payment-apps');apps.setAttribute('aria-label','Pay with a UPI app');let lastLaunch=0;
 const help=note('Tapping an app also copies '+INR(current.requested_paise)+'. If the app opens without the amount, paste it there.','fine app-help');help.id='app-help';help.setAttribute('role','status');
 for(const app of current.upi_apps||[]){
  const link=el('a',app.name,'pay-app pay-app-'+app.app);link.href=app.href;
  link.addEventListener('click',e=>{if(!current||Date.now()>=current.expires*1000){e.preventDefault();closePayment();return;}if(Date.now()-lastLaunch<4000){e.preventDefault();help.textContent='Wait a moment before another attempt. If the app did not open, use the QR or copy controls below.';return;}lastLaunch=Date.now();navigator.clipboard?.writeText(exact).catch(()=>{});help.textContent=INR(current.requested_paise)+' copied. If '+app.name+' opens without the amount, paste it there. Coming back here does not confirm payment.';});apps.append(link);
 }
 const qr=el('img');qr.className='qr';qr.alt='UPI QR with the exact amount';qr.src='/api/public/tips/'+current.id+'/qr?token='+encodeURIComponent(current.token);
 const save=el('a','Save payment QR','primary');save.href=qr.src;save.download='AcePressure-payment.png';
 const recipient=el('input');recipient.readOnly=true;recipient.value=current.upi_id||'';recipient.setAttribute('aria-label','Receiving UPI ID');
 const copyId=button('Copy UPI ID',()=>copyPayment(current.upi_id,box,copyId)),copyAmount=button('Copy exact amount',()=>copyPayment(exact,box,copyAmount));
 box.append(el('p','Pay with','pay-with'),apps,help,el('p','or scan the QR','pay-divider'),el('p','Payee: '+(current.payee_name||''),'payee'),qr,save,note('On this phone: save the QR, open your UPI app, and use its Scan → Photos/Gallery option if available. Or scan this screen using another phone. The QR includes the exact amount; check it before authorizing.','fine'));
 if(current.requested_paise>200000)box.append(note('Some apps limit QR payments imported from photos to ₹2,000. If rejected, use a camera scan from another screen or copy the UPI ID and exact amount. Do not split this payment.','fine'));
 box.append(recipient,copyId,copyAmount,note('If your app rejects a payment, check its payment history before trying again. Never pay twice for the same tip.','fine'));
}else box.append(note('DEMO PAYMENT — open Admin → Pending payments to simulate verification.'));
box.append(el('p','Waiting for payment confirmation. Some payments need creator review; do not pay twice.','pending'),el('p','','fine'),button('Check payment status',manualCheck,'subtle'),button('Back to form',reset,'subtle'));$('.fine',box).dataset.keep='true';const timer=el('p','','countdown');timer.setAttribute('aria-live','off');box.append(timer);revealCard();}
// 1.6.4: the window closing is calm. The page keeps checking (LATE_FOR) and says so; review: a payment for this tip was seen
// and waits for the creator's approval. final: the creator closed the tip, so checking stops.
function closePayment(review=false,final=false){
 const box=$('#payment');if(!current)return;const mode=final?'final':review?'review':'closed';if(box.dataset.closed===mode)return;
 current.closed=true;current.review=review;current.final=final;safeStore.set('ace-tip',JSON.stringify(current),'sessionStorage');box.dataset.closed=mode;
 const id=note('Tip ID: '+current.id+'. Mention it if you contact '+config.creator+' about this tip.','fine');
 if(final)box.replaceChildren(el('h2','This tip was closed'),el('p',config.creator+' closed this tip. If you paid, contact them with the tip ID below. Don’t pay again.','pending'),id,button('Back to tipping page',reset,'primary'));
 else if(review)box.replaceChildren(el('h2','Waiting for approval'),el('p','We’ve seen a payment for this tip. '+config.creator+' approves it by hand, usually within a few minutes, and this page updates by itself. Don’t pay again.','pending'),id,button('Check payment status',manualCheck,'subtle'),button('Back to tipping page',reset,'subtle'));
 else box.replaceChildren(el('h2','Payment window closed'),el('p','If you’ve paid, it can still be confirmed: leave this page open and it updates by itself. Don’t pay again.','pending'),id,button('Check payment status',manualCheck),button('Back to tipping page',reset,'primary'));
}
// The countdown is local: it makes no network requests.
setInterval(()=>{if(!current||current.closed)return;const left=Math.max(0,current.expires-Math.floor(Date.now()/1000));if(!left){closePayment(current.review);check();}const timer=$('.countdown');if(timer){timer.textContent='Expires in '+Math.floor(left/60)+':'+String(left%60).padStart(2,'0');timer.classList.toggle('urgent',left<=60);}},1000);
async function check(){
 if(!current||checking||document.hidden)return;
 clearTimeout(poll);checking=true;lastCheck=Date.now();const target=current;
 try{
  const d=await api('/api/public/tips/'+target.id,undefined,{'X-Tip-Token':target.token});
  if(current!==target)return;
  failures=0;
  const paid=['VERIFIED','MANUAL'].includes(d.status),box=$('#payment');
  if(paid){safeStore.remove('ace-tip','sessionStorage');current=null;renderCelebration(box,d);if(window.aceConfetti)window.aceConfetti(140);return;}
  if(!['PENDING','EXPIRED'].includes(d.status))closePayment(false,true);
  else if(d.status!=='PENDING'||Date.now()>=d.expires*1000||current.closed)closePayment(d.needs_review);
  else{current.review=!!d.needs_review;const message=$('.pending');if(message)message.textContent=d.needs_review?'We’ve seen a payment for this tip. '+config.creator+' approves it by hand, usually within a few minutes. This page updates by itself. Don’t pay again.':'Waiting for payment confirmation. This page checks every 20 seconds. Don’t pay twice.';}
 }catch(e){failures=Math.min(failures+1,3);const n=$('.pending');if(current===target&&n&&!current.closed)n.textContent='Connection interrupted. Retrying less often. You can check status manually.';}
 finally{checking=false;scheduleCheck();}
}
let previewAudio=null,previewContext=null;
function soundLabel(value){const raw=({chime:'Chime',pulse:'Pulse',none:'Silent'})[value]||config.sound_labels?.[value]||String(value);
 // "airhorn_myinstants" reads as a developer artifact next to "Thug Life"; already-cased names are left alone.
 return /[_]/.test(raw)||(/[a-z]/.test(raw)&&raw===raw.toLowerCase())?raw.replace(/[_-]+/g,' ').replace(/\s+/g,' ').trim().replace(/(^|\s)(\S)/g,(m,a,c)=>a+c.toUpperCase()):raw;}

/* Soundboard — streamer-curated gallery of alert clips, each with a per-sound minimum tip.
   Supports: category pills, instant search, tier-meter preview, locked state, favorites in
   localStorage, click-to-select, preview-play on each tile. Fully config-driven. */
const SOUNDBOARD_FAV_KEY='ace-sb-favorites';
let soundboardItems=[],soundboardFilter={cat:'All',search:''},soundboardAudio=null,soundboardWired=false,pickRefusal='';
function sbFavorites(){try{return new Set(JSON.parse(localStorage.getItem(SOUNDBOARD_FAV_KEY)||'[]'));}catch{return new Set();}}
function sbToggleFav(id){const favs=sbFavorites();if(favs.has(id))favs.delete(id);else favs.add(id);try{localStorage.setItem(SOUNDBOARD_FAV_KEY,JSON.stringify([...favs]));}catch{}return favs.has(id);}
function sbNote(t){$('#soundboard-note').textContent=t;}
// Safe to call again (a failed tip re-runs it): the listeners are wired once, and a pick that is no longer listed is dropped.
async function buildSoundboard(){
    const section=$('#soundboard-section');if(!section)return;
    try{const res=await api('/api/public/soundboard');soundboardItems=res.items||[];}
    catch{/* keep the list it had: a failed refresh says nothing about the pick (the first load starts empty) */}
    const picked=$('#soundboard_id').value;if(picked&&!soundboardItems.some(it=>it.id===picked)){$('#soundboard_id').value='';$('#soundboard-clear').hidden=true;}
    if(!soundboardItems.length){section.hidden=true;return;}
    section.hidden=false;
    // Category pills — "All" + "★ Favorites" + each distinct category, in insertion order.
    const cats=['All','★ Favorites'];for(const it of soundboardItems){if(!cats.includes(it.category))cats.push(it.category);}
    if(!cats.includes(soundboardFilter.cat))soundboardFilter.cat='All';
    const pillHost=$('#soundboard-categories');pillHost.replaceChildren();
    for(const cat of cats){
        const b=button(cat,()=>{soundboardFilter.cat=cat;for(const x of pillHost.children){x.classList.toggle('selected',x.textContent===cat);x.setAttribute('aria-selected',String(x.textContent===cat));}renderSoundboardGrid();},'pill');
        b.setAttribute('role','tab');b.setAttribute('aria-selected',String(cat===soundboardFilter.cat));
        b.classList.toggle('selected',cat===soundboardFilter.cat);pillHost.append(b);
    }
    if(!soundboardWired){soundboardWired=true;
        const search=$('#soundboard-search');search.oninput=()=>{soundboardFilter.search=search.value.trim().toLowerCase();renderSoundboardGrid();};
        // Typing 150 passes through 1 and 15, so the amount never clears a pick: Pay refuses one the tip doesn't cover (refusePick).
        $('#amount').addEventListener('input',()=>{renderSoundboardGrid();updateTierMeter();});
        $('#soundboard-clear').onclick=()=>{$('#soundboard_id').value='';$('#soundboard-clear').hidden=true;sbNote('');renderSoundboardGrid();};
    }
    keepPickAffordable();updateTierMeter();renderSoundboardGrid();
}
// The picked sound, when the amount no longer covers it.
function unaffordablePick(){const it=soundboardItems.find(x=>x.id===$('#soundboard_id').value);return it&&it.min_paise>Math.floor(+$('#amount').value||0)*100?it:null;}
// When the list is (re)loaded, e.g. after a tip failed because the streamer raised a price meanwhile, a pick the amount no longer
// covers is cleared with a note (the server's error is already showing), so the next Pay plays the default. True when it cleared one.
function keepPickAffordable(){
    const it=unaffordablePick();if(!it)return false;
    $('#soundboard_id').value='';$('#soundboard-clear').hidden=true;
    sbNote('“'+it.name+'” needs a tip of at least ₹'+it.min_paise/100+', so your pick was cleared. The streamer’s default will play.');
    return true;
}
function updateTierMeter(){
    const amt=Math.floor(+$('#amount').value||0)*100;
    const total=soundboardItems.length;const unlocked=soundboardItems.filter(x=>amt>=x.min_paise).length;
    $('#soundboard-counter').textContent=unlocked+' of '+total+' unlocked';
    const meter=$('#soundboard-tier');meter.replaceChildren();
    const bar=el('div',undefined,'tier-bar');const fill=el('div',undefined,'tier-fill');fill.style.width=Math.min(100,(unlocked/Math.max(total,1))*100)+'%';bar.append(fill);
    meter.append(bar,el('span','₹'+(amt/100).toFixed(0)+' tip unlocks '+unlocked+' / '+total+' sounds','tier-label'));
}
function renderSoundboardGrid(){
    // The rebuild drops the focused tile, so focus moves to the same tile in the new grid (keyboard users keep their place).
    const grid=$('#soundboard-grid'),focused=grid.contains(document.activeElement)?document.activeElement.dataset.id:undefined;grid.replaceChildren();
    // A Pay refusal goes once its cause does: an amount that covers the pick, another pick or the default.
    if(pickRefusal&&!unaffordablePick()){if($('#form-error').textContent===pickRefusal)$('#form-error').textContent='';pickRefusal='';}
    const amt=Math.floor(+$('#amount').value||0)*100;const favs=sbFavorites();const selected=$('#soundboard_id').value;const q=soundboardFilter.search;
    let list=soundboardItems.slice();
    if(soundboardFilter.cat==='★ Favorites')list=list.filter(it=>favs.has(it.id));
    else if(soundboardFilter.cat!=='All')list=list.filter(it=>it.category===soundboardFilter.cat);
    if(q)list=list.filter(it=>(it.name+' '+it.category).toLowerCase().includes(q));
    if(soundboardFilter.cat==='All'&&!q)grid.append(defaultTile(selected===''));
    if(!list.length){grid.append(note(soundboardFilter.cat==='★ Favorites'?'No favorites yet. Tap the ☆ on any tile to save it.':'No sounds match that search.','empty'));return;}
    for(const it of list){
        // The pick stays drawn as picked whatever the amount: Pay refuses one the tip doesn't cover, so it is never dropped silently.
        const locked=amt<it.min_paise&&selected!==it.id;const tile=el('button',undefined,'soundboard-tile'+(locked?' locked':'')+(selected===it.id?' selected':''));
        // Locked tiles stay focusable (aria-disabled, not disabled) so a click can say what unlocks them.
        tile.type='button';tile.dataset.id=it.id;tile.setAttribute('role','radio');tile.setAttribute('aria-checked',String(selected===it.id));if(locked)tile.setAttribute('aria-disabled','true');
        tile.title=locked?`Tip at least ₹${it.min_paise/100} to pick this sound`:it.name;
        const emoji=el('span',it.emoji||'🔊','tile-emoji');
        const name=el('span',it.name,'tile-name');
        const price=it.min_paise?'₹'+(it.min_paise/100):'Any tip',min=el('span',price,'tile-min');
        const star=el('span',favs.has(it.id)?'★':'☆','tile-fav');star.title=favs.has(it.id)?'Unfavorite':'Favorite';
        star.onclick=ev=>{ev.stopPropagation();sbToggleFav(it.id);renderSoundboardGrid();};
        const play=el('span','▶','tile-play');play.title='Preview';
        play.onclick=ev=>{ev.stopPropagation();playSoundboardPreview(it,tile);};
        tile.append(emoji,name,min,star,play);
        // On a phone the note can sit below the screen, so a tapped locked tile also says what unlocks it on its own price chip for a moment.
        tile.onclick=()=>{if(locked){sbNote('Tip at least ₹'+it.min_paise/100+' to pick “'+it.name+'”.');clearTimeout(tile.nudgeTimer);tile.classList.remove('nudge');void tile.offsetWidth;tile.classList.add('nudge');min.textContent='Tip '+price+'+';tile.nudgeTimer=setTimeout(()=>{tile.classList.remove('nudge');min.textContent=price;},2500);return;}
            $('#soundboard_id').value=selected===it.id?'':it.id;$('#soundboard-clear').hidden=!$('#soundboard_id').value;sbNote('');renderSoundboardGrid();};
        grid.append(tile);
    }
    if(focused!==undefined)[...grid.children].find(t=>t.dataset.id===focused)?.focus();
}
// The first tile means “no pick”: the tip plays the streamer’s default (config.sounds holds just that sound).
function defaultTile(active){
    const v=config.sounds?.[0],label=['chime','pulse'].includes(v)||config.sound_labels?.[v]?soundLabel(v):'';
    const tile=el('button',undefined,'soundboard-tile default-tile'+(active?' selected':''));
    tile.type='button';tile.dataset.id='';tile.setAttribute('role','radio');tile.setAttribute('aria-checked',String(active));
    tile.title='Plays the streamer’s default sound'+(label?' ('+label+')':'');
    tile.append(el('span','⭐','tile-emoji'),el('span','Streamer’s default','tile-name'),el('span',label||'Any tip','tile-min'));
    if(v&&v!=='none'){const play=el('span','▶','tile-play');play.title='Preview';play.onclick=ev=>{ev.stopPropagation();playPreview(v);};tile.append(play);}
    tile.onclick=()=>{$('#soundboard_id').value='';$('#soundboard-clear').hidden=true;sbNote('');renderSoundboardGrid();};
    return tile;
}
// Previews play at the streamer's volume (1.6.2, in %). Defined here, not in common.js, so a browser that kept the old common.js still works.
const previewVolume=v=>typeof v==='number'&&v>=0&&v<=100?v/100:1;
async function playSoundboardPreview(item,tile){
    try{if(soundboardAudio){soundboardAudio.pause();soundboardAudio=null;}
        for(const t of $$('.soundboard-tile.playing'))t.classList.remove('playing');
        soundboardAudio=new Audio(item.url);soundboardAudio.volume=previewVolume(item.volume);tile.classList.add('playing');
        soundboardAudio.onended=()=>tile.classList.remove('playing');
        soundboardAudio.onerror=()=>{tile.classList.remove('playing');$('#form-error').textContent='Preview failed to load.';};
        await soundboardAudio.play();
    }catch(e){if(e&&e.name==='AbortError')return;tile.classList.remove('playing');$('#form-error').textContent='Preview blocked by browser: '+e.message;}  // AbortError: a second tap replaced this preview
}
async function playPreview(value){if(previewAudio){previewAudio.pause();previewAudio=null;}if(previewContext){const previous=previewContext;previewContext=null;if(previous.state!=='closed')await previous.close();}try{if(value==='none')return;if(['chime','pulse'].includes(value)){const Context=window.AudioContext||window.webkitAudioContext;if(!Context)throw Error('Audio preview is unavailable in this browser.');const c=new Context();previewContext=c;await c.resume();const gain=c.createGain();gain.connect(c.destination);gain.gain.setValueAtTime(.12,c.currentTime);gain.gain.exponentialRampToValueAtTime(.001,c.currentTime+.6);const o=c.createOscillator();o.type='sine';o.frequency.setValueAtTime(value==='chime'?660:220,c.currentTime);o.frequency.setValueAtTime(value==='chime'?880:330,c.currentTime+.15);o.connect(gain);o.start();o.stop(c.currentTime+.6);o.onended=()=>{if(c.state!=='closed')c.close();if(previewContext===c)previewContext=null;};}else{
    // v1.5.6 — Audio loading often fails with the cryptic browser-native
    // "no supported source" error. Wire a specific error handler so the user
    // sees an actionable hint instead of guessing.
    previewAudio=new Audio('/media/'+encodeURIComponent(value));previewAudio.volume=previewVolume(config.default_volume);
    const loadError=new Promise((_,reject)=>{
        previewAudio.addEventListener('error',()=>{
            const err=previewAudio.error;
            const codes={1:'Aborted while loading.',2:'Network error loading audio.',3:'Browser could not decode this audio file.',4:'This audio format is not supported by your browser. Re-export as standard MP3 (constant bitrate Layer 3) or WAV.'};
            reject(new Error(codes[err?.code]||'Audio could not be loaded.'));
        },{once:true});
    });
    await Promise.race([previewAudio.play().catch(e=>{throw e;}),loadError]);
}}catch(e){if(e&&e.name==='AbortError')return;$('#form-error').textContent='Preview failed: '+(e.message||'unknown error');}}
async function copyPayment(value,box,btn){try{await navigator.clipboard.writeText(value);if(!btn)return;if(!btn.dataset.label)btn.dataset.label=btn.textContent;btn.textContent='Copied ✓';btn.classList.add('copied');clearTimeout(btn.copyTimer);btn.copyTimer=setTimeout(()=>{btn.textContent=btn.dataset.label;btn.classList.remove('copied');},1800);}catch(e){const input=box.querySelector('input');if(input){input.focus();input.select();}let n=box.querySelector('.copy-fallback');if(!n){n=note('','fine copy-fallback');(input||box.lastElementChild).after(n);}n.textContent='Copy manually: '+value;}}
$('#remember-supporter').checked=safeStore.get('ace-remember')==='yes';
$('#forget-supporter').onclick=async()=>{try{await api('/api/public/forget-browser',{});safeStore.remove('ace-remember');$('#remember-supporter').checked=false;$('#form-error').textContent='Browser recognition removed. Existing donation history is unchanged.';}catch(e){$('#form-error').textContent=e.message;}};
init();

// Name-token regex fallback — used when server did not persist voice_genders (browser engine,
// legacy settings, or admins who typed raw voice IDs into the TTS JSON array). Covers the common
// Microsoft/Edge voice name tokens; unmatched voices land in the "any" bucket.
// v1.5.8 — pattern changed from \bName\b to (non-letter)Name(not-lowercase) to catch CamelCase
// voice IDs like 'en-US-AvaMultilingualNeural' where 'a'→'M' isn't a word boundary.
const VOICE_MALE_TOKENS=/(^|[^A-Za-z])(Andrew|Brian|William|Guy|Davis|Jason|Tony|Christopher|Eric|Jacob|Ethan|Roger|Steffan|Drew|Madhur|Prabhat|Florian|Remy|Giuseppe|Hyunsu|Mark|David|Thomas|Liam|Henri|Diego|Ryan|Noah|Kai|Lucas|Alonso|Rehaan|Arnav|Ravi|Niwat|Bashkar|Ibrahim|Hamed|Mohan|Male)(?![a-z])/;
const VOICE_FEMALE_TOKENS=/(^|[^A-Za-z])(Ava|Emma|Jenny|Aria|Sara|Nancy|Michelle|Monica|Zira|Hazel|Catherine|Claire|Elvira|Swara|Neerja|Seraphina|Vivienne|Thalita|Natasha|Clara|Fiona|Freya|Isabella|Luna|Nova|Sofia|Ananya|Kavya|Pooja|Priya|Anju|Lekha|Shruti|Pallavi|Heera|Aditi|Kalpana|Female)(?![a-z])/;
function voiceGender(id){
    const g=config.voice_genders?.[id];
    if(g==='Male')return 'male';
    if(g==='Female')return 'female';
    if(VOICE_MALE_TOKENS.test(id))return 'male';
    if(VOICE_FEMALE_TOKENS.test(id))return 'female';
    return 'any';
}
function voiceDetail(id){
    const m=/^([a-z]{2,3})[-_]([A-Z]{2})\b/.exec(id);let lang='';
    if(m){try{lang=new Intl.DisplayNames(['en'],{type:'language'}).of(m[1]+'-'+m[2])||'';}catch(_){lang=m[1]+'-'+m[2];}}
    return [lang,/Multilingual/i.test(id)||/^hi[-_]/i.test(id)?'Hinglish-ready':''].filter(Boolean).join(' · ');
}
function buildVoices(){
    const host=$('#voice-choices');host.replaceChildren();
    const groups={male:[],female:[],any:[]};
    for(const v of config.voices)groups[voiceGender(v)].push(v);
    // v1.5.8 — labels use emoji + explicit Male/Female wording, always numbered so admins see "Male 1, Male 2" clearly.
    const META={male:{sym:'👨',word:'Male',cls:'voice-male'},female:{sym:'👩',word:'Female',cls:'voice-female'},any:{sym:'🎙️',word:'Voice',cls:'voice-any'}};
    for(const g of ['male','female','any']){
        const list=groups[g],meta=META[g];
        list.forEach((v,i)=>{
            const num=list.length>1?' '+(i+1):'';
            const friendly=meta.word+num;
            const realName=config.voice_labels?.[v]||({'en-IN':'English · India','hi-IN':'Hindi · India'})[v]||v;
            const b=document.createElement('button');
            b.type='button';
            b.className='voice-card '+meta.cls;
            b.setAttribute('aria-pressed',String($('#voice').value===v));
            b.title=realName;
            b.setAttribute('aria-label',friendly+' — '+realName);
            const gi=el('span',meta.sym,'voice-gender-icon');
            const label=el('span',undefined,'voice-text');
            label.append(el('span',friendly,'voice-friendly-name'));
            const detail=voiceDetail(v);
            if(detail)label.append(el('span',detail,'voice-sub'));
            const spk=el('span','🔊','voice-preview-spk');
            spk.setAttribute('role','button');spk.setAttribute('aria-label','Preview '+friendly);
            spk.onclick=(e)=>{e.stopPropagation();$('#voice').value=v;for(const x of host.children){x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));}$('#preview-voice').click();};
            b.append(gi,label,spk);
            b.onclick=()=>{$('#voice').value=v;for(const x of host.children){x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));}};
            if($('#voice').value===v)b.classList.add('selected');
            host.append(b);
        });
    }
    const enabled=config.tts_enabled&&config.tts_engine!=='off';
    document.querySelector('[name=tts]').disabled=!enabled;
    $('#preview-voice').disabled=!enabled;
    $('#voice-feedback').textContent=!enabled?'Voice readout is currently off.':config.tts_engine==='azure'?'Voice readout uses Microsoft Azure. English/Hinglish pronunciation varies; preview before choosing.':config.tts_engine==='edge'?'Voice readout uses Microsoft’s online Edge voices, so your message is sent to Microsoft to be spoken.':'Tap 🔊 on a card to preview that voice. Hinglish pronunciation depends on the configured voice.';
}
let voiceAudio;
$('#preview-voice').onclick=async()=>{const feedback=$('#voice-feedback'),voice=$('#voice').value;try{if(voiceAudio)voiceAudio.pause();if(config.tts_engine==='browser'){if(!('speechSynthesis'in window))throw Error('Voice preview is unavailable in this browser.');speechSynthesis.cancel();let voices=speechSynthesis.getVoices();if(!voices.length){await new Promise(r=>setTimeout(r,500));voices=speechSynthesis.getVoices();}const found=voices.find(x=>x.name===voice||x.lang.toLowerCase()===voice.toLowerCase());if(!found)throw Error('This voice is not installed on this device. The creator can configure server voices.');const sample='GG bhai, kya clutch tha! Thanks for the stream.',u=new SpeechSynthesisUtterance(typeof maybeTransliterate==='function'?maybeTransliterate(sample,found):sample);u.volume=previewVolume(config.tts_volume);u.voice=found;u.lang=found.lang;speechSynthesis.speak(u);feedback.textContent='Preview uses this device’s voice; the stream device may differ.';}else{voiceAudio=new Audio('/api/public/voice-preview?voice='+encodeURIComponent(voice));voiceAudio.volume=previewVolume(config.tts_volume);await voiceAudio.play();feedback.textContent='Playing a sample of the stream voice.';}}catch(e){feedback.textContent='Preview unavailable. '+e.message;}};
