const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {execFileSync}=require('node:child_process');
(async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'pdf-tool-workflows-'));
 const python=path.join(__dirname,'../.venv/bin/python');
 execFileSync(python,['-c',`import pymupdf as f,sys,pathlib
root=pathlib.Path(sys.argv[1])
for i in range(3):
 d=f.open();p=d.new_page(width=400,height=300)
 for n,text in enumerate(['SECRET','Alice Example','test@example.de','DE89 3704 0044 0532 0130 00','+49 30 12345678']):p.insert_text((35,50+n*40),text,fontsize=16)
 d.save(root/f'Vertrag-{i}.pdf');d.close()
(root/'kaputt.pdf').write_bytes(b'broken')`,temp]);
 const files=[0,1,2].map(i=>path.join(temp,`Vertrag-${i}.pdf`)),bad=path.join(temp,'kaputt.pdf');
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1050}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.argv[2]||'http://127.0.0.1:8792');
  // A transient page request failure and a corrupt PDF must not block others.
  let failOnce=true;
  await page.route('**/batch/step?*',async route=>{if(failOnce){failOnce=false;await route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Simulierter vorübergehender Fehler'})})}else await route.continue()});
  await page.setInputFiles('#file',[files[0],files[1],bad]);
  await page.click('#batchRun');
  await page.waitForFunction(()=>!busy&&batchQueue.filter(e=>e.status==='Fehler').length===2);
  assert.equal(await page.locator('#batchRows tr').count(),3);
  await page.unroute('**/batch/step?*');
  await page.click('#batchRetry');
  await page.waitForFunction(()=>!busy&&batchQueue.filter(e=>e.status==='Fertig').length===2);
  let download=page.waitForEvent('download');await page.click('#batchZip');await(await download).saveAs(path.join(temp,'results.zip'));
  execFileSync(python,['-c',"import zipfile,json,sys;z=zipfile.ZipFile(sys.argv[1]);assert len([n for n in z.namelist() if n.endswith('.pdf')])==2;r=json.loads(z.read('Ergebnisbericht.json'));assert sum(x['status']=='Fehler' for x in r)==1",path.join(temp,'results.zip')]);
  // Stop after one whole file, then resume the waiting files.
  await page.click('#batchClear');await page.setInputFiles('#batchFiles',files);
  let releaseFirst,seenFirst;const firstSeen=new Promise(r=>seenFirst=r),release=new Promise(r=>releaseFirst=r);
  let intercept=true;await page.route('**/batch/step?*',async route=>{if(intercept){intercept=false;seenFirst();await release}await route.continue()});
  await page.click('#batchRun');await firstSeen;await page.click('#batchStop');releaseFirst();
  await page.waitForFunction(()=>!busy&&batchQueue.filter(e=>e.status==='Fertig').length===1);
  assert.equal(await page.evaluate(()=>batchQueue.filter(e=>e.status==='Wartet').length),2);
  await page.unroute('**/batch/step?*');await page.click('#batchRun');
  await page.waitForFunction(()=>!busy&&batchQueue.every(e=>e.status==='Fertig'));
  // Shared terms and optional pattern suggestions require per-file review.
  await page.click('#batchClear');await page.setInputFiles('#batchFiles',files.slice(0,2));
  await page.fill('#batchTerms','SECRET');await page.click('#batchPrepare');
  await page.waitForFunction(()=>!busy&&batchQueue.every(e=>e.status==='Vorbereitet'));
  assert((await page.locator('#batchSuggestions input').count())>=6);
  await page.locator('#batchSuggestions').evaluate(e=>e.closest('details').open=true);
  await page.locator('#batchSuggestions').locator('input').first().check();await page.click('#batchAdopt');
  await page.click('#batchRun');await page.waitForFunction(()=>!busy&&document.querySelector('#status').textContent.includes('prüfen'));
  for(let i=0;i<2;i++){
   await page.locator('#batchRows tr').nth(i).getByRole('button').click();
   await page.waitForFunction(()=>!busy&&activeBatchItem!==null);
   await page.click('#approvePage');await page.click('#batchSaveReview');
   await page.waitForFunction(()=>!busy);
  }
  await page.click('#batchRun');await page.waitForFunction(()=>!busy&&batchQueue.every(e=>e.status==='Fertig'));
  download=page.waitForEvent('download');await page.click('#batchZip');await(await download).saveAs(path.join(temp,'redacted.zip'));
  execFileSync(python,['-c',"import zipfile,pymupdf as f,sys;z=zipfile.ZipFile(sys.argv[1]); names=[n for n in z.namelist() if n.endswith('.pdf')];assert len(names)==2; docs=[f.open(stream=z.read(n),filetype='pdf') for n in names];assert all('secret' not in ''.join(p.get_text() for p in d).casefold() for d in docs)",path.join(temp,'redacted.zip')]);
  // Merge originals, reorder/rotate/remove, undo, then split.
  await page.click('#mergeQueue');await page.waitForFunction(()=>!busy&&count===2);
  await page.locator('#pagePlan').evaluate(e=>e.closest('details').open=true);
  await page.locator('#pagePlan>div').first().getByRole('button',{name:'↓',exact:true}).click();
  await page.locator('#pagePlan>div').first().getByRole('button',{name:'↷',exact:true}).click();
  await page.locator('#pagePlan>div').last().getByRole('button',{name:'Entfernen',exact:true}).click();
  await page.click('#applyPages');await page.waitForFunction(()=>!busy&&count===1);
  await page.click('#undo');await page.waitForFunction(()=>!busy&&count===2);
  await page.selectOption('#sizeProfile','lossless');
  await page.locator('#split').evaluate(e=>e.closest('details').open=true);
  await page.fill('#splitRanges','1;2');download=page.waitForEvent('download');await page.click('#split');await(await download).saveAs(path.join(temp,'split.zip'));
  execFileSync(python,['-c',"import zipfile,sys;assert len(zipfile.ZipFile(sys.argv[1]).namelist())==2",path.join(temp,'split.zip')]);
  // Real suggestion controls do not select anything until the user chooses.
  await page.locator('#suggest').evaluate(e=>e.closest('details').open=true);await page.click('#suggest');
  await page.waitForFunction(()=>!busy&&document.querySelectorAll('#suggestions input').length>=6);
  assert.equal(await page.locator('#suggestions input:checked').count(),0);
  await page.locator('#suggestions input').first().check();await page.click('#adoptSuggestions');
  assert((await page.evaluate(()=>changedPages().length))>0);
  // Save and reload an explicit local preset, including the chosen term list.
  await page.locator('#presetName').evaluate(e=>e.closest('details').open=true);
  await page.fill('#presetName','Browser-Test');await page.check('#saveTerms');await page.click('#savePreset');
  await page.waitForFunction(()=>!busy&&savedPresets.some(p=>p.name==='Browser-Test'));
  await page.reload();await page.waitForFunction(()=>savedPresets.some(p=>p.name==='Browser-Test'));
  await page.locator('#preset').evaluate(e=>e.closest('details').open=true);
  await page.selectOption('#preset',{label:'Browser-Test'});await page.click('#loadPreset');
  assert.equal(await page.locator('#batchTerms').inputValue(),'SECRET');
  await page.click('#deletePreset');await page.waitForFunction(()=>!busy&&!savedPresets.some(p=>p.name==='Browser-Test'));
  assert.deepEqual(errors,[]);
  console.log('Workflow browser checks passed: multi-file queue, partial errors, retry, ZIP report, stop/resume, shared terms, pattern suggestions, mandatory review, native lossless export, merge, page plan/undo, split and persisted presets.');
 }finally{await browser.close();fs.rmSync(temp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
