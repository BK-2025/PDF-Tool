import io, json, secrets, threading, webbrowser, math, argparse
import unicodedata
import os
import html
import zipfile
import shutil
from urllib.parse import urlsplit, parse_qs
import workflows as wf
from contextlib import contextmanager
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import pymupdf as fitz
from PIL import Image, ImageDraw

TOKEN = secrets.token_urlsafe(32)
DOCUMENT = None
OCR_CACHE = {}
PAGE_UNDO = []

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
    'lossless': {'dpi': 200, 'format': 'PNG'},
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
            if type(entry.get('rotation',0)) is not int or entry.get('rotation',0) not in (0,90,180,270):
                raise ValueError('Ungültige Textdrehung')
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
                css=f'* {{ margin:0; padding:0; }} body {{font-family:sans-serif; font-size:{size}pt; color:black;}}', scale_low=1, rotate=(-entry.get('rotation',0))%360)
            if spare < 0:
                raise ValueError('Ersatztext passt nicht in den Bereich. Bereich größer ziehen oder Schrift verkleinern.')

def render_image(page, dpi, entries):
    if page.rect.width*page.rect.height*(dpi/72)**2>40_000_000:
        raise ValueError('Seite überschreitet die Rastergrenze. Niedrigere Auflösung oder verlustfreies Profil verwenden.')
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    if entries:
        with fitz.open() as edited:
            p = edited.new_page(width=page.rect.width, height=page.rect.height)
            p.insert_image(p.rect, stream=pix.tobytes('png'))
            write_edits(p, entries)
            pix = p.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)

def export_pdf(doc, marks, searchable=False, profile='standard', edits=None, ocr_dpi=200, skip_existing=False, stats=None):
    stats = {} if stats is None else stats
    stats.update(ocr_pages=0,preserved_pages=0)
    if type(ocr_dpi) is not int or ocr_dpi not in (150,200,300) or type(skip_existing) is not bool:
        raise ValueError('Ungültige OCR-Einstellungen')
    if type(searchable) is not bool:
        raise ValueError('Ungültiger Exportmodus')
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError('Ungültiges Größenprofil')
    options = PROFILES[profile]
    dpi = options['dpi']
    edits = {} if edits is None else edits
    validate_edits(doc, edits)
    tessdata = Path(__file__).resolve().with_name('tessdata')
    if not isinstance(marks, dict):
        raise ValueError('Ungültige Markierungen')
    for key, rectangles in marks.items():
        if key not in {str(n) for n in range(len(doc))} or not isinstance(rectangles, list):
            raise ValueError('Ungültige Seite oder Markierungen')
        if not all(valid_rect(r) for r in rectangles):
            raise ValueError('Ungültige Markierung')
    if profile == 'lossless':
        return export_lossless(doc,marks,edits,searchable,ocr_dpi,stats,skip_existing)
    with fitz.open() as out:
        for n, page in enumerate(doc):
            if searchable and skip_existing and not marks.get(str(n)) and not edits.get(str(n)) and wf.preserve_text(page):
                out.insert_pdf(doc,from_page=n,to_page=n,annots=False,links=False)
                stats['preserved_pages'] += 1
                continue
            recognition_dpi = max(ocr_dpi, dpi) if searchable else dpi
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
                    stats['ocr_pages'] += 1
                except Exception as e:
                    raise ValueError(f'OCR-Export auf Seite {n+1} fehlgeschlagen: {e}') from e
        return out.tobytes(garbage=4, deflate=True)

