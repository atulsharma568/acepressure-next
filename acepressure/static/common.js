'use strict';
const $=(s,r=document)=>r.querySelector(s);
const $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
const INR=p=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:p%100?2:0}).format((p||0)/100);
const date=t=>t?new Date(t*1000).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',day:'numeric',month:'short',year:'numeric',hour:'numeric',minute:'2-digit'}):'—';
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(text,fn,cls=''){const b=el('button',text,cls);b.type='button';b.addEventListener('click',fn);return b;}
function note(text,cls='notice'){return el('p',text,cls);}
async function readJSON(r){try{return await r.json();}catch(_){return {error:r.status===413?'That file is too large. Sounds and images can be up to 8 MB, videos up to 24 MB.':'Request failed (HTTP '+r.status+'). Check that AcePressure is still running.'};}}
async function api(url,body,headers={}){const opts={headers:{...headers},credentials:'same-origin'};if(body!==undefined){opts.method='POST';opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body);}const r=await fetch(url,opts);const d=await readJSON(r);if(!r.ok)throw Object.assign(Error(d.error||'Request failed'),{status:r.status});return d;}
function options(select,items){select.replaceChildren(...items.map(x=>{const o=el('option',typeof x==='string'?x:x.label);o.value=typeof x==='string'?x:x.value;return o;}));}
function empty(node,text){node.replaceChildren(note(text,'empty'));}
// A volume in % (a library sound's, or the voice's) as an audio element volume; missing or odd values play as uploaded.
function volumeLevel(v){return typeof v==='number'&&v>=0&&v<=100?v/100:1;}

/* Hinglish detection and conversion for alerts from servers older than 1.6.2. Since 1.6.2 the server decides
   (acepressure/tts_service.py) and sends p.hinglish and p.speech_hi with each alert, so these short lists are only a fallback.
   Returns true if text contains Devanagari OR a meaningful fraction of romanized-Hindi tokens.
   Used by browser TTS to prefer a Hindi-capable voice when the operator-picked voice is English-only. */
const HINGLISH_WORDS=new Set(['bhai','bhaai','bhaiya','bhaiyya','didi','yaar','yar','dost','kya','kyun','kaise','kaisa','kaisi','kahan','kab','kaun','kyu','hai','hain','tha','thi','ho','hoga','hogi','honge','raha','rahi','rahe','nahi','nahin','mat','na','aap','tum','main','mai','mera','meri','mere','tera','teri','tere','hamara','hamari','tumhara','tumhari','apna','apni','apne','bahut','bohot','thoda','zyada','kam','sab','kuch','koi','achha','accha','achhi','bura','buri','badiya','badhiya','mast','jhakaas','namaste','dhanyavaad','shukriya','bhagwan','paisa','paise','rupaye','khel','jeet','haar','maza','mazaa','mazaak','clutch','op','ekdum','bilkul','sahi','galat','theek','thik','arre','arrey','oye','waah','wah','kal','aaj','subah','raat','pyaar','pyar','desi','bharat','india','jaldi','dheere','chalo','suno','dekho','bolo']);
function hasDevanagari(t){return /[ऀ-ॿ]/.test(t||'');}
function hinglishScore(t){if(!t)return 0;if(hasDevanagari(t))return 1;const tokens=(t.toLowerCase().match(/\b[a-z]{2,20}\b/g)||[]);if(!tokens.length)return 0;let hits=0;for(const w of tokens)if(HINGLISH_WORDS.has(w))hits++;return hits/tokens.length;}
function isHinglish(t){return hinglishScore(t)>=0.15;}
function pickVoiceForText(text,preferredVoice,availableVoices,hinglish){/* availableVoices from speechSynthesis.getVoices(); hinglish: the server's verdict, when it sent one */
    if(!availableVoices||!availableVoices.length)return preferredVoice;
    const preferred=availableVoices.find(v=>v.name===preferredVoice||v.lang.toLowerCase()===(preferredVoice||'').toLowerCase());
    if(!(typeof hinglish==='boolean'?hinglish:isHinglish(text)))return preferred||preferredVoice;
    /* Hinglish detected — prefer a Hindi voice if the preferred one isn't one. */
    const preferredIsHindi=preferred&&(preferred.lang||'').toLowerCase().startsWith('hi');
    if(preferredIsHindi)return preferred;
    const hindi=availableVoices.find(v=>(v.lang||'').toLowerCase().startsWith('hi-in'))||availableVoices.find(v=>(v.lang||'').toLowerCase().startsWith('hi'));
    return hindi||preferred||preferredVoice;
}

