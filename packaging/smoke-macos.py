"""Exercise the actual frozen macOS binary, including bundled OCR models."""
import json
import re
import subprocess
import time
import urllib.request
import pymupdf as fitz

process = subprocess.Popen(['dist/PDF-Tool.app/Contents/MacOS/PDF-Tool','--no-browser','--port','18765'])
base='http://127.0.0.1:18765'
try:
    for attempt in range(60):
        if process.poll() is not None:
            raise RuntimeError('macOS app exited during startup')
        try:
            with urllib.request.urlopen(base,timeout=2) as response:
                html=response.read().decode()
            break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError('macOS app did not become ready')
    token=re.search(r"token='([^']+)'",html)[1]
    def post(path,body,raw=False):
        request=urllib.request.Request(base+path,data=body if raw else json.dumps(body).encode(),headers={'X-Token':token})
        with urllib.request.urlopen(request,timeout=120) as response:
            return response.read()
    with fitz.open() as doc:
        p=doc.new_page(width=400,height=240)
        p.insert_text((40,80),'SECRET',fontsize=20)
        p.insert_text((40,140),'Alice Example',fontsize=20)
        png=p.get_pixmap(dpi=200).tobytes('png')
        with fitz.open() as scan:
            p=scan.new_page(width=400,height=240);p.insert_image(p.rect,stream=png)
            post('/load',scan.tobytes(),True)
    assert json.loads(post('/ocr',{'page':0}))['characters']>0
    marks=json.loads(post('/search',{'term':'SECRET'}))
    assert marks['0']
    exported=post('/export',{'marks':marks,'searchable':True,'profile':'lossless'})
    with fitz.open(stream=exported,filetype='pdf') as doc:
        text=doc[0].get_text().casefold()
        assert 'secret' not in text and 'alice' in text
    post('/shutdown',{})
    process.wait(timeout=15)
    assert process.returncode==0
    print('Frozen macOS app passed startup, OCR, redaction, lossless OCR export and shutdown.')
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=15)
