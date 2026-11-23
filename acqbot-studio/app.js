(()=>{'use strict';
const el=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),val=s=>String(s??'').trim(),yes=s=>!!val(s)&&!/^(?:tbd|n\/a|na|none|unknown|pending|not provided|not applicable)$/i.test(val(s)),norm=s=>val(s).toLowerCase().replace(/[^a-z0-9]/g,'');
const specs=[
['title','Topic title','public'],['topicNumber','AcqBot / topic number','public'],['release','Release','public'],['program','Program (SBIR / STTR)','public'],['phase','Phase / D2P2','public'],['technology','Technology areas','public'],['objective','Objective','public',1],['description','Description','public',1],['keywords','Keywords','public',1],['phaseI','Phase I description','public',1],['phaseII','Phase II description','public',1],['phaseIII','Phase III / dual use','public',1],['references','References','public',1],
['org','Submitting organization','admin'],['customer','Supported organization / sponsor','admin'],['mopm','MOPM','admin'],['mopmEmail','MOPM email','admin'],['tpoc','TPOC','admin'],['tpocEmail','TPOC email','admin'],['co','Contracting officer','admin'],['coEmail','CO email','admin'],['awards','Proposed award count','admin'],['awardValue','Proposed amount per award','admin'],['period','Period of performance','admin'],['needDate','Required need date','admin'],['transition','Transition / follow-on ownership','admin',1],['pa','Public Affairs review','admin'],['opsec','OPSEC review','admin'],['fdo','Foreign Disclosure review','admin'],['legal','Legal review','admin'],['pk','PK review','admin'],['spnNote','SPN routing notes','admin',1]
];
const alias={
title:['Topic Title','Topic Name','Title'],topicNumber:['ID','AcqBot ID','Topic ID','OUSW TOPIC NUMBER','Topic Number'],
release:['Release #','Release Name','Target Release','Release'],program:['Program','SBIR OR STTR'],phase:['Phase','Topic Category','D2P2?'],
technology:['Technology Areas','Technology Area(s)','DAF Modernization Areas'],objective:['Topic Objective','Objective'],description:['Topic Description','Description'],keywords:['Topic Keywords','Keywords'],
phaseI:['Topic Phase I Description','Phase I Description'],phaseII:['Topic Phase II Description','Phase II Description'],
phaseIII:['Topic Phase III / Dual Use Description','Topic Phase III Dual Use Description','Phase III Description','Dual Use Description'],references:['Topic References','References'],
org:['Wing/Directorate/Delta','Submitting Organization','Managing Organization'],customer:['Supported Organization','Operational Sponsor','Customer'],
mopmEmail:['Primary MOPM Email'],tpocEmail:['Primary TPOC Email'],coEmail:['Managing Organization Contracting Officer Email'],
awards:['Number of Awards','# of Awards','Proposed Number of Awards'],awardValue:['Estimated Per Award Amt','Estimated Award Amount','Amount Per Award'],
period:['PoP Duration','Period of Performance'],needDate:['Required Need Date'],transition:['Transition Plan','Phase III Transition Plan','Follow On Funding Plan'],
pa:['Public Affairs Disposition','PA Review','Public Affairs Approval'],opsec:['OPSEC Disposition','OPSEC Approval'],fdo:['Foreign Disclosure Disposition','FDO Approval'],legal:['Legal Review','JA Review'],pk:['PK Review','Contracting Review'],spnNote:['SPN Notes','Coordination Notes']
};
const blank=()=>Object.fromEntries(specs.map(x=>[x[0],'']));
const st={rows:[blank()],index:0,current:'topic',documents:{topic:'',spn:''},raw:''};
const field=(k,r)=>Object.entries(r||{}).find(([key,v])=>(alias[k]||[]).some(a=>norm(a)===norm(key))&&yes(v))?.[1]||'';
function mapRow(obj){
const r=blank();for(const k of Object.keys(alias))r[k]=val(field(k,obj));
const full=(stem)=>[obj[stem+' First Name'],obj[stem+' Last Name']].filter(yes).join(' ');
r.mopm=full('Primary MOPM');r.tpoc=full('Primary TPOC');r.co=full('Managing Organization Contracting Officer');
if(/^(yes|y|true|1)$/i.test(val(obj['D2P2?'])))r.phase='D2P2';
if(/sttr/i.test(r.program))r.program='STTR';else if(/sbir/i.test(r.program))r.program='SBIR';
return r;
}
function makeInputs(){
for(const [key,label,group,long] of specs){
const div=document.createElement('div');div.className='field'+(long?' wide':'');
const lab=document.createElement('label');lab.className='fieldlabel';lab.htmlFor='f_'+key;lab.textContent=label;div.append(lab);
let input;if(long){input=document.createElement('textarea');input.rows=4}else{input=document.createElement('input');input.type='text'}
input.id='f_'+key;input.addEventListener('input',()=>{st.rows[st.index][key]=input.value;rebuild();picker()});div.append(input);el(group==='public'?'publicFields':'adminFields').append(div);
}
}
function fill(){for(const [k] of specs)el('f_'+k).value=st.rows[st.index][k]||'';el('raw').value=st.raw}
function picker(){
const sel=el('recordPicker');sel.innerHTML='';
st.rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=(r.title||'Topic '+(i+1)).slice(0,44);sel.append(o)});
sel.value=st.index;
el('topicscount').textContent=st.rows.length+(st.rows.length===1?' topic':' topics');
}
function para(hd,content){
return yes(content)?'<h3>'+esc(hd)+'</h3><p>'+esc(content).replace(/\n/g,'<br>')+'</p>':'';
}
function makeTopic(r){
let out='<div class="docmeta">PUBLIC-FACING SBIR/STTR SOLICITATION · WORKING DRAFT</div><h2>'+esc(r.title||'Untitled topic')+'</h2>';
const meta=[r.topicNumber,r.program,r.phase,r.release].filter(yes);
if(meta.length)out+='<div class="docmeta">'+meta.map(esc).join(' · ')+'</div>';
out+=para('Technology Area(s)',r.technology)+para('Objective',r.objective)+para('Description',r.description)+para('Keywords',r.keywords);
if(!/d2p2|direct.*phase.*ii/i.test(r.phase)&&!/^not applicable/i.test(r.phaseI))out+=para('Phase I',r.phaseI);
out+=para('Phase II',r.phaseII)+para('Phase III / Dual Use',r.phaseIII);
if(yes(r.references)){let refs=val(r.references).split(/;|\n/).map(val).filter(yes);out+='<h3>References</h3><ol>'+refs.map(x=>'<li>'+esc(x.replace(/^\d+[.)]\s*/,''))+'</li>').join('')+'</ol>'}
if(!yes(r.description)&&!yes(r.objective))out+='<p style="color:#a35b4a">The source lacks a public narrative. Add the missing fields before export.</p>';
return out;
}
function table(rows){return '<table style="width:100%;border-collapse:collapse;font-size:12px">'+rows.map(x=>'<tr><td style="width:42%;color:#777;vertical-align:top;padding:6px 12px 6px 0">'+esc(x[0])+'</td><td style="vertical-align:top;padding:6px 0">'+esc(yes(x[1])?x[1]:'Not provided')+'</td></tr>').join('')+'</table>'}
function makeSPN(r){
let t='<div class="docmeta">INTERNAL SPN COORDINATION DRAFT · NOT SIGNED</div><h2>Topic Coordination / SPN</h2><p><b>'+esc(r.title||'Untitled topic')+'</b></p>';
t+='<p>Request coordination and review of this proposed '+esc(r.program||'SBIR/STTR')+' topic for '+esc(r.release||'the designated release')+'. Confirm all approvals against authoritative records before signature routing.</p>';
t+='<h3>Identification</h3>'+table([['Topic number',r.topicNumber],['Topic title',r.title],['Release',r.release],['Program',r.program],['Phase / category',r.phase],['Submitting organization',r.org],['Operational customer',r.customer]]);
t+='<h3>Proposed award strategy</h3>'+table([['Number of awards',r.awards],['Estimated per award',r.awardValue],['Period of performance',r.period],['Need date',r.needDate],['Transition partner',r.transition]]);
t+='<h3>Contacts</h3>'+table([['MOPM',r.mopm],['MOPM email',r.mopmEmail],['TPOC',r.tpoc],['TPOC email',r.tpocEmail],['Contracting officer',r.co],['CO email',r.coEmail]]);
t+='<h3>Review records (verify each disposition)</h3>'+table([['Public Affairs',r.pa],['OPSEC',r.opsec],['Foreign Disclosure',r.fdo],['Legal / JA',r.legal],['Contracting / PK',r.pk]]);
t+=para('Additional coordination',r.spnNote);
t+='<h3>Proposed routing</h3><p>Assign the lead, validate the final public draft against the AcqBot source, coordinate applicable reviewers, return substantive issues to the submitting PM/TPOC, and obtain signatures on the approved SPN form. This working draft is not an official signed SPN.</p>';
return t;
}
function saveEdit(){if(st.current!=='review')st.documents[st.current]=el('paper').innerHTML}
function display(){
el('paper').classList.toggle('hidden',st.current==='review');el('review').classList.toggle('hidden',st.current!=='review');
el('download').disabled=el('copy').disabled=st.current==='review';
if(st.current==='review')el('review').innerHTML=makeReview(st.rows[st.index]);else el('paper').innerHTML=st.documents[st.current];
}
function rebuild(){st.documents={topic:makeTopic(st.rows[st.index]),spn:makeSPN(st.rows[st.index])};display()}
function setPreview(t){saveEdit();st.current=t;document.querySelectorAll('[data-preview]').forEach(b=>b.classList.toggle('on',b.dataset.preview===t));display()}
function reviewChecks(r){
const arr=[];
function check(name,ok,description){arr.push({name,ok:!!ok,description})}
check('Public-facing title',yes(r.title),'Clear, vendor-neutral and suitable for publication.');
check('Measurable objective',yes(r.objective),'Describe the desired research outcome.');
check('Technical scope',yes(r.description),'Define the operational problem, technical challenge, test metrics and boundaries.');
check('Phase II deliverables',yes(r.phaseII),'Define prototype, government verification and demo outputs.');
if(!/d2p2/i.test(r.phase))check('Phase I scope',yes(r.phaseI),'Only necessary for a pathway that includes Phase I.');
check('Phase III transition',yes(r.phaseIII),'Describe a credible dual-use or government transition.');
check('References',yes(r.references),'Check publication status and exact edition before release.');
check('Assigned MOPM',yes(r.mopm),'Identify who coordinates the topic.');
check('Government TPOC',yes(r.tpoc),'Identify who oversees the technical effort.');
check('Contracting officer',yes(r.co),'Identify the CO or route to contracting for support.');
check('Funding assumptions',yes(r.awards)&&yes(r.awardValue),'Confirm proposed award count and planning amount.');
for(const [name,key] of [['Public Affairs','pa'],['OPSEC','opsec'],['Foreign Disclosure','fdo'],['Legal','legal'],['PK','pk']])check(name+' coordination',yes(r[key]),'Record and verify actual review artifacts; completion is not inferred.');
const text=[r.title,r.objective,r.description,r.phaseI,r.phaseII,r.phaseIII,r.references].join('\n');
check('No apparent restriction markings',!/\b(CUI|FOUO|NOFORN|SECRET|ITAR)\b/i.test(text),'Automated scan does not establish public release approval.');
check('No internal contacts in public fields',!(/[\w.+-]+@[\w.-]+\.[a-z]{2,}/i.test(text)),'Keep POC details within the internal coordination package.');
return arr;
}
function makeReview(r){
const arr=reviewChecks(r),done=arr.filter(x=>x.ok).length;
return '<small>PRE-PUBLICATION QUALITY CHECK</small><h3>'+done+' / '+arr.length+' checks passed</h3><p>Completeness review only. Does not replace PA/OPSEC/FDO/legal/PK review or certify Distribution A.</p>'+arr.map(x=>'<div class="reviewitem '+(x.ok?'ok':'')+'"><span class="tick">'+(x.ok?'✓':'!')+'</span><div><strong>'+esc(x.name)+'</strong><p>'+esc(x.description)+'</p></div></div>').join('');
}
function use(rows,source,raw){
const recs=rows.map(mapRow).filter(r=>Object.values(r).filter(yes).length>=2),seen=new Set();
st.rows=recs.filter(r=>{const id=[r.title,r.topicNumber,r.objective].map(norm).join('|');if(seen.has(id))return false;seen.add(id);return true});
if(!st.rows.length)st.rows=[blank()];st.index=0;st.raw=raw||'';picker();fill();st.current='topic';document.querySelectorAll('[data-preview]').forEach(b=>b.classList.toggle('on',b.dataset.preview==='topic'));rebuild();
el('message').textContent=recs.length?'Imported '+st.rows.length+' topic record(s). Verify mapped data and edit as needed.':'No recognized record found. Enter the fields manually or use a column-based AcqBot export.';
el('filename').textContent=source;el('filemeta').textContent='Processed locally';el('filebar').classList.remove('hidden');
}
function matrixToObjects(matrix){
const rows=matrix.map(row=>(row||[]).map(val));let best=-1,score=0;
for(let i=0;i<Math.min(rows.length,20);i++){const n=rows[i].filter(k=>Object.values(alias).some(a=>a.some(b=>norm(k)===norm(b)))).length;if(n>score){best=i;score=n}}
if(score>=3)return rows.slice(best+1).filter(row=>row.some(yes)).map(row=>Object.fromEntries(rows[best].map((key,i)=>[key,row[i]]).filter(x=>yes(x[0]))));
const ob={};for(const row of rows){const k=/^\d+$/.test(row[0])&&row.length>2?row[1]:row[0],v=/^\d+$/.test(row[0])&&row.length>2?row[2]:row[1];if(yes(k)&&yes(v))ob[k]=v}
return Object.keys(ob).length?[ob]:[];
}
function parseText(text){
try{let j=JSON.parse(text);return Array.isArray(j)?j:Array.isArray(j.topics)?j.topics:Array.isArray(j.records)?j.records:[j]}catch{}
const obj={},lines=String(text).replace(/\r/g,'').split('\n');let last='';
for(const l of lines){
const m=l.match(/^\s*([^:\t|]{2,100})\s*[:\t|]\s*(.*)$/);
if(m&&Object.values(alias).some(a=>a.some(s=>norm(s)===norm(m[1])))){last=m[1];obj[last]=m[2]}
else if(last&&val(l))obj[last]+='\n'+l.trim();
}
return Object.keys(obj).length?[obj]:[];
}
async function readPDF(file){
if(typeof pdfjsLib==='undefined')throw Error('PDF library unavailable. Try Excel, CSV or text.');
pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
const pdf=await pdfjsLib.getDocument({data:await file.arrayBuffer()}).promise;let raw='';
for(let p=1;p<=Math.min(pdf.numPages,100);p++){const page=await pdf.getPage(p),items=(await page.getTextContent()).items;let old=null;
for(const a of items){const y=a.transform?.[5];if(old!==null&&typeof y==='number'&&Math.abs(y-old)>3)raw+='\n';else raw+=' ';raw+=a.str;old=y}}
return raw;
}
async function upload(file){
if(!file)return;el('message').textContent='Reading '+file.name+'…';try{
let rows=[],raw='',name=file.name.toLowerCase();
if(/\.(xls|xlsx|csv|tsv)$/.test(name)){
if(typeof XLSX==='undefined')throw Error('Spreadsheet library unavailable; reload the page.');
const book=XLSX.read(await file.arrayBuffer(),{type:'array'});
for(const key of book.SheetNames){const arr=XLSX.utils.sheet_to_json(book.Sheets[key],{header:1,defval:''});rows.push(...matrixToObjects(arr));raw+='SHEET: '+key+'\n'+arr.map(r=>r.join(' | ')).join('\n')+'\n\n'}
}else{raw=name.endsWith('.pdf')?await readPDF(file):await file.text();rows=parseText(raw)}
use(rows,file.name,raw);el('filemeta').textContent=(Math.round(file.size/1024)||1)+' KB · browser-only';
}catch(e){el('message').textContent='Import failed: '+e.message}
}
function saveBlob(blob,filename){
const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1200);
}
function download(t){
saveEdit();const r=st.rows[st.index],title=t==='topic'?'Public_Topic':'SPN_Draft';
const base=(r.topicNumber||r.title||'AcqBot_Topic').replace(/[^a-z0-9_-]+/gi,'_').slice(0,56);
const html='<!doctype html><html><head><meta charset="utf-8"><style>body{font:11pt Arial;line-height:1.5}h2{font-size:19pt}h3{font-size:12pt;text-transform:uppercase;margin-top:16pt}table{width:100%;border-collapse:collapse}td{border-bottom:1px solid #ddd;padding:7pt}li{margin-bottom:7pt}</style></head><body>'+st.documents[t]+'</body></html>';
saveBlob(new Blob(['\ufeff',html],{type:'application/msword'}),base+'_'+title+'.doc');el('actionStatus').textContent='Downloaded Word-compatible .doc draft.';
}
function sample(){
use([{'Topic Title':'Expeditionary Aircraft Power System Health Monitoring','ID':'DEMO-001','Release #':'FY27 R5','Program':'SBIR','D2P2?':'Yes',
'Technology Areas':'Electrical power systems; condition-based maintenance; diagnostics',
'Topic Objective':'Develop and demonstrate an aircraft power subsystem health-monitoring capability that detects and characterizes emerging faults under representative operational conditions.',
'Topic Description':'Aircraft electrical systems operating in austere conditions can develop intermittent faults that are difficult to reproduce during routine maintenance. Research non-intrusive sensing, fault isolation and edge analytics that distinguish real degradation from transient operating conditions. Propose testable metrics for detection performance, false alarms, latency and integration.',
'Topic Phase II Description':'Develop a prototype and verification plan. Demonstrate against representative hardware and report fault-detection performance, false-alarm rates, compute requirements and interface constraints.',
'Topic Phase III / Dual Use Description':'Potential transition to aircraft sustainment engineering and maintenance organizations, subject to sponsor confirmation and follow-on funding. Commercial uses include industrial equipment monitoring.',
'Topic References':'MIL-STD-704, Aircraft Electric Power Characteristics (revision to verify); MIL-STD-810H, Environmental Engineering Considerations and Laboratory Tests (applicability to verify)',
'Primary MOPM First Name':'Sample','Primary MOPM Last Name':'Lead','Primary TPOC First Name':'Sample','Primary TPOC Last Name':'Engineer',
'Managing Organization Contracting Officer First Name':'Sample','Managing Organization Contracting Officer Last Name':'CO','Number of Awards':'2'}],
'Sample record','Sample only; no actual approval or sponsor.');
}
function init(){
makeInputs();fill();rebuild();
document.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click',()=>{const t=b.dataset.edit;document.querySelectorAll('[data-edit]').forEach(x=>x.classList.toggle('on',x===b));el('publicFields').classList.toggle('hidden',t!=='public');el('adminFields').classList.toggle('hidden',t!=='admin');el('rawPane').classList.toggle('hidden',t!=='raw')}));
document.querySelectorAll('[data-preview]').forEach(b=>b.addEventListener('click',()=>setPreview(b.dataset.preview)));
el('sample').addEventListener('click',sample);
el('recordPicker').addEventListener('change',e=>{saveEdit();st.index=Number(e.target.value);fill();rebuild()});
el('browse').addEventListener('click',e=>{e.stopPropagation();el('file').click()});
el('file').addEventListener('change',e=>upload(e.target.files?.[0]));
const zone=el('drop');zone.addEventListener('click',e=>{if(e.target.id!=='browse')el('file').click()});
zone.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();el('file').click()}});
for(const type of ['dragover','dragenter'])zone.addEventListener(type,e=>{e.preventDefault();zone.classList.add('drag')});
for(const type of ['dragleave','drop'])zone.addEventListener(type,e=>{e.preventDefault();zone.classList.remove('drag')});
zone.addEventListener('drop',e=>upload(e.dataTransfer?.files?.[0]));
el('paper').addEventListener('input',saveEdit);
el('download').addEventListener('click',()=>download(st.current));
el('both').addEventListener('click',()=>{download('topic');setTimeout(()=>download('spn'),500)});
el('copy').addEventListener('click',async()=>{saveEdit();try{await navigator.clipboard.writeText(el('paper').innerText);el('actionStatus').textContent='Text copied.'}catch{el('actionStatus').textContent='Clipboard unavailable; select and copy manually.'}});
el('rebuild').addEventListener('click',()=>{rebuild();el('actionStatus').textContent='Regenerated from current fields.'});
}
init();
})();