/* Roman Hindi → Devanagari transliteration — mirror of acepressure/tts_service.py.
   Applied before speechSynthesis.speak() when the selected voice is Hindi-capable,
   so Hindi/Multilingual browser voices read "bhai" as भाई, not "bai". */
const HINGLISH_TRANSLITERATION={
    bhai:'भाई',bhaai:'भाई',bhaiya:'भैया',bhaiyya:'भैया',
    didi:'दीदी',yaar:'यार',yar:'यार',dost:'दोस्त',
    aap:'आप',tum:'तुम',main:'मैं',mai:'मैं',
    mera:'मेरा',meri:'मेरी',mere:'मेरे',
    tera:'तेरा',teri:'तेरी',tere:'तेरे',
    hamara:'हमारा',hamari:'हमारी',
    tumhara:'तुम्हारा',tumhari:'तुम्हारी',
    apna:'अपना',apni:'अपनी',apne:'अपने',
    kya:'क्या',kyun:'क्यों',kyu:'क्यों',
    kaise:'कैसे',kaisa:'कैसा',kaisi:'कैसी',
    kahan:'कहाँ',kab:'कब',kaun:'कौन',
    hai:'है',hain:'हैं',tha:'था',thi:'थी',
    hoga:'होगा',hogi:'होगी',honge:'होंगे',
    raha:'रहा',rahi:'रही',rahe:'रहे',
    nahi:'नहीं',nahin:'नहीं',mat:'मत',
    bahut:'बहुत',bohot:'बहुत',thoda:'थोड़ा',zyada:'ज़्यादा',kam:'कम',
    sab:'सब',kuch:'कुछ',koi:'कोई',
    achha:'अच्छा',accha:'अच्छा',achhi:'अच्छी',
    bura:'बुरा',buri:'बुरी',
    badiya:'बढ़िया',badhiya:'बढ़िया',
    mast:'मस्त',jhakaas:'झकास',
    theek:'ठीक',thik:'ठीक',sahi:'सही',galat:'ग़लत',
    bilkul:'बिल्कुल',ekdum:'एकदम',
    namaste:'नमस्ते',namaskar:'नमस्कार',
    dhanyavaad:'धन्यवाद',dhanyawad:'धन्यवाद',shukriya:'शुक्रिया',
    arre:'अरे',arrey:'अरे',oye:'ओए',
    waah:'वाह',wah:'वाह',ohho:'ओहो',
    paisa:'पैसा',paise:'पैसे',
    rupaye:'रुपये',rupay:'रुपये',rupaiya:'रुपया',
    jaldi:'जल्दी',dheere:'धीरे',ruko:'रुको',chalo:'चलो',
    suno:'सुनो',dekho:'देखो',bolo:'बोलो',
    khela:'खेला',khelna:'खेलना',
    kal:'कल',aaj:'आज',parso:'परसों',
    subah:'सुबह',shaam:'शाम',raat:'रात',din:'दिन',
    khana:'खाना',pani:'पानी',paani:'पानी',chai:'चाय',ghar:'घर',
    maza:'मज़ा',mazaa:'मज़ा',majaa:'मज़ा',mazaak:'मज़ाक़',
    pyaar:'प्यार',pyar:'प्यार',mohabbat:'मोहब्बत',
    bhagwan:'भगवान',ishwar:'ईश्वर',jai:'जय',
    bharat:'भारत',hindustan:'हिन्दुस्तान',desi:'देसी',
    jeet:'जीत',jeeta:'जीता',haar:'हार',haara:'हारा',khel:'खेल'
};
// Match the server's conservative language policy.
for(const word of ['main','mat','mere','din','mast','ram','na','ho']){
    HINGLISH_WORDS.delete(word);delete HINGLISH_TRANSLITERATION[word];
}
for(const word of ['the','enjoy','clutch','op','hehe','school','live','stream','donate','tip','india'])HINGLISH_WORDS.delete(word);
const _TRANSLIT_RE=new RegExp('\\b('+Object.keys(HINGLISH_TRANSLITERATION).sort((a,b)=>b.length-a.length).join('|')+')\\b','gi');
function transliterateHinglish(text){
    if(!text)return text;
    return text.replace(_TRANSLIT_RE,m=>HINGLISH_TRANSLITERATION[m.toLowerCase()]||m);
}
function voiceHandlesHindi(voiceObj){
    if(!voiceObj)return false;
    const lang=(voiceObj.lang||'').toLowerCase();
    const name=(voiceObj.name||'').toLowerCase();
    return lang.startsWith('hi')||name.includes('multilingual')||name.includes('hindi');
}
function maybeTransliterate(text,voiceObj){
    if(!isHinglish(text))return text;
    if(!voiceHandlesHindi(voiceObj))return text;
    return transliterateHinglish(text);
}
