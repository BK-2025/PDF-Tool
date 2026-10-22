// Batch orchestration is sequential. Source File objects remain in the browser;
// the local server retains at most one source document per processing job.
let reviewed={},pagePlan=[],activeBatchItem=null,batchQueue=[],batchSession=null,batchRunning=false,batchStop=false,queueSequence=0,suggestions=[],savedPresets=[];
const builtinPresets=[
 {name:'OCR-Archiv · verlustfrei',profile:'lossless',dpi:200,skip_existing:true,terms:[],export_mode:'ocr'},
 {name:'Vertrag · kompakt',profile:'compact',dpi:200,skip_existing:true,terms:[],export_mode:'ocr'},
 {name:'Scan · genaue Erkennung',profile:'standard',dpi:300,skip_existing:false,terms:[],export_mode:'ocr'}
];
function pageFingerprint(n){return JSON.stringify([marks[n]||[],edits[n]||[]])}
function changedPages(){return [...new Set([...Object.keys(marks),...Object.keys(edits)])].filter(n=>(marks[n]||[]).length||(edits[n]||[]).length).map(Number).sort((a,b)=>a-b)}
function approvedPages(){return changedPages().filter(n=>reviewed[n]===pageFingerprint(n))}
function reviewPayload(){return {require_review:$('requireReview').checked,reviewed_pages:approvedPages()}}
function assertReviewed(){if($('requireReview').checked&&approvedPages().length!==changedPages().length)throw Error('Bitte alle geänderten Seiten in der Prüfansicht freigeben.')}
function workflowControls(){
 $('exportMode').querySelector('option[value=image]').textContent=$('sizeProfile').value==='lossless'?'Originaltext erhalten · ohne zusätzliche OCR':'Bild-PDF · ohne Textschicht';
 $('approvePage').disabled=busy||!count;
 $('nextReview').disabled=busy||!changedPages().some(n=>reviewed[n]!==pageFingerprint(n));
 $('batchSaveReview').hidden=!activeBatchItem;
 $('batchSaveReview').disabled=busy||!activeBatchItem;
 $('reviewSummary').textContent=count?`${approvedPages().length} / ${changedPages().length} geänderte Seiten freigegeben · Seite ${page+1}: ${reviewed[page]===pageFingerprint(page)?'geprüft':'noch nicht geprüft'}`:'Keine Datei geöffnet';
 if(count&&!pagePlan.length)pagePlan=Array.from({length:count},(_,i)=>({page:i,rotation:0}));
 renderPagePlan();
 for(let id of ['batchPrepare','batchRun','batchRetry','batchAgain','batchZip','batchClear','mergeQueue','batchFiles','batchTerms','batchDpi','batchProfile','batchSkip','batchAdopt','loadPreset','savePreset','deletePreset'])$(id).disabled=busy;
 $('batchStop').disabled=!batchRunning;
 for(let button of $('batchRows').querySelectorAll('button'))button.disabled=busy;
 for(let input of document.querySelectorAll('#suggestions input,#batchSuggestions input'))input.disabled=busy;
}
$('approvePage').onclick=()=>{reviewed[page]=pageFingerprint(page);controls();status(`Seite ${page+1} freigegeben. Jede weitere Änderung hebt diese Freigabe wieder auf.`)};
$('nextReview').onclick=()=>run(async()=>{let pending=changedPages().filter(n=>reviewed[n]!==pageFingerprint(n));if(!pending.length)return;page=pending.find(n=>n>page)??pending[0];editSelection=null;$('editor').hidden=true;await show()});
function renderPagePlan(){
 $('pagePlan').replaceChildren();
 pagePlan.forEach((entry,i)=>{
  let row=document.createElement('div'),label=document.createElement('span');label.textContent=`${i+1}. Original ${entry.page+1} · +${entry.rotation}° `;row.append(label);
  for(let [text,action,disabled] of [
   ['↑',()=>{[pagePlan[i-1],pagePlan[i]]=[pagePlan[i],pagePlan[i-1]]},i===0],
   ['↓',()=>{[pagePlan[i+1],pagePlan[i]]=[pagePlan[i],pagePlan[i+1]]},i===pagePlan.length-1],
   ['↶',()=>{entry.rotation=(entry.rotation+270)%360},false],
   ['↷',()=>{entry.rotation=(entry.rotation+90)%360},false],
   ['Entfernen',()=>pagePlan.splice(i,1),pagePlan.length===1]
  ]){let button=document.createElement('button');button.textContent=text;button.disabled=busy||disabled;button.onclick=()=>{action();renderPagePlan()};row.append(button)}
  $('pagePlan').append(row);
 });
}
$('applyPages').onclick=()=>run(async()=>{
 if(editSelection)throw Error('Textänderung zuerst übernehmen oder abbrechen.');
 let result=await(await api('/pages',{plan:pagePlan,marks,edits,page})).json();
 let expired=history.findLastIndex(state=>{let value=JSON.parse(state);return value.kind==='pages'&&!result.undo_ids.includes(value.id)});if(expired>=0)history=history.slice(expired+1);
 history.push(JSON.stringify({kind:'pages',id:result.undo}));count=result.pages;page=0;marks=result.marks;edits=result.edits;reviewed={};pagePlan=[];editSelection=null;$('editor').hidden=true;renderEdits();await show();await liveSearch();status('Seitenplan übernommen. Markierungen wurden mitgedreht und neu zugeordnet; Rückgängig ist möglich.');
});
function downloadBlob(blob,name){let url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),60000)}
$('split').onclick=()=>run(async()=>{
 if(editSelection||searchPending||Object.values(preview).some(rs=>rs.length))throw Error('Offene Textänderungen / Suchtreffer zuerst übernehmen oder verwerfen.');
 assertReviewed();status('Teil-PDFs werden erstellt …');
 let r=await api('/split',{marks,edits,searchable:$('exportMode').value==='ocr',profile:$('sizeProfile').value,dpi:Number($('ocrDpi').value),skip_existing:$('skipText').checked,ranges:$('splitRanges').value,...reviewPayload()});
 downloadBlob(await r.blob(),baseName+'-geteilt.zip');status('Teil-PDFs als ZIP erstellt.');
});
$('suggest').onclick=()=>run(async()=>{
 suggestions=await(await api('/suggestions',{edits})).json();$('suggestions').replaceChildren();
 suggestions.forEach((item,i)=>{let label=document.createElement('label'),check=document.createElement('input'),jump=document.createElement('button');label.className='candidate';check.type='checkbox';check.dataset.suggestion=String(i);label.append(check,document.createTextNode(` ${item.kind}: ${item.value} · Seite ${item.page+1} `));jump.textContent='Zeigen';jump.onclick=()=>run(async()=>{page=item.page;focusedRect=item.rects[0];await show()});label.append(jump);$('suggestions').append(label)});
 status(`${suggestions.length} Vorschläge gefunden. Treffer einzeln prüfen; nicht erkannte Angaben bleiben möglich.`);
});
$('adoptSuggestions').onclick=()=>{if(busy)return;let hits={};for(let input of $('suggestions').querySelectorAll('input:checked')){let s=suggestions[Number(input.dataset.suggestion)];(hits[s.page]??=[]).push(...s.rects);input.checked=false}applyHits(hits)};
$('shutdown').onclick=async()=>{if(busy){status('Zuerst die laufende Verarbeitung beenden.');return}await api('/shutdown',{});document.body.replaceChildren(Object.assign(document.createElement('p'),{textContent:'PDF-Tool beendet. Dieses Browserfenster kann geschlossen werden.'}))};
function resetEditorState(pages,name,size){count=pages;page=0;marks={};edits={};history=[];reviewed={};pagePlan=[];editSelection=null;activeBatchItem=null;searchVersion++;clearTimeout(searchTimer);searchPending=false;preview={};focusedRect=null;zoom=1;originalBytes=size;baseName=name.replace(/\.pdf$/i,'');$('name').textContent=name;$('term').value='';$('editor').hidden=true;renderEdits();renderResults({});$('ocrState').textContent='Für Scans zuerst OCR ausführen · Deutsch + Englisch'}
function queueFiles(files){
 if(busy)return;
 files=[...files];if(!files.length)return;
 if(batchQueue.length+files.length>20)throw Error('Maximal 20 PDFs pro Stapel.');
 if(batchQueue.reduce((n,e)=>n+e.file.size,0)+files.reduce((n,f)=>n+f.size,0)>500*1024*1024)throw Error('Maximal 500 MB pro Stapel.');
 for(let file of files){if(file.size>150*1024*1024||(!/\.pdf$/i.test(file.name)&&file.type!=='application/pdf'))throw Error('Nur PDFs bis 150 MB pro Datei.');}
 for(let file of files)batchQueue.push({id:String(++queueSequence),file,status:'Wartet',pages:0,marks:{},edits:{},approvals:{},suggestions:[],preparedTerms:null,report:null,error:''});
 $('batchPanel').open=true;renderBatch();$('batchProgress').textContent=`${batchQueue.length} PDFs im Stapel. OCR-Stapel starten oder mit Suchliste zuerst Treffer vorbereiten.`;
}
function handleFiles(files,asBatch=false){try{if(asBatch||files.length>1)queueFiles(files);else run(()=>loadFile(files[0]))}catch(e){status(e.message);$('batchProgress').textContent=e.message}}
$('file').onchange=()=>{let files=[...$('file').files];$('file').value='';handleFiles(files)};
$('batchFiles').onchange=()=>{handleFiles([...$('batchFiles').files],true);$('batchFiles').value=''};
window.addEventListener('drop',e=>{e.preventDefault();document.body.classList.remove('drop-active');if(busy)return;handleFiles([...e.dataTransfer.files],!!e.target.closest('#batchPanel'))});
// Replace the original one-file drop callback to avoid processing twice.
function batchOptions(){return {profile:$('batchProfile').value,dpi:Number($('batchDpi').value),skip_existing:$('batchSkip').checked,terms:[...new Set($('batchTerms').value.split('\n').map(t=>t.trim()).filter(Boolean))]}}
function batchPath(path,extra={}){return path+'?'+new URLSearchParams({session:batchSession,...extra})}
function renderBatch(){
 $('batchRows').replaceChildren();
 for(let entry of batchQueue){let row=document.createElement('tr'),r=entry.report||{},values=[entry.file.name,entry.error?`${entry.status}: ${entry.error}`:entry.status,entry.pages||'–',`${r.ocr_pages||0} / ${r.preserved_pages||0}`,(r.no_text_pages||[]).join(', ')||'–',r.output_bytes?`${(r.output_bytes/1024/1024).toFixed(2)} MB (${Math.abs(Math.round((1-r.output_bytes/entry.file.size)*100))} % ${r.output_bytes<=entry.file.size?'kleiner':'größer'})`:'–'];for(let value of values){let cell=document.createElement('td');cell.textContent=value;row.append(cell)}let action=document.createElement('td'),button=document.createElement('button');button.textContent='Prüfen / bearbeiten';button.disabled=busy;button.onclick=()=>run(()=>openBatchReview(entry));action.append(button);row.append(action);$('batchRows').append(row)}
 renderBatchSuggestions();
}
function renderBatchSuggestions(){
 $('batchSuggestions').replaceChildren();
 for(let entry of batchQueue)entry.suggestions.forEach((item,i)=>{let label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.dataset.file=entry.id;check.dataset.index=String(i);label.className='candidate';label.append(check,document.createTextNode(` ${entry.file.name} · Seite ${item.page+1} · ${item.kind}: ${item.value}`));$('batchSuggestions').append(label)});
}
$('batchAdopt').onclick=()=>{if(busy)return;for(let input of $('batchSuggestions').querySelectorAll('input:checked')){let entry=batchQueue.find(e=>e.id===input.dataset.file),s=entry.suggestions[Number(input.dataset.index)];for(let rect of s.rects)if(!(entry.marks[s.page]||[]).some(r=>JSON.stringify(r)===JSON.stringify(rect)))(entry.marks[s.page]??=[]).push(rect);entry.approvals={};entry.status='Prüfung nötig'}renderBatch();$('batchProgress').textContent='Ausgewählte Vorschläge übernommen. Betroffene Dateien vor Export prüfen.'};
async function openBatchReview(entry){
 await loadFile(entry.file);activeBatchItem=entry.id;marks=JSON.parse(JSON.stringify(entry.marks));edits=JSON.parse(JSON.stringify(entry.edits));reviewed={...entry.approvals};history=[];renderEdits();await show();status('Stapeldatei prüfen. Betroffene Seiten freigeben und „Änderungen für Stapel übernehmen“ wählen.');
}
$('batchSaveReview').onclick=()=>run(async()=>{
 if(editSelection)throw Error('Offene Textänderung zuerst übernehmen.');
 if(approvedPages().length!==changedPages().length)throw Error('Alle geänderten Seiten zuerst freigeben.');
 let entry=batchQueue.find(e=>e.id===activeBatchItem);if(!entry)throw Error('Stapeldatei nicht mehr vorhanden.');
 let source=await(await api('/source',{})).blob();entry.file=new File([source],entry.file.name,{type:'application/pdf'});entry.pages=count;entry.marks=JSON.parse(JSON.stringify(marks));entry.edits=JSON.parse(JSON.stringify(edits));entry.approvals={...reviewed};entry.status='Freigegeben';entry.error='';renderBatch();status('Freigegebene Änderungen in den Stapel übernommen.');
});
async function processBatch(mode,retryOnly=false){
 if(!batchQueue.length)throw Error('Zuerst PDFs zum Stapel hinzufügen.');
 const options=batchOptions(),termsKey=JSON.stringify(options.terms);
 let selected=batchQueue.filter(e=>retryOnly?e.status==='Fehler':mode==='analyse'||e.status!=='Fertig');
 if(mode==='export'&&options.terms.length)selected=selected.filter(e=>!(e.status==='Fehler'&&e.preparedTerms!==termsKey));
 if(!selected.length)throw Error('Keine ausstehenden Dateien. Für einen neuen Lauf „Alle neu verarbeiten“ wählen.');
 if(mode==='export')for(let e of selected){if(options.terms.length&&e.preparedTerms!==termsKey)throw Error('Gemeinsame Suchliste: zuerst Treffer für alle Dateien vorbereiten.');let dirty=[...new Set([...Object.keys(e.marks),...Object.keys(e.edits)])].filter(n=>(e.marks[n]||[]).length||(e.edits[n]||[]).length);if(dirty.some(n=>e.approvals[n]!==JSON.stringify([e.marks[n]||[],e.edits[n]||[]])))throw Error(`${e.file.name}: geänderte Seiten zuerst prüfen und für den Stapel übernehmen.`);}
 if(!batchSession)batchSession=(await(await api('/batch/reset',{options})).json()).session;
 else await api(batchPath('/batch/options'),options);
 batchRunning=true;batchStop=false;controls();
 try{
  for(let [position,entry] of selected.entries()){
   entry.error='';entry.status=mode==='analyse'?'Treffer werden gesucht':'OCR läuft';renderBatch();
   try{
    let meta=await(await api(batchPath('/batch/load',{id:entry.id,name:entry.file.name}),entry.file,true)).json();entry.pages=meta.pages;
    await api(batchPath('/batch/prepare'),{mode,marks:mode==='export'?entry.marks:{},edits:mode==='export'?entry.edits:{},reviewed_pages:Object.keys(entry.approvals).map(Number)});
    if(mode==='analyse'){entry.preparedTerms=null;entry.marks={};entry.edits={};entry.approvals={};entry.suggestions=[];}
    for(let n=0;n<meta.pages;n++){
     const started=Date.now(),update=()=>{$('batchProgress').textContent=`${position+1}/${selected.length}: ${entry.file.name}\nSeite ${n+1}/${meta.pages} · ${Math.floor((Date.now()-started)/1000)} s${batchStop?' · Stopp nach dieser Datei vorgemerkt':''}`};update();let timer=setInterval(update,1000),result;
     try{result=await(await api(batchPath('/batch/step'),{})).json()}finally{clearInterval(timer)}
     if(mode==='analyse'){if(result.marks.length)entry.marks[n]=result.marks;entry.suggestions.push(...result.suggestions.map(s=>({...s,page:n})));}
    }
    entry.report=await(await api(batchPath('/batch/finish'),{})).json();entry.status=mode==='analyse'?'Vorbereitet':'Fertig';if(mode==='analyse')entry.preparedTerms=termsKey;
   }catch(e){entry.status='Fehler';entry.error=e.message;try{await api(batchPath('/batch/fail'),{id:entry.id,error:e.message});let records=await(await api(batchPath('/batch/report'),{})).json();entry.report=records.find(r=>r.id===entry.id)||null}catch{}}
   renderBatch();if(batchStop)break;
  }
 }finally{batchRunning=false;controls();}
 $('batchProgress').textContent=`${batchStop?'Nach aktueller Datei gestoppt. ':''}${batchQueue.filter(e=>e.status==='Fertig').length} fertig · ${batchQueue.filter(e=>e.status==='Fehler').length} Fehler. ${mode==='analyse'?'Dateien mit Treffern prüfen und freigeben.':'Ergebnisse können als ZIP geladen werden.'}`;
}
$('batchPrepare').onclick=()=>run(()=>processBatch('analyse'));
$('batchRun').onclick=()=>run(()=>processBatch('export'));
$('batchRetry').onclick=()=>run(()=>processBatch('export',true));
$('batchAgain').onclick=()=>run(async()=>{for(let entry of batchQueue){entry.status='Wartet';entry.error=''}await processBatch('export')});
$('batchStop').onclick=()=>{batchStop=true;$('batchProgress').textContent+='\nStopp nach aktueller Datei vorgemerkt.'};
$('batchZip').onclick=()=>run(async()=>{if(!batchSession)throw Error('Noch keine Stapelergebnisse.');downloadBlob(await(await api(batchPath('/batch/zip'),{})).blob(),'PDF-Ergebnisse.zip')});
$('batchClear').onclick=()=>run(async()=>{await api('/batch/reset',{options:batchOptions()});batchSession=null;batchQueue=[];activeBatchItem=null;renderBatch();$('batchProgress').textContent='Stapel und temporäre Ausgaben gelöscht.'});
$('mergeQueue').onclick=()=>run(async()=>{
 if(batchQueue.length<2)throw Error('Zum Zusammenführen mindestens zwei Dateien hinzufügen.');
 await api('/merge/start',{});for(let [i,entry] of batchQueue.entries()){$('batchProgress').textContent=`Zusammenführen ${i+1}/${batchQueue.length}: ${entry.file.name}`;await api('/merge/add',entry.file,true)}
 let result=await(await api('/merge/finish',{})).json();resetEditorState(result.pages,'Zusammengefuehrt.pdf',batchQueue.reduce((n,e)=>n+e.file.size,0));await show();status('Dateien in Listenreihenfolge zusammengeführt. Einzeldatei-Markierungen werden dabei nicht übernommen; die gemeinsame PDF jetzt prüfen / bearbeiten und speichern.');
});
function renderPresets(){let selected=$('preset').value;$('preset').replaceChildren(new Option('Vorlage wählen',''));for(let [i,preset] of [...builtinPresets,...savedPresets].entries())$('preset').append(new Option(preset.name,String(i)));$('preset').value=selected}
$('loadPreset').onclick=()=>{if(busy)return;let preset=[...builtinPresets,...savedPresets][Number($('preset').value)];if($('preset').value===''||!preset)return;$('sizeProfile').value=$('batchProfile').value=preset.profile;$('ocrDpi').value=$('batchDpi').value=String(preset.dpi);$('skipText').checked=$('batchSkip').checked=preset.skip_existing;$('exportMode').value=preset.export_mode;$('term').value=$('batchTerms').value=preset.terms.join('\n');if(count)liveSearch();controls();status(`Vorlage „${preset.name}“ angewendet.`)};
$('savePreset').onclick=()=>run(async()=>{let name=$('presetName').value.trim();if(!name)throw Error('Vorlagenname eingeben.');let options=batchOptions();options.profile=$('sizeProfile').value;options.dpi=Number($('ocrDpi').value);options.skip_existing=$('skipText').checked;options.terms=$('saveTerms').checked?(options.terms.length?options.terms:searchTerms()):[];let preset={...options,name,export_mode:$('exportMode').value};savedPresets=await(await api('/settings/save',{presets:[...savedPresets.filter(p=>p.name!==name),preset]})).json().then(r=>r.presets);renderPresets();status('Vorlage lokal gespeichert. Suchbegriffe nur bei aktivierter Option gespeichert.');});
$('deletePreset').onclick=()=>run(async()=>{let index=Number($('preset').value)-builtinPresets.length;if($('preset').value===''||index<0)throw Error('Eine eigene gespeicherte Vorlage auswählen.');let next=savedPresets.filter((_,i)=>i!==index);savedPresets=(await(await api('/settings/save',{presets:next})).json()).presets;renderPresets();status('Eigene Vorlage gelöscht.');});
api('/settings/get',{}).then(r=>r.json()).then(r=>{savedPresets=r.presets;renderPresets()}).catch(e=>status(`Vorlagen nicht geladen: ${e.message}`));
controls();

$('sizeProfile').addEventListener('change',()=>controls());