def add_ocr_layer(page, dpi):
    tessdata = Path(__file__).resolve().with_name('tessdata')
    if not all((tessdata/(lang+'.traineddata')).is_file() for lang in ('deu','eng')):
        raise ValueError('OCR-Sprachmodelle fehlen im Ordner tessdata.')
    rotation = page.rotation
    area = page.rect.width*page.rect.height*(dpi/72)**2
    dpi = min(dpi,int(dpi*math.sqrt(12_000_000/max(1,area))))
    if dpi<72:
        raise ValueError('Seite zu groß für OCR')
    try:
        page.set_rotation(0)
        pix = page.get_pixmap(dpi=dpi,colorspace=fitz.csRGB,alpha=False)
        with model_directory(tessdata.parent) as models:
            data = pix.pdfocr_tobytes(language='deu+eng',tessdata=models)
        with fitz.open(stream=data,filetype='pdf') as layer:
            for image in layer[0].get_images():
                layer[0].delete_image(image[0])
            # Keep existing vector text and add OCR only where it is absent.
            # This also covers mixed pages when skipping is disabled.
            native_words = page.get_text('words')
            for word in native_words:
                layer[0].add_redact_annot(fitz.Rect(word[:4]),fill=None,cross_out=False)
            if native_words:
                layer[0].apply_redactions(images=0,graphics=0,text=0)
            page.show_pdf_page(page.rect,layer,0)
    finally:
        page.set_rotation(rotation)


def export_lossless(doc, marks, edits, searchable, dpi, stats, skip_existing):
    # Preserve original image streams and vector artwork. Ambiguous interactive
    # appearances are refused, never silently rasterized in this profile.
    if any(list(p.annots() or []) or list(p.widgets() or []) for p in doc):
        raise ValueError('Verlustfrei: PDF enthält Anmerkungen oder Formularfelder. Für deren bereinigte Ausgabe Standard verwenden.')
    with fitz.open() as out:
        out.insert_pdf(doc,annots=False,links=False,widgets=False)
        for n,page in enumerate(out):
            page.remove_rotation()
            entries = edits.get(str(n),[])
            rectangles = marks.get(str(n),[])
            for entry in entries:
                page.add_redact_annot(edit_rect(page,entry),fill=(1,1,1),cross_out=False)
            for rect in rectangles:
                page.add_redact_annot(edit_rect(page,{'rect':rect}),fill=(0,0,0),cross_out=False)
            if entries or rectangles:
                page.apply_redactions(images=2,graphics=2,text=0)
            write_edits(page,entries)
            # Redactions win when an edit overlaps a blackened region.
            for rect in rectangles:
                page.add_redact_annot(edit_rect(page,{'rect':rect}),fill=(0,0,0),cross_out=False)
            if rectangles:
                page.apply_redactions(images=2,graphics=2,text=0)
            if searchable and (not skip_existing or not wf.has_text(page)):
                add_ocr_layer(page,dpi)
                stats['ocr_pages'] += 1
            elif searchable:
                stats['preserved_pages'] += 1
        return out.tobytes(garbage=4,deflate=True,deflate_images=True,deflate_fonts=True,use_objstms=1)


BATCH = wf.BatchSession(export_pdf,model_directory,validate_edits)

