import io
import json
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import tempfile
import shutil
from pathlib import Path
from http.server import HTTPServer
import pymupdf as fitz
from PIL import Image
import app


class ToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        if app.DOCUMENT:
            app.DOCUMENT.close()
            app.DOCUMENT = None

    def post(self, path, body, raw=False, token=app.TOKEN):
        data = body if raw else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, headers={'X-Token': token})
        with urllib.request.urlopen(req) as response:
            return response.read()

    def fixture(self, scan=False, rotation=0):
        with fitz.open() as doc:
            page = doc.new_page(width=400, height=240)
            page.insert_text((40, 80), 'SECRET', fontsize=20)
            page.insert_text((40, 140), 'Alice Example', fontsize=20)
            if scan:
                png = page.get_pixmap(dpi=300).tobytes('png')
                with fitz.open() as scanned:
                    p = scanned.new_page(width=400, height=240)
                    p.insert_image(p.rect, stream=png)
                    p.set_rotation(rotation)
                    return scanned.tobytes()
            doc.set_metadata({'author': 'Sensitive author'})
            doc.embfile_add('private.txt', b'SECRET ATTACHMENT')
            page.set_rotation(rotation)
            return doc.tobytes()

    def test_search_redact_export(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                self.assertEqual(json.loads(self.post('/load', self.fixture(rotation=rotation), True))['pages'], 1)
                hits = json.loads(self.post('/search', {'term': 'SECRET'}))
                self.assertEqual(len(hits['0']), 1)
                preview = self.post('/page', {'page': 0})
                self.assertTrue(preview.startswith(b'\x89PNG'))
                data = self.post('/export', {'marks': hits})
                with fitz.open(stream=data, filetype='pdf') as result:
                    self.assertEqual(len(result), 1)
                    self.assertEqual(result[0].get_text(), '')
                    self.assertEqual(result.embfile_count(), 0)
                    self.assertFalse(result.metadata.get('author'))
                    pix = result[0].get_pixmap(dpi=200)
                    image = Image.open(io.BytesIO(pix.tobytes('png')))
                    x0, y0, x1, y1 = hits['0'][0]
                    self.assertEqual(image.getpixel((int((x0+x1)/2*image.width), int((y0+y1)/2*image.height)))[:3], (0, 0, 0))

    def test_scan_ocr(self):
        for rotation in (0, 90):
            with self.subTest(rotation=rotation):
                self.post('/load', self.fixture(scan=True, rotation=rotation), True)
                self.assertEqual(json.loads(self.post('/search', {'term': 'SECRET'})), {})
                self.assertGreater(json.loads(self.post('/ocr', {'page': 0}))['characters'], 0)
                hits = json.loads(self.post('/search', {'term': 'SECRET'}))
                self.assertEqual(len(hits['0']), 1)
                self.assertTrue(all(0 <= v <= 1 for v in hits['0'][0]))
                self.post('/clear', {})
                self.assertEqual(app.OCR_CACHE, {})
                self.assertIsNone(app.DOCUMENT)

    def test_invalid_requests(self):
        self.post('/load', self.fixture(), True)
        for path, body, token in [('/page', {'page': 0}, 'wrong'), ('/page', {'page': -1}, app.TOKEN), ('/export', {'marks': {'99': [[0, 0, 1, 1]]}}, app.TOKEN), ('/export', {'marks': {'0': [[0.5, 0, 0.1, 1]]}}, app.TOKEN)]:
            with self.subTest(path=path, body=body), self.assertRaises(urllib.error.HTTPError):
                self.post(path, body, token=token)
        with urllib.request.urlopen(self.url) as response:
            self.assertIn(app.TOKEN.encode(), response.read())
            self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_word_selection_all_pages(self):
        with fitz.open() as doc:
            for rotation in (0, 90, 180, 270):
                page = doc.new_page(width=400, height=240)
                page.insert_text((40, 80), 'Alice ALICE Alice, Malice', fontsize=18)
                page.set_rotation(rotation)
            self.post('/load', doc.tobytes(), True)
        hits = json.loads(self.post('/search', {'term': 'Alice,', 'whole_word': True}))
        self.assertEqual(set(hits), {'0', '1', '2', '3'})
        for index in range(4):
            words = json.loads(self.post('/words', {'page': index}))
            self.assertEqual(len(hits[str(index)]), 3)
            self.assertEqual(words[0]['text'], 'Alice')
            self.assertEqual(words[0]['rect'], hits[str(index)][0])
            self.assertTrue(all(0 <= v <= 1 for w in words for v in w['rect']))

    def test_ocr_word_positions(self):
        self.post('/load', self.fixture(scan=True, rotation=90), True)
        self.assertEqual(json.loads(self.post('/words', {'page': 0})), [])
        self.post('/ocr', {'page': 0})
        words = json.loads(self.post('/words', {'page': 0}))
        word = next(w for w in words if w['text'] == 'SECRET')
        hits = json.loads(self.post('/search', {'term': word['text'], 'whole_word': True}))
        self.assertIn(word['rect'], hits['0'])

    def test_zoom_resolution_and_validation(self):
        self.post('/load', self.fixture(), True)
        sizes = []
        for zoom in (.5, 1, 3):
            data = self.post('/page', {'page': 0, 'zoom': zoom})
            sizes.append(Image.open(io.BytesIO(data)).size)
        self.assertLess(sizes[0][0], sizes[1][0])
        self.assertLess(sizes[1][0], sizes[2][0])
        for invalid in (0, 4, True, '2', float('nan')):
            with self.subTest(zoom=invalid), self.assertRaises(urllib.error.HTTPError):
                self.post('/page', {'page': 0, 'zoom': invalid})

    def test_ocr_quality_selection(self):
        self.post('/load', self.fixture(scan=True), True)
        for dpi in (150, 200, 300):
            with self.subTest(dpi=dpi):
                result = json.loads(self.post('/ocr', {'page': 0, 'dpi': dpi}))
                self.assertGreater(result['characters'], 0)
                self.assertEqual(result['dpi'], dpi)
                self.assertEqual(app.OCR_CACHE[0][2], dpi)
        for dpi in (0, 600, '200', True):
            with self.subTest(invalid=dpi), self.assertRaises(urllib.error.HTTPError):
                self.post('/ocr', {'page': 0, 'dpi': dpi})

    def test_relative_models_in_unicode_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Vermögens verwaltung'
            shutil.copytree(Path(app.__file__).parent / 'tessdata', root / 'tessdata')
            with fitz.open(stream=self.fixture(scan=True), filetype='pdf') as doc:
                with app.model_directory(root) as models:
                    self.assertEqual(models, 'tessdata')
                    text = doc[0].get_textpage_ocr(language='deu+eng', dpi=150, full=True, tessdata=models)
                    self.assertIn('SECRET', text.extractText())
            self.assertEqual(Path.cwd(), original)

            with self.assertRaisesRegex(RuntimeError, 'test failure'):
                with app.model_directory(root):
                    raise RuntimeError('test failure')
            self.assertEqual(Path.cwd(), original)

    def test_searchable_redacted_export(self):
        for scan in (False, True):
            for rotation in (0, 90, 180, 270):
                with self.subTest(scan=scan, rotation=rotation):
                    self.post('/load', self.fixture(scan=scan, rotation=rotation), True)
                    # Populate the original OCR cache with the secret. Export
                    # must never use it for its new text layer.
                    self.post('/ocr', {'page': 0})
                    marks = json.loads(self.post('/search', {'term': 'SECRET'}))
                    self.assertTrue(marks['0'])
                    data = self.post('/export', {'marks': marks, 'searchable': True})
                    with fitz.open(stream=data, filetype='pdf') as result:
                        text = result[0].get_text().casefold()
                        self.assertNotIn('secret', text)
                        self.assertIn('alice', text)
                        self.assertIn('example', text)
                        self.assertEqual(result.embfile_count(), 0)
                        self.assertFalse(result.metadata.get('author'))
                        pix = result[0].get_pixmap(dpi=200)
                        image = Image.open(io.BytesIO(pix.tobytes('png')))
                        for x0, y0, x1, y1 in marks['0']:
                            self.assertEqual(image.getpixel((int((x0+x1)/2*image.width), int((y0+y1)/2*image.height)))[:3], (0, 0, 0))

    def test_searchable_export_failure_is_reported(self):
        self.post('/load', self.fixture(), True)
        with patch.object(fitz.Pixmap, 'pdfocr_tobytes', side_effect=RuntimeError('OCR unavailable')):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post('/export', {'marks': {}, 'searchable': True})
            self.assertIn('OCR-Export auf Seite 1', json.loads(error.exception.read())['error'])
        self.assertIsNotNone(app.DOCUMENT)

    def test_compression_profiles(self):
        image = Image.effect_noise((1200, 800), 80).convert('RGB')
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        with fitz.open() as doc:
            p = doc.new_page(width=432, height=288)
            p.insert_image(p.rect, stream=buf.getvalue())
            self.post('/load', doc.tobytes(), True)
        sizes = []
        for profile in ('standard', 'compact', 'small'):
            data = self.post('/export', {'marks': {}, 'profile': profile})
            sizes.append(len(data))
            with fitz.open(stream=data, filetype='pdf') as result:
                self.assertEqual(result[0].rect, fitz.Rect(0, 0, 432, 288))
                if profile != 'standard':
                    self.assertIn('DCTDecode', [entry[8] for entry in result[0].get_images()])
        self.assertLess(sizes[1], sizes[0])
        self.assertLess(sizes[2], sizes[1])

    def test_text_replacement_and_searchable_profiles(self):
        self.post('/load', self.fixture(), True)
        self.post('/ocr', {'page': 0})
        edits = {'0': [{'rect': [.08, .18, .8, .43], 'text': 'PUBLIC', 'font_size': 20}]}
        words = json.loads(self.post('/words', {'page': 0, 'edits': edits}))
        self.assertIn('PUBLIC', [w['text'] for w in words])
        self.assertNotIn('SECRET', [w['text'] for w in words])
        self.assertEqual(json.loads(self.post('/search', {'term': 'SECRET', 'edits': edits})), {})
        self.assertIn('0', json.loads(self.post('/search', {'term': 'PUBLIC', 'edits': edits})))
        self.assertTrue(self.post('/page', {'page': 0, 'edits': edits}).startswith(b'\x89PNG'))
        for profile in ('standard', 'compact', 'small'):
            with self.subTest(profile=profile):
                data = self.post('/export', {'marks': {}, 'edits': edits, 'searchable': True, 'profile': profile})
                with fitz.open(stream=data, filetype='pdf') as result:
                    text = result[0].get_text().casefold()
                    self.assertIn('public', text)
                    self.assertNotIn('secret', text)
                    if profile != 'standard':
                        self.assertIn('DCTDecode', [entry[8] for entry in result[0].get_images()])
                # Blackening has priority over replacement text.
                data = self.post('/export', {'marks': {'0': [edits['0'][0]['rect']]}, 'edits': edits, 'searchable': True, 'profile': profile})
                with fitz.open(stream=data, filetype='pdf') as result:
                    self.assertNotIn('public', result[0].get_text().casefold())
        # Client edits never modify the source document or its OCR cache.
        self.assertIn('0', json.loads(self.post('/search', {'term': 'SECRET'})))

    def test_invalid_edits_and_profiles(self):
        self.post('/load', self.fixture(), True)
        for request in (
            {'marks': {}, 'profile': 'unknown'},
            {'marks': {}, 'edits': []},
            {'marks': {}, 'edits': {'9': []}},
            {'marks': {}, 'edits': {'0': [{'rect': [0, 0, 1, 1], 'text': 'x', 'font_size': 0}]}},
            {'marks': {}, 'edits': {'0': [{'rect': [0, 0, .01, .01], 'text': 'This does not fit', 'font_size': 72}]}},
            {'marks': {}, 'edits': {'0': [{'rect': [0, 0, .5, .5], 'text': 'a'}, {'rect': [.1, .1, .6, .6], 'text': 'b'}]}},
        ):
            with self.subTest(request=request), self.assertRaises(urllib.error.HTTPError):
                self.post('/export', request)

    def test_replacement_unicode_and_removal(self):
        self.post('/load', self.fixture(), True)
        entry = {'rect': [.08, .18, .8, .43], 'text': 'Müller & <Söhne>', 'font_size': 18}
        edits = {'0': [entry]}
        words = json.loads(self.post('/words', {'page': 0, 'edits': edits}))
        text = ' '.join(w['text'] for w in words)
        self.assertIn('Müller', text)
        self.assertIn('<Söhne>', text)
        entry['text'] = ''
        data = self.post('/export', {'marks': {}, 'edits': edits})
        with fitz.open(stream=data, filetype='pdf') as result:
            image = Image.open(io.BytesIO(result[0].get_pixmap(dpi=200).tobytes('png')))
            self.assertEqual(image.getpixel((int(.3*image.width), int(.3*image.height)))[:3], (255, 255, 255))
        self.assertEqual(json.loads(self.post('/search', {'term': 'SECRET', 'edits': edits})), {})


if __name__ == '__main__':
    unittest.main()
