import io, json, secrets, threading, webbrowser, math, argparse
import unicodedata
import os
import html
from contextlib import contextmanager
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import pymupdf as fitz
from PIL import Image, ImageDraw

TOKEN = secrets.token_urlsafe(32)
DOCUMENT = None
OCR_CACHE = {}

@contextmanager
def model_directory(directory):
    # The server processes requests serially. Native Tesseract builds on Windows
    # may not handle non-ASCII absolute paths; pass only an ASCII relative path.
    previous = Path.cwd()
    try:
        os.chdir(directory)
        yield 'tessdata'
    finally:
        os.chdir(previous)

def word_key(text):
    return unicodedata.normalize('NFKC', text).casefold().strip('.,;:!?()[]{}\"„“”«»')

def page_words(index, edits=None):
    page = DOCUMENT[index]
    entries = (edits or {}).get(str(index), [])
    words = list(page.get_text('words'))
    if index in OCR_CACHE:
        words.extend(OCR_CACHE[index][1].extractWORDS())
    result, seen = [], set()
    for word in words:
        rect = fitz.Rect(word[:4]) * page.rotation_matrix
        if any(rect.intersects(edit_rect(page, entry)) for entry in entries):
            continue
        key = (word[4], tuple(round(v, 1) for v in rect))
        if key in seen:
            continue
        seen.add(key)
        rect = rect + (-1, -1, 1, 1)
        result.append({'text': word[4], 'rect': [max(0, rect.x0/page.rect.width), max(0, rect.y0/page.rect.height), min(1, rect.x1/page.rect.width), min(1, rect.y1/page.rect.height)]})
    if entries:
        with fitz.open() as overlay:
            p = overlay.new_page(width=page.rect.width, height=page.rect.height)
            write_edits(p, entries)
            for word in p.get_text('words'):
                r = fitz.Rect(word[:4]) + (-1,-1,1,1)
                result.append({'text': word[4], 'rect': [max(0,r.x0/p.rect.width),max(0,r.y0/p.rect.height),min(1,r.x1/p.rect.width),min(1,r.y1/p.rect.height)]})
    return result

PROFILES = {
    'standard': {'dpi': 200, 'format': 'PNG'},
    'compact': {'dpi': 150, 'format': 'JPEG', 'quality': 80},
    'small': {'dpi': 100, 'format': 'JPEG', 'quality': 60, 'grayscale': True},
}

def valid_rect(rect):
    return (isinstance(rect, list) and len(rect) == 4
            and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in rect)
            and rect[0] < rect[2] and rect[1] < rect[3])

def validate_edits(doc, edits):
    if not isinstance(edits, dict):
        raise ValueError('Ungültige Textänderungen')
    for key, entries in edits.items():
        if key not in {str(n) for n in range(len(doc))} or not isinstance(entries, list) or len(entries) > 200:
            raise ValueError('Ungültige Seite oder zu viele Textänderungen')
        for position, entry in enumerate(entries):
            if not isinstance(entry, dict) or not valid_rect(entry.get('rect')):
                raise ValueError('Ungültiger Textbereich')
            if any(fitz.Rect(entry['rect']).intersects(fitz.Rect(previous['rect'])) for previous in entries[:position]):
                raise ValueError('Textbereiche dürfen sich nicht überlappen. Vorherige Änderung zuerst entfernen.')
            text, size = entry.get('text'), entry.get('font_size', 12)
            if not isinstance(text, str) or len(text) > 2000 or any(ord(c) < 32 and c not in '\n\t' for c in text):
                raise ValueError('Ungültiger Ersatztext (maximal 2000 Zeichen)')
            if type(size) not in (int, float) or not math.isfinite(size) or not 4 <= size <= 72:
                raise ValueError('Schriftgröße muss zwischen 4 und 72 pt liegen')

def edit_rect(page, entry):
    x0, y0, x1, y1 = entry['rect']
    return fitz.Rect(x0*page.rect.width, y0*page.rect.height, x1*page.rect.width, y1*page.rect.height)

def write_edits(page, entries):
    for entry in entries:
        rect = edit_rect(page, entry)
        # Whiteout affects the image first. Only replacement text is inserted.
        page.draw_rect(rect, color=None, fill=(1, 1, 1), overlay=True)
        if entry['text']:
            content = html.escape(entry['text']).replace('\n', '<br>')
            size = entry.get('font_size', 12)
            spare, _ = page.insert_htmlbox(rect, content,
                css=f'* {{ margin:0; padding:0; }} body {{font-family:sans-serif; font-size:{size}pt; color:black;}}', scale_low=1)
            if spare < 0:
                raise ValueError('Ersatztext passt nicht in den Bereich. Bereich größer ziehen oder Schrift verkleinern.')

def render_image(page, dpi, entries):
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    if entries:
        with fitz.open() as edited:
            p = edited.new_page(width=page.rect.width, height=page.rect.height)
            p.insert_image(p.rect, stream=pix.tobytes('png'))
            write_edits(p, entries)
            pix = p.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)

