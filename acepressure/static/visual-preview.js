'use strict';
const q=new URLSearchParams(location.search),stage=$('#stage');
function render(v){v=applyVisuals(v);const vertical=q.get('layout')==='vertical';stage.className=(q.get('kind')==='alert'?'alert-stage ':'')+(vertical?'vertical':'horizontal');stage.replaceChildren(q.get('kind')==='alert'?alertCard({name:'Ace supporter',display_paise:50000,message:'GG! Thanks for the stream.',tier:4,test:true},v):goalCard({title:'Weekly support · preview',current:75000,target:200000,percent:37.5,design:'compact',style:'bar'},v));}
window.addEventListener('message',e=>{if(e.origin===location.origin&&e.source===parent&&e.data?.type==='ace-preview')render(e.data.visuals);});
api('/api/admin/visuals').then(d=>render(d.visuals));
