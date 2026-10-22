import io
import json
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from PIL import Image
import pymupdf as fitz
import app
import workflows as wf
import test_app as base


class WorkflowTests(unittest.TestCase):
    post = base.ToolTests.post
    fixture = base.ToolTests.fixture

    @classmethod
    def setUpClass(cls):
        base.ToolTests.setUpClass.__func__(cls)
        cls.temp = tempfile.TemporaryDirectory()
        cls.settings = wf.SETTINGS_PATH
        wf.SETTINGS_PATH = Path(cls.temp.name)/'config/settings.json'

    @classmethod
    def tearDownClass(cls):
        base.ToolTests.tearDownClass.__func__(cls)
        app.BATCH.close()
        wf.SETTINGS_PATH = cls.settings
        cls.temp.cleanup()

    def new_batch(self, **options):
        return json.loads(self.post('/batch/reset',{'options':options}))['session']

    def batch(self, session, route, body=None, **query):
        from urllib.parse import urlencode
        return self.post('/batch/'+route+'?'+urlencode({'session':session,**query}),{} if body is None else body,raw=isinstance(body,bytes))

    def process(self, session, key, raw, name='Vertrag.pdf', mode='export', marks=None, reviewed=None):
        meta=json.loads(self.batch(session,'load',raw,id=key,name=name))
        self.batch(session,'prepare',{'mode':mode,'marks':marks or {},'reviewed_pages':reviewed or []})
        pages=[json.loads(self.batch(session,'step')) for _ in range(meta['pages'])]
        result=json.loads(self.batch(session,'finish'))
        return result,pages

    def test_twenty_files_and_unique_safe_zip_names(self):
        session=self.new_batch(profile='lossless',skip_existing=True)
        for n in range(20):
            report,_=self.process(session,str(n),self.fixture(),name='../Vertrag.pdf')
            self.assertEqual(report['status'],'Fertig')
            self.assertEqual(report['preserved_pages'],1)
            self.assertEqual(report['ocr_pages'],0)
        with zipfile.ZipFile(io.BytesIO(self.batch(session,'zip'))) as z:
            pdfs=[n for n in z.namelist() if n.endswith('.pdf')]
            self.assertEqual(len(pdfs),20)
            self.assertEqual(len(set(pdfs)),20)
            self.assertFalse(any('/' in n or '\\' in n for n in pdfs))
            self.assertIn('Ergebnisbericht.csv',z.namelist())
            self.assertEqual(len(json.loads(z.read('Ergebnisbericht.json'))),20)
            with fitz.open(stream=z.read(pdfs[0]),filetype='pdf') as doc:
                self.assertIn('SECRET',doc[0].get_text())

    def test_failed_file_does_not_block_others_and_retry(self):
        session=self.new_batch()
        with self.assertRaises(urllib.error.HTTPError):
            self.batch(session,'load',b'broken',id='bad',name='kaputt.pdf')
        self.process(session,'good',self.fixture())
        records=json.loads(self.batch(session,'report'))
        self.assertEqual({r['status'] for r in records},{'Fehler','Fertig'})
        self.process(session,'bad',self.fixture(),name='korrigiert.pdf')
        self.assertTrue(all(r['status']=='Fertig' for r in json.loads(self.batch(session,'report'))))
        old_root=app.BATCH.root
        self.new_batch()
        self.assertFalse(old_root.exists())

    def test_scanned_batch_and_redaction_review(self):
        session=self.new_batch(profile='lossless',skip_existing=True,terms=['SECRET'])
        report,pages=self.process(session,'scan',self.fixture(scan=True),mode='analyse')
        self.assertEqual(report['ocr_pages'],1)
        marks={'0':pages[0]['marks']}
        self.assertTrue(marks['0'])
        self.batch(session,'load',self.fixture(scan=True),id='scan',name='Scan.pdf')
        with self.assertRaises(urllib.error.HTTPError):
            self.batch(session,'prepare',{'mode':'export','marks':marks,'reviewed_pages':[]})
        self.batch(session,'prepare',{'mode':'export','marks':marks,'reviewed_pages':[0]})
        self.batch(session,'step');self.batch(session,'finish')
        with zipfile.ZipFile(io.BytesIO(self.batch(session,'zip'))) as archive:
            with fitz.open(stream=archive.read('Scan-ocr.pdf'),filetype='pdf') as doc:
                self.assertNotIn('secret',doc[0].get_text().casefold())
                self.assertIn('alice',doc[0].get_text().casefold())

    def test_page_plan_rotates_state_and_undo(self):
        with fitz.open() as doc:
            for n in range(3):
                p=doc.new_page(width=400,height=240);p.insert_text((40,80),f'PAGE {n+1}')
            self.post('/load',doc.tobytes(),True)
        marks={'0':[[.1,.2,.3,.4]]}
        edits={'0':[{'rect':[.5,.5,.9,.9],'text':'Neu','font_size':12}]}
        result=json.loads(self.post('/pages',{'plan':[{'page':2},{'page':0,'rotation':90}],'marks':marks,'edits':edits,'page':1}))
        self.assertEqual(result['pages'],2)
        self.assertEqual(result['marks']['1'],[wf.rotate_rect(marks['0'][0],90)])
        self.assertEqual(result['edits']['1'][0]['rotation'],90)
        self.assertTrue(self.post('/page',{'page':1,'edits':result['edits']}).startswith(b'\x89PNG'))
        self.assertIn('PAGE 3',app.DOCUMENT[0].get_text())
        restored=json.loads(self.post('/pages/undo',{'id':result['undo']}))
        self.assertEqual(restored['pages'],3)
        self.assertEqual(restored['marks'],marks)
        self.assertEqual(restored['edits'],edits)

    def test_merge_split_and_ranges(self):
        self.post('/merge/start',{})
        self.post('/merge/add',self.fixture(),True)
        self.post('/merge/add',self.fixture(),True)
        self.assertEqual(json.loads(self.post('/merge/finish',{}))['pages'],2)
        data=self.post('/split',{'ranges':'2;1','profile':'lossless','searchable':True})
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(len(archive.namelist()),2)
            with fitz.open(stream=archive.read('Teil-001.pdf'),filetype='pdf') as doc:
                self.assertEqual(len(doc),1)
                self.assertIn('SECRET',doc[0].get_text())
        for ranges in ('1;1','3','2-1','x'):
            with self.subTest(ranges=ranges),self.assertRaises(urllib.error.HTTPError):
                self.post('/split',{'ranges':ranges})

    def test_review_enforcement_and_preferences(self):
        self.post('/load',self.fixture(),True)
        marks=json.loads(self.post('/search',{'term':'SECRET'}))
        with self.assertRaises(urllib.error.HTTPError):
            self.post('/export',{'marks':marks,'require_review':True,'reviewed_pages':[]})
        self.assertTrue(self.post('/export',{'marks':marks,'require_review':True,'reviewed_pages':[0]}).startswith(b'%PDF'))
        presets=[{'name':'Verträge','profile':'lossless','dpi':200,'skip_existing':True,'terms':['Müller'],'export_mode':'ocr'}]
        self.post('/settings/save',{'presets':presets})
        self.assertEqual(json.loads(self.post('/settings/get',{}))['presets'],presets)
        self.post('/settings/save',{'presets':[]})
        self.assertEqual(json.loads(self.post('/settings/get',{}))['presets'],[])

    def test_sensitive_suggestions_are_not_applied(self):
        with fitz.open() as doc:
            p=doc.new_page()
            for n,line in enumerate(['Kontakt test@example.de','IBAN DE89 3704 0044 0532 0130 00','Telefon +49 30 12345678']):
                p.insert_text((40,60+n*40),line,fontsize=14)
            self.post('/load',doc.tobytes(),True)
        result=json.loads(self.post('/suggestions',{}))
        self.assertEqual({r['kind'] for r in result},{'E-Mail','IBAN','Telefon'})
        self.assertTrue(all(r['page']==0 and r['rects'] for r in result))
        self.assertIn('test@example.de',app.DOCUMENT[0].get_text())

    def test_lossless_preserves_logo_pixels_and_vectors(self):
        logo=Image.new('RGB',(800,400),(35,115,175))
        buf=io.BytesIO();logo.save(buf,format='JPEG',quality=96)
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=240)
            p.insert_image(fitz.Rect(200,120,380,210),stream=buf.getvalue())
            p.draw_circle((280,60),20,color=(1,0,0),fill=(0,1,0))
            p.insert_text((30,50),'SECRET',fontsize=20)
            raw=doc.tobytes()
            original=doc.extract_image(p.get_images()[0][0])['image']
            drawings=p.get_drawings()
        self.post('/load',raw,True)
        data=self.post('/export',{'marks':{},'profile':'lossless','searchable':True})
        with fitz.open(stream=data,filetype='pdf') as result:
            self.assertEqual(result.extract_image(result[0].get_images()[0][0])['image'],original)
            self.assertEqual(result[0].get_drawings(),drawings)
        marks=json.loads(self.post('/search',{'term':'SECRET'}))
        data=self.post('/export',{'marks':marks,'profile':'lossless','searchable':True})
        with fitz.open(stream=data,filetype='pdf') as result:
            self.assertNotIn('secret',result[0].get_text().casefold())
            self.assertEqual(result.extract_image(result[0].get_images()[0][0])['image'],original)
            self.assertTrue(result[0].get_drawings())

    def test_force_ocr_on_mixed_page_keeps_native_text_once(self):
        with fitz.open() as source:
            p=source.new_page(width=400,height=240)
            p.insert_text((40,80),'SCANNED NAME',fontsize=20)
            png=p.get_pixmap(dpi=200).tobytes('png')
        with fitz.open() as source:
            p=source.new_page(width=400,height=300)
            p.insert_image(fitz.Rect(0,60,400,300),stream=png)
            p.insert_text((40,40),'Native header',fontsize=18)
            self.post('/load',source.tobytes(),True)
        data=self.post('/export',{'marks':{},'profile':'lossless','searchable':True,'skip_existing':False})
        with fitz.open(stream=data,filetype='pdf') as result:
            text=result[0].get_text().casefold()
            self.assertIn('scanned name',text)
            self.assertEqual(text.count('native header'),1)

    def test_lossless_scan_keeps_original_image_stream(self):
        raw=self.fixture(scan=True)
        with fitz.open(stream=raw,filetype='pdf') as doc:
            image=doc.extract_image(doc[0].get_images()[0][0])['image']
        self.post('/load',raw,True)
        data=self.post('/export',{'marks':{},'profile':'lossless','searchable':True})
        with fitz.open(stream=data,filetype='pdf') as doc:
            self.assertIn('SECRET',doc[0].get_text())
            self.assertEqual(doc.extract_image(doc[0].get_images()[0][0])['image'],image)