def export_pdf(doc, marks, searchable=False, profile='standard', edits=None):
    if type(searchable) is not bool:
        raise ValueError('Ungültiger Exportmodus')
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError('Ungültiges Größenprofil')
    options = PROFILES[profile]
    dpi = options['dpi']
    edits = {} if edits is None else edits
    validate_edits(doc, edits)
    tessdata = Path(__file__).resolve().with_name('tessdata')
    if searchable and not all((tessdata / (lang + '.traineddata')).is_file() for lang in ('deu', 'eng')):
        raise ValueError('OCR-Sprachmodelle fehlen im Ordner tessdata.')
    if not isinstance(marks, dict):
        raise ValueError('Ungültige Markierungen')
    for key, rectangles in marks.items():
        if key not in {str(n) for n in range(len(doc))} or not isinstance(rectangles, list):
            raise ValueError('Ungültige Seite oder Markierungen')
        if not all(valid_rect(r) for r in rectangles):
            raise ValueError('Ungültige Markierung')
    with fitz.open() as out:
        for n, page in enumerate(doc):
            recognition_dpi = max(200, dpi) if searchable else dpi
            img = render_image(page, recognition_dpi, edits.get(str(n), []))
            draw = ImageDraw.Draw(img)
            for x0, y0, x1, y1 in marks.get(str(n), []):
                draw.rectangle((math.floor(x0*img.width), math.floor(y0*img.height), min(img.width-1, math.ceil(x1*img.width)), min(img.height-1, math.ceil(y1*img.height))), fill='black')
            ocr_image = img
            if dpi != recognition_dpi:
                img = img.resize((math.ceil(page.rect.width*dpi/72), math.ceil(page.rect.height*dpi/72)), Image.Resampling.LANCZOS)
            if options.get('grayscale'):
                img = img.convert('L')
            buf = io.BytesIO()
            img.save(buf, format=options['format'], **({'quality': options['quality'], 'optimize': True} if options['format'] == 'JPEG' else {}))
            p = out.new_page(width=page.rect.width, height=page.rect.height)
            p.insert_image(p.rect, stream=buf.getvalue())
            if searchable:
                # Recognize only sanitized pixels. JPEG is used only for final
                # storage; OCR sees the lossless edited/blackened raster.
                upright = ocr_image.rotate(page.rotation, expand=True)
                png = io.BytesIO()
                upright.save(png, format='PNG')
                sanitized = fitz.Pixmap(png.getvalue())
                sanitized.set_dpi(recognition_dpi, recognition_dpi)
                try:
                    with model_directory(tessdata.parent) as model_path:
                        recognized = sanitized.pdfocr_tobytes(language='deu+eng', tessdata=model_path)
                    with fitz.open(stream=recognized, filetype='pdf') as ocr_doc:
                        # Keep just the fresh invisible OCR layer. The displayed
                        # raster above already has the chosen compression.
                        for image in ocr_doc[0].get_images():
                            ocr_doc[0].delete_image(image[0])
                        p.show_pdf_page(p.rect, ocr_doc, 0, rotate=-page.rotation)
                except Exception as e:
                    raise ValueError(f'OCR-Export auf Seite {n+1} fehlgeschlagen: {e}') from e
        return out.tobytes(garbage=4, deflate=True)

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
                edits = req.get('edits', {})
                validate_edits(DOCUMENT, edits)
                return self.reply(json.dumps(page_words(index, edits)).encode())
            if self.path == '/page':
                p = DOCUMENT[int(req['page'])]
                zoom = req.get('zoom', 1)
                if type(zoom) not in (int, float) or not math.isfinite(zoom) or not .5 <= zoom <= 3:
                    raise ValueError('Ungültiger Zoom')
                scale = min(1.5 * zoom, 4000 / max(p.rect.width, p.rect.height))
                edits = req.get('edits', {})
                validate_edits(DOCUMENT, edits)
                image = render_image(p, max(36, int(72*scale)), edits.get(str(index), []))
                buf = io.BytesIO()
                image.save(buf, format='PNG')
                return self.reply(buf.getvalue(), 'image/png')
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
                    tessdata = Path(__file__).resolve().with_name('tessdata')
                    if not all((tessdata / (lang + '.traineddata')).is_file() for lang in ('deu','eng')):
                        raise ValueError('OCR-Sprachmodelle fehlen im Ordner tessdata.')
                    ocr_page = DOCUMENT[index]
                    rotation = ocr_page.rotation
                    try:
                        ocr_page.set_rotation(0)
                        with model_directory(tessdata.parent) as model_path:
                            textpage = ocr_page.get_textpage_ocr(
                                language='deu+eng', dpi=effective_dpi, full=True, tessdata=model_path)
                        OCR_CACHE[index] = (ocr_page, textpage, dpi)
                    finally:
                        ocr_page.set_rotation(rotation)
                text = OCR_CACHE[index][1].extractText()
                return self.reply(json.dumps({'characters':len(text), 'dpi':effective_dpi}).encode())
            if self.path == '/search':
                edits = req.get('edits', {})
                validate_edits(DOCUMENT, edits)
                term = req['term'].strip()
                if not term: raise ValueError('Suchtext fehlt')
                hits = {}
                for n,p in enumerate(DOCUMENT):
                    rects=[]
                    if req.get('whole_word'):
                        rects = [w['rect'] for w in page_words(n, edits) if word_key(w['text']) == word_key(term)]
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
                        if any(r.intersects(edit_rect(p, entry)) for entry in edits.get(str(n), [])):
                            continue
                        rects.append([max(0,r.x0/p.rect.width),max(0,r.y0/p.rect.height),min(1,r.x1/p.rect.width),min(1,r.y1/p.rect.height)])
                    if edits.get(str(n)):
                        with fitz.open() as overlay:
                            replacement = overlay.new_page(width=p.rect.width, height=p.rect.height)
                            write_edits(replacement, edits[str(n)])
                            for r in replacement.search_for(term):
                                r = r + (-1,-1,1,1)
                                rects.append([max(0,r.x0/p.rect.width),max(0,r.y0/p.rect.height),min(1,r.x1/p.rect.width),min(1,r.y1/p.rect.height)])
                    if rects: hits[str(n)]=rects
                return self.reply(json.dumps(hits).encode())
            if self.path == '/export':
                return self.reply(export_pdf(DOCUMENT, req['marks'], req.get('searchable', False), req.get('profile', 'standard'), req.get('edits', {})), 'application/pdf')
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