def require_review(req):
    if req.get('require_review',False):
        reviewed = req.get('reviewed_pages',[])
        if not isinstance(reviewed,list) or any(type(n) is not int for n in reviewed):
            raise ValueError('Ungültige Seitenfreigabe')
        dirty = {int(k) for key in ('marks','edits') for k,v in req.get(key,{}).items() if v}
        if not dirty.issubset(set(reviewed)):
            raise ValueError('Geänderte Seiten zuerst in der Prüfansicht freigeben')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, data, kind='application/json', status=200):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}': return self.reply(b'{}', status=403)
        if self.path == '/workflows.js':
            return self.reply(Path(__file__).with_name('workflows.js').read_bytes(),'text/javascript; charset=utf-8')
        if self.path != '/': return self.reply(b'{}', status=404)
        html = Path(__file__).with_name('index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
        self.reply(html.encode(), 'text/html; charset=utf-8')
    def do_POST(self):
        global DOCUMENT, PAGE_UNDO, BATCH
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}': return self.reply(b'{}', status=403)
        if self.headers.get('X-Token') != TOKEN: return self.reply(b'{}', status=403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0: raise ValueError('Ungültige Inhaltslänge')
            if length > 150*1024*1024: raise ValueError('Maximal 150 MB pro PDF')
            raw = self.rfile.read(length)
            parsed = urlsplit(self.path)
            route = parsed.path
            query = parse_qs(parsed.query)
            if route == '/shutdown':
                self.reply(b'{}')
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if route.startswith('/settings/'):
                request = json.loads(raw)
                value = wf.preferences_save(request.get('presets')) if route == '/settings/save' else wf.preferences_read()
                return self.reply(json.dumps({'presets':value}).encode())
            if route == '/batch/reset':
                request = json.loads(raw)
                options = wf.validate_options(request.get('options',{}))
                BATCH.close()
                BATCH = wf.BatchSession(export_pdf,model_directory,validate_edits)
                BATCH.options = options
                return self.reply(json.dumps({'session':BATCH.id}).encode())
            if route.startswith('/batch/'):
                if query.get('session',[''])[0] != BATCH.id:
                    raise ValueError('Stapelverbindung abgelaufen. Stapel neu starten.')
                if route == '/batch/load':
                    result = BATCH.load(raw,query.get('id',[''])[0],query.get('name',['Dokument.pdf'])[0])
                else:
                    request = json.loads(raw)
                    if route == '/batch/options':
                        BATCH.options = wf.validate_options(request)
                        result = {}
                    elif route == '/batch/prepare':
                        reviewed = request.get('reviewed_pages',[])
                        if not isinstance(reviewed,list) or any(type(n) is not int for n in reviewed):
                            raise ValueError('Ungültige Stapelfreigabe')
                        BATCH.prepare(request.get('mode'),request.get('marks',{}),reviewed,request.get('edits',{}))
                        result = {}
                    elif route == '/batch/step':
                        result = BATCH.step()
                    elif route == '/batch/finish':
                        result = BATCH.finish()
                    elif route == '/batch/fail':
                        key = request.get('id')
                        if key in BATCH.records:
                            BATCH.records[key].update(status='Fehler',error=str(request.get('error','Verarbeitung abgebrochen'))[:2000])
                            if getattr(BATCH,'key',None)==key:
                                BATCH.close_current()
                        result = {}
                    elif route == '/batch/report':
                        result = list(BATCH.records.values())
                    elif route == '/batch/zip':
                        target = BATCH.archive()
                        self.send_response(200)
                        self.send_header('Content-Type','application/zip')
                        self.send_header('Cache-Control','no-store')
                        self.send_header('Content-Length',str(target.stat().st_size))
                        self.end_headers()
                        with target.open('rb') as f:
                            shutil.copyfileobj(f,self.wfile)
                        return
                    else:
                        raise ValueError('Unbekannte Stapelaktion')
                return self.reply(json.dumps(result).encode())
            if route == '/merge/start':
                if BATCH.merge is not None:
                    BATCH.merge.close()
                BATCH.merge = fitz.open()
                BATCH.merge_bytes = BATCH.merge_files = 0
                return self.reply(b'{}')
            if route == '/merge/add':
                if BATCH.merge is None or BATCH.merge_files>=20 or BATCH.merge_bytes+len(raw)>wf.MAX_BATCH:
                    raise ValueError('Zusammenführen: maximal 20 Dateien / 500 MB')
                with wf.open_pdf(raw) as doc:
                    BATCH.merge.insert_pdf(doc)
                BATCH.merge_bytes += len(raw)
                BATCH.merge_files += 1
                return self.reply(b'{}')
            if route == '/merge/finish':
                if BATCH.merge is None or not len(BATCH.merge):
                    raise ValueError('Keine PDFs zum Zusammenführen')
                if DOCUMENT is not None:
                    DOCUMENT.close()
                DOCUMENT,BATCH.merge = BATCH.merge,None
                OCR_CACHE.clear()
                PAGE_UNDO.clear()
                return self.reply(json.dumps({'pages':len(DOCUMENT)}).encode())
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
                PAGE_UNDO.clear()
                return self.reply(json.dumps({'pages':len(doc)}).encode())
            if not DOCUMENT: raise ValueError('Bitte PDF öffnen')
            req = json.loads(raw)
            if self.path in ('/page', '/ocr', '/words'):
                index = req.get('page')
                if type(index) is not int or not 0 <= index < len(DOCUMENT):
                    raise ValueError('Ungültige Seitennummer')
            if self.path == '/source':
                return self.reply(DOCUMENT.tobytes(garbage=4),'application/pdf')
            if self.path == '/pages':
                marks,edits = req.get('marks',{}),req.get('edits',{})
                validate_edits(DOCUMENT,edits)
                if not isinstance(marks,dict) or any(k not in {str(n) for n in range(len(DOCUMENT))} or not isinstance(v,list) or not all(valid_rect(r) for r in v) for k,v in marks.items()):
                    raise ValueError('Ungültige Markierungen')
                updated,new_marks,new_edits = wf.transform_pages(DOCUMENT,req.get('plan'),marks,edits)
                token = secrets.token_hex(12)
                PAGE_UNDO.append({'id':token,'data':DOCUMENT.tobytes(garbage=4),'marks':marks,'edits':edits,'page':req.get('page',0)})
                if len(PAGE_UNDO)>5:
                    PAGE_UNDO.pop(0)
                DOCUMENT.close()
                DOCUMENT = updated
                OCR_CACHE.clear()
                return self.reply(json.dumps({'pages':len(DOCUMENT),'marks':new_marks,'edits':new_edits,'undo':token,'undo_ids':[item['id'] for item in PAGE_UNDO]}).encode())
            if self.path == '/pages/undo':
                if not PAGE_UNDO or req.get('id') != PAGE_UNDO[-1]['id']:
                    raise ValueError('Seitenänderung kann nicht zurückgenommen werden')
                state = PAGE_UNDO.pop()
                restored = fitz.open(stream=state.pop('data'),filetype='pdf')
                DOCUMENT.close()
                DOCUMENT = restored
                OCR_CACHE.clear()
                return self.reply(json.dumps(dict(state,pages=len(DOCUMENT))).encode())
            if self.path == '/suggestions':
                edits = req.get('edits',{})
                validate_edits(DOCUMENT,edits)
                suggestions = []
                for n in range(len(DOCUMENT)):
                    suggestions.extend(dict(item,page=n) for item in wf.sensitive_suggestions(page_words(n,edits)))
                return self.reply(json.dumps(suggestions).encode())
            if self.path == '/split':
                require_review(req)
                groups = wf.parse_ranges(req.get('ranges',''),len(DOCUMENT))
                data = export_pdf(DOCUMENT,req.get('marks',{}),req.get('searchable',True),req.get('profile','standard'),req.get('edits',{}),req.get('dpi',200),req.get('skip_existing',False))
                result = io.BytesIO()
                with fitz.open(stream=data,filetype='pdf') as source, zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as archive:
                    for n,group in enumerate(groups):
                        with fitz.open() as piece:
                            for index in group:
                                piece.insert_pdf(source,from_page=index,to_page=index)
                            archive.writestr(f'Teil-{n+1:03}.pdf',piece.tobytes(garbage=4,deflate=True))
                return self.reply(result.getvalue(),'application/zip')
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
                if req.get('skip_existing',False) and wf.has_text(DOCUMENT[index]):
                    return self.reply(json.dumps({'characters':len(DOCUMENT[index].get_text()),'dpi':0,'skipped':True}).encode())
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
                require_review(req)
                return self.reply(export_pdf(DOCUMENT, req['marks'], req.get('searchable', False), req.get('profile', 'standard'), req.get('edits', {}),req.get('dpi',200),req.get('skip_existing',False)), 'application/pdf')
            if self.path == '/clear':
                DOCUMENT.close(); DOCUMENT=None
                OCR_CACHE.clear()
                PAGE_UNDO.clear()
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
        BATCH.close()
        server.server_close()
