// Run against a separate test server: node tests/browser.cjs URL fixture.pdf
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const {execFileSync} = require('node:child_process');
(async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'pdf-tool-test-'));
 const fixture=process.argv[3]||path.join(temp,'fixture.pdf');
 if(!process.argv[3])execFileSync(path.join(__dirname,'../.venv/bin/python'),['-c',"import pymupdf as f,sys; d=f.open(); [(lambda p:p.insert_text((40,80),'SECRET Alice Example',fontsize=20))(d.new_page(width=400,height=240)) for _ in range(2)]; d.save(sys.argv[1]); d.close()",fixture]);
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.argv[2]||'http://127.0.0.1:8766');
  await page.setInputFiles('#file',fixture);
  await page.waitForFunction(()=>document.querySelector('#pageLabel').textContent.includes('Seite 1 / 2')&&!document.querySelector('#search').disabled);
  await page.selectOption('#ocrDpi','150');
  await page.selectOption('#ocrScope','current');
  await page.click('#ocr');
  await page.waitForFunction(()=>document.querySelector('#ocrState').textContent.includes('OCR fertig · 1 Seiten')&&!document.querySelector('#term').disabled);
  // Reload to test native-text result counts independently of OCR rectangles.
  await page.setInputFiles('#file',fixture);
  await page.waitForFunction(()=>document.querySelector('#ocrState').textContent.includes('Für Scans zuerst')&&!document.querySelector('#search').disabled);
  await page.fill('#term','Alice\nSECRET\nAlice');
  await page.waitForFunction(()=>document.querySelectorAll('#results button').length===4);
  assert.match(await page.locator('#resultsInfo').textContent(),/4 Fundstellen auf 2 Seiten/);
  await page.locator('#results button').nth(2).click();
  await page.waitForFunction(()=>document.querySelector('#pageLabel').textContent.includes('Seite 2 / 2')&&!document.querySelector('#zoomIn').disabled);
  const before=await page.locator('#canvas').evaluate(e=>({display:e.getBoundingClientRect().width,pixels:e.width}));
  await page.click('#zoomIn');
  await page.waitForFunction(()=>document.querySelector('#zoomLabel').textContent==='125 %'&&!document.querySelector('#zoomIn').disabled);
  const after=await page.locator('#canvas').evaluate(e=>({display:e.getBoundingClientRect().width,pixels:e.width}));
  assert(after.display>before.display);assert(after.pixels>before.pixels);
  await page.click('#zoomFit');
  await page.waitForFunction(()=>document.querySelector('#zoomLabel').textContent==='100 %'&&!document.querySelector('#zoomFit').disabled);
  await page.click('#export');
  assert.match(await page.locator('#status').textContent(),/Gelbe Treffer/);
  await page.click('#search');
  await page.waitForFunction(()=>document.querySelector('#pageLabel').textContent.includes('4 Markierungen'));
  await page.click('#undo');
  await page.waitForFunction(()=>document.querySelector('#pageLabel').textContent.includes('0 Markierungen'));
  // Whole-word selection still works after zoom and page navigation.
  await page.fill('#term','');
  await page.waitForFunction(()=>document.querySelectorAll('#results button').length===0);
  await page.selectOption('#mode','word');
  const word=await page.evaluate(async()=>{let r=await fetch('/words',{method:'POST',headers:{'X-Token':token},body:JSON.stringify({page:1})});return(await r.json()).find(w=>w.text==='Alice')});
  const canvas=await page.locator('#canvas').boundingBox();
  await page.mouse.click(canvas.x+(word.rect[0]+word.rect[2])/2*canvas.width,canvas.y+(word.rect[1]+word.rect[3])/2*canvas.height);
  await page.waitForFunction(()=>document.querySelector('#pageLabel').textContent.includes('2 Markierungen'));
  const downloadPromise=page.waitForEvent('download');await page.click('#export');const download=await downloadPromise;
  assert(download.suggestedFilename().endsWith('-geschwaerzt-ocr.pdf'));
  const exported=path.join(temp,'redacted-ocr.pdf');await download.saveAs(exported);
  execFileSync(path.join(__dirname,'../.venv/bin/python'),['-c',"import pymupdf as f,sys; d=f.open(sys.argv[1]); text=' '.join(p.get_text() for p in d).casefold(); assert 'alice' not in text; assert 'secret' in text and 'example' in text",exported]);
  await page.selectOption('#exportMode','image');
  const imageDownloadPromise=page.waitForEvent('download');await page.click('#export');const imageDownload=await imageDownloadPromise;
  assert(imageDownload.suggestedFilename().endsWith('-geschwaerzt.pdf'));
  const imageExport=path.join(temp,'redacted-image.pdf');await imageDownload.saveAs(imageExport);
  execFileSync(path.join(__dirname,'../.venv/bin/python'),['-c',"import pymupdf as f,sys; d=f.open(sys.argv[1]); assert all(not p.get_text().strip() for p in d)",imageExport]);
  await page.click('#clear');
  await page.waitForFunction(()=>document.querySelector('#pageLabel').textContent==='Keine Seiten');
  assert.equal(await page.locator('#results button').count(),0);
  // Drop a PDF instead of using the picker.
  const bytes=require('node:fs').readFileSync(fixture);
  const dt=await page.evaluateHandle(data=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(data)],'drop.pdf',{type:'application/pdf'}));return dt},Array.from(bytes));
  await page.dispatchEvent('body','drop',{dataTransfer:dt});
  await page.waitForFunction(()=>document.querySelector('#pageLabel').textContent.includes('Seite 1 / 2'));
  assert.equal(await page.locator('#name').textContent(),'drop.pdf');
  assert.deepEqual(errors,[]);
  console.log('Browser checks passed: multiple terms, deduplication, jump, zoom, export guard, undo, word click, download, clear, drag-and-drop.');
 } finally {await browser.close();fs.rmSync(temp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
