import io, json, secrets, threading, webbrowser, math, argparse
import unicodedata
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import pymupdf as fitz
from PIL import Image, ImageDraw

TOKEN = secrets.token_urlsafe(32)
DOCUMENT = None
OCR_CACHE = {}

def word_key(text):
    return unicodedata.normalize('NFKC', text).casefold().strip('.,;:!?()[]{}\"„“”«»')

def page_words(index):
    page = DOCUMENT[index]
    words = list(page.get_text('words'))
    if index in OCR_CACHE:
        words.extend(OCR_CACHE[index][1].extractWORDS())
    result, seen = [], set()
    for word in words:
        rect = fitz.Rect(word[:4]) * page.rotation_matrix
        key = (word[4], tuple(round(v, 1) for v in rect))
        if key in seen:
            continue
        seen.add(key)
        rect = rect + (-1, -1, 1, 1)
        result.append({'text': word[4], 'rect': [max(0, rect.x0/page.rect.width), max(0, rect.y0/page.rect.height), min(1, rect.x1/page.rect.width), min(1, rect.y1/page.rect.height)]})
    return result

def export_pdf(doc, marks):
    if not isinstance(marks, dict):
        raise ValueError('Ungültige Markierungen')
    for key, rectangles in marks.items():
        if key not in {str(n) for n in range(len(doc))} or not isinstance(rectangles, list):
            raise ValueError('Ungültige Seite oder Markierungen')
        for r in rectangles:
            if not isinstance(r, list) or len(r) != 4 or not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in r):
                raise ValueError('Ungültige Markierung')
            if r[2] <= r[0] or r[3] <= r[1]:
                raise ValueError('Leere Markierung')
    out = fitz.open()
    for n, page in enumerate(doc):
        pix = page.get_pixmap(dpi=200, colorspace=fitz.csRGB, alpha=False)
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        draw = ImageDraw.Draw(img)
        for r in marks.get(str(n), []):
            if len(r) != 4 or not all(isinstance(v, (int,float)) and math.isfinite(v) and 0 <= v <= 1 for v in r):
                raise ValueError('Ungültige Markierung')
            x0,y0,x1,y1 = r
            if x1 <= x0 or y1 <= y0: raise ValueError('Leere Markierung')
            draw.rectangle((math.floor(x0*pix.width), math.floor(y0*pix.height), min(pix.width-1, math.ceil(x1*pix.width)), min(pix.height-1, math.ceil(y1*pix.height))), fill='black')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=buf.getvalue())
    data = out.tobytes(garbage=4, deflate=True)
    out.close()
    return data

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, data, kind='application/json', status=200):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}': return self.reply(b'{}', status=403)
        if self.path != '/': return self.reply(b'{}', status=404)
        html = Path(__file__).with_name('index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
        self.reply(html.encode(), 'text/html; charset=utf-8')
    def do_POST(self):
        global DOCUMENT
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}': return self.reply(b'{}', status=403)
        if self.headers.get('X-Token') != TOKEN: return self.reply(b'{}', status=403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0: raise ValueError('Ungültige Inhaltslänge')
            if length > 150*1024*1024: raise ValueError('Maximal 150 MB pro PDF')
            raw = self.rfile.read(length)
            if self.path == '/load':
                doc = fitz.open(stream=raw, filetype='pdf')
                if doc.needs_pass:
                    doc.close()
                    raise ValueError('Bitte zuerst eine unverschlüsselte Kopie erstellen.')
                if not len(doc):
                    doc.close()
                    raise ValueError('PDF enthält keine Seiten')
                if DOCUMENT: DOCUMENT.close()
                OCR_CACHE.clear()
                DOCUMENT = doc
                return self.reply(json.dumps({'pages':len(doc)}).encode())
            if not DOCUMENT: raise ValueError('Bitte PDF öffnen')
            req = json.loads(raw)
            if self.path in ('/page', '/ocr', '/words'):
                index = req.get('page')
                if type(index) is not int or not 0 <= index < len(DOCUMENT):
                    raise ValueError('Ungültige Seitennummer')
            if self.path == '/words':
                return self.reply(json.dumps(page_words(index)).encode())
            if self.path == '/page':
                p = DOCUMENT[int(req['page'])]
                zoom = req.get('zoom', 1)
                if type(zoom) not in (int, float) or not math.isfinite(zoom) or not .5 <= zoom <= 3:
                    raise ValueError('Ungültiger Zoom')
                scale = min(1.5 * zoom, 4000 / max(p.rect.width, p.rect.height))
                return self.reply(p.get_pixmap(matrix=fitz.Matrix(scale,scale), alpha=False).tobytes('png'), 'image/png')
            if self.path == '/ocr':
                index = int(req['page'])
                dpi = req.get('dpi', 200)
                if type(dpi) is not int or dpi not in (150, 200, 300):
                    raise ValueError('OCR-Auflösung muss 150, 200 oder 300 dpi sein')
                rect = DOCUMENT[index].rect
                pixel_area = rect.width * rect.height * (dpi / 72) ** 2
                effective_dpi = min(dpi, int(dpi * math.sqrt(12_000_000 / max(1, pixel_area))))
                if effective_dpi < 72:
                    raise ValueError('Seite zu groß für OCR. Bitte Seitengröße verkleinern.')
                if index not in OCR_CACHE or OCR_CACHE[index][2] != dpi:
                    tessdata = Path(__file__).with_name('tessdata')
                    if not all((tessdata / (lang + '.traineddata')).is_file() for lang in ('deu','eng')):
                        raise ValueError('OCR-Sprachmodelle fehlen im Ordner tessdata.')
                    ocr_page = DOCUMENT[index]
                    rotation = ocr_page.rotation
                    try:
                        ocr_page.set_rotation(0)
                        textpage = ocr_page.get_textpage_ocr(
                            language='deu+eng', dpi=effective_dpi, full=True, tessdata=str(tessdata))
                        OCR_CACHE[index] = (ocr_page, textpage, dpi)
                    finally:
                        ocr_page.set_rotation(rotation)
                text = OCR_CACHE[index][1].extractText()
                return self.reply(json.dumps({'characters':len(text), 'dpi':effective_dpi}).encode())
            if self.path == '/search':
                term = req['term'].strip()
                if not term: raise ValueError('Suchtext fehlt')
                hits = {}
                for n,p in enumerate(DOCUMENT):
                    rects=[]
                    if req.get('whole_word'):
                        rects = [w['rect'] for w in page_words(n) if word_key(w['text']) == word_key(term)]
                        if rects: hits[str(n)] = rects
                        continue
                    found = list(p.search_for(term))
                    if n in OCR_CACHE:
                        found.extend(OCR_CACHE[n][0].search_for(term, textpage=OCR_CACHE[n][1]))
                    seen = set()
                    for r in found:
                        key = tuple(round(v, 1) for v in r)
                        if key in seen: continue
                        seen.add(key)
                        r = (r + (-1,-1,1,1)) * p.rotation_matrix
                        rects.append([max(0,r.x0/p.rect.width),max(0,r.y0/p.rect.height),min(1,r.x1/p.rect.width),min(1,r.y1/p.rect.height)])
                    if rects: hits[str(n)]=rects
                return self.reply(json.dumps(hits).encode())
            if self.path == '/export':
                return self.reply(export_pdf(DOCUMENT, req['marks']), 'application/pdf')
            if self.path == '/clear':
                DOCUMENT.close(); DOCUMENT=None
                OCR_CACHE.clear()
                return self.reply(b'{}')
            self.reply(b'{}',status=404)
        except Exception as e:
            self.reply(json.dumps({'error':str(e)}).encode(), status=400)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    url = f'http://127.0.0.1:{server.server_port}'
    print('PDF-Schwärzer läuft lokal: '+url+'\nBeenden: Strg+C', flush=True)
    if not args.no_browser:
        threading.Timer(.5, lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if DOCUMENT: DOCUMENT.close()
        server.server_close()
