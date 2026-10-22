"""Local batch processing, page plans, detection and reusable preferences."""
import csv
import io
import json
import math
import re
import secrets
import os
import sys
import tempfile
import zipfile
from pathlib import Path
import pymupdf as fitz

MAX_FILE = 150 * 1024 * 1024
MAX_BATCH = 500 * 1024 * 1024
def settings_path():
    if os.environ.get('PDF_TOOL_SETTINGS'):
        return Path(os.environ['PDF_TOOL_SETTINGS'])
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))
    elif sys.platform == 'darwin':
        root = Path.home()/'Library/Application Support'
    else:
        root = Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))
    return root/'PDF-Tool'/'settings.json'

SETTINGS_PATH = settings_path()


def open_pdf(raw):
    if not raw or len(raw) > MAX_FILE:
        raise ValueError('PDF fehlt oder überschreitet 150 MB')
    doc = fitz.open(stream=raw, filetype='pdf')
    if doc.needs_pass or not len(doc):
        doc.close()
        raise ValueError('PDF ist passwortgeschützt oder enthält keine Seiten')
    return doc


def has_text(page):
    text = page.get_text().strip()
    return sum(c.isalnum() for c in text) >= 8 and text.count('\ufffd') <= max(1, len(text)//10)


def preserve_text(page):
    # Annotated pages must be flattened so appearance is not lost by copying.
    return has_text(page) and not list(page.annots() or []) and not list(page.widgets() or [])


def normalized(rect, page):
    rect = (fitz.Rect(rect) + (-1, -1, 1, 1)) * page.rotation_matrix
    return [max(0, rect.x0/page.rect.width), max(0, rect.y0/page.rect.height), min(1, rect.x1/page.rect.width), min(1, rect.y1/page.rect.height)]


def rotate_rect(rect, degrees):
    points = [(rect[0], rect[1]), (rect[0], rect[3]), (rect[2], rect[1]), (rect[2], rect[3])]
    for _ in range((degrees % 360)//90):
        points = [(1-y, x) for x, y in points]
    return [min(x for x,y in points), min(y for x,y in points), max(x for x,y in points), max(y for x,y in points)]


def transform_pages(doc, plan, marks, edits):
    if not isinstance(plan, list) or not plan or len(plan) > len(doc):
        raise ValueError('Mindestens eine Seite behalten; Seiten nicht duplizieren')
    seen, new_marks, new_edits = set(), {}, {}
    out = fitz.open()
    try:
        for dest, item in enumerate(plan):
            if not isinstance(item, dict):
                raise ValueError('Ungültiger Seitenplan')
            source, rotation = item.get('page'), item.get('rotation', 0)
            if type(source) is not int or not 0 <= source < len(doc) or source in seen or type(rotation) is not int or rotation not in (0,90,180,270):
                raise ValueError('Ungültige oder doppelte Seite / Drehung')
            seen.add(source)
            out.insert_pdf(doc, from_page=source, to_page=source)
            out[-1].set_rotation((doc[source].rotation+rotation)%360)
            if marks.get(str(source)):
                new_marks[str(dest)] = [rotate_rect(r, rotation) for r in marks[str(source)]]
            if edits.get(str(source)):
                new_edits[str(dest)] = [dict(entry, rect=rotate_rect(entry['rect'], rotation), rotation=(entry.get('rotation', 0)+rotation)%360) for entry in edits[str(source)]]
        return out, new_marks, new_edits
    except Exception:
        out.close()
        raise


def parse_ranges(text, count):
    if not isinstance(text, str):
        raise ValueError('Seitenbereiche als Text angeben')
    if not text.strip():
        return [[n] for n in range(count)]
    groups, used = [], set()
    for part in text.split(';'):
        pages = []
        for chunk in part.split(','):
            match = re.fullmatch(r'\s*(\d+)(?:\s*-\s*(\d+))?\s*', chunk)
            if not match:
                raise ValueError('Seitenbereiche z. B. 1-3;4-6;7 oder 1,3;2,4')
            a, b = int(match[1]), int(match[2] or match[1])
            if not 1 <= a <= b <= count:
                raise ValueError('Seitenbereich außerhalb des Dokuments')
            for page in range(a-1,b):
                if page in used:
                    raise ValueError('Seiten dürfen beim Aufteilen nur einmal vorkommen')
                used.add(page)
                pages.append(page)
        groups.append(pages)
    return groups


def sensitive_suggestions(words):
    pieces, spans, cursor = [], [], 0
    for word in words:
        value = word['text']
        pieces.append(value)
        spans.append((cursor, cursor+len(value), word['rect']))
        cursor += len(value)+1
    text = ' '.join(pieces)
    found = []
    patterns = [('E-Mail', r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)'),
                ('Telefon', r'(?<!\w)(?:\+49|0049|0)[\d ()/.-]{6,24}\d(?!\w)')]
    for kind, pattern in patterns:
        for match in re.finditer(pattern, text):
            if kind == 'Telefon' and not 7 <= len(re.sub(r'\D','',match[0])) <= 15:
                continue
            found.append((kind, match[0], match.start(), match.end()))
    lengths = {'DE':22,'AT':20,'CH':21,'NL':18,'FR':27,'GB':22,'ES':24,'IT':27,'BE':16,'LU':20,'PL':28,'PT':25,'DK':18,'SE':24,'NO':15,'FI':18,'IE':22}
    for match in re.finditer(r'\b[A-Z]{2}\s*\d{2}(?:\s*[A-Z0-9]){10,30}', text):
        length = lengths.get(re.sub(r'\s','',match[0])[:2])
        if not length:
            continue
        indices = [i for i in range(match.start(),match.end()) if not text[i].isspace()]
        if len(indices) < length:
            continue
        end = indices[length-1]+1
        compact = re.sub(r'\s','',text[match.start():end])
        digits = ''.join(str(ord(c)-55) if c.isalpha() else c for c in compact[4:]+compact[:4])
        if int(digits)%97 == 1:
            found.append(('IBAN',text[match.start():end],match.start(),end))
    result, seen = [], set()
    for kind, value, start, end in found:
        rects = [rect for a,b,rect in spans if a < end and b > start]
        key = (kind,value,tuple(tuple(r) for r in rects))
        if rects and key not in seen:
            seen.add(key)
            result.append({'kind':kind, 'value':value, 'rects':rects})
    return result


def validate_options(options):
    if not isinstance(options, dict):
        raise ValueError('Ungültige Einstellungen')
    profile, dpi = options.get('profile','compact'), options.get('dpi',200)
    terms = options.get('terms',[])
    if profile not in ('lossless','standard','compact','small') or type(dpi) is not int or dpi not in (150,200,300):
        raise ValueError('Ungültige Qualität')
    if not isinstance(terms,list) or len(terms)>100 or any(not isinstance(t,str) or not t.strip() or len(t)>200 for t in terms):
        raise ValueError('Maximal 100 Suchbegriffe mit je 200 Zeichen')
    if any(type(options.get(k,True)) is not bool for k in ('skip_existing',)):
        raise ValueError('Ungültige Texterkennungseinstellung')
    return {'profile':profile,'dpi':dpi,'terms':list(dict.fromkeys(t.strip() for t in terms)), 'skip_existing':options.get('skip_existing',True)}


def preferences_read():
    if not SETTINGS_PATH.exists():
        return []
    data = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
    return validate_preferences(data)


def validate_preferences(data):
    if not isinstance(data,list) or len(data)>20:
        raise ValueError('Maximal 20 Vorlagen')
    result, seen = [], set()
    for item in data:
        if not isinstance(item,dict) or not isinstance(item.get('name'),str) or not 1 <= len(item['name'].strip()) <= 60:
            raise ValueError('Vorlagenname fehlt oder zu lang')
        name = item['name'].strip()
        if name in seen or item.get('export_mode','ocr') not in ('ocr','image'):
            raise ValueError('Doppelte Vorlage oder ungültiger Exportmodus')
        seen.add(name)
        result.append(dict(validate_options(item),name=name,export_mode=item.get('export_mode','ocr')))
    return result


def preferences_save(data):
    data = validate_preferences(data)
    SETTINGS_PATH.parent.mkdir(parents=True,exist_ok=True)
    temporary = SETTINGS_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    temporary.replace(SETTINGS_PATH)
    return data


def safe_name(value):
    value = re.split(r'[/\\]',str(value))[-1]
    value = re.sub(r'[\x00-\x1f<>:"|?*]','_',value).strip('. ')
    return (value or 'Dokument.pdf')[:120]


class BatchSession:
    """One source PDF at a time; completed outputs use private temporary files."""
    def __init__(self, exporter, directory, edit_validator=None):
        self.exporter, self.directory, self.edit_validator = exporter, directory, edit_validator
        self.temp = tempfile.TemporaryDirectory(prefix='pdf-tool-batch-')
        self.root = Path(self.temp.name)
        self.doc = self.out = None
        self.records = {}
        self.options = validate_options({})
        self.id = secrets.token_urlsafe(16)
        self.merge = None
        self.merge_bytes = self.merge_files = 0

    def close_current(self):
        for name in ('doc','out'):
            value = getattr(self,name)
            if value is not None:
                value.close()
                setattr(self,name,None)

    def close(self):
        self.close_current()
        if self.merge is not None:
            self.merge.close()
        self.temp.cleanup()

    def load(self, raw, key, name):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key):
            raise ValueError('Ungültige Datei-ID')
        if key not in self.records and len(self.records)>=20:
            raise ValueError('Maximal 20 Dateien pro Stapel')
        if sum(r.get('input_bytes',0) for k,r in self.records.items() if k != key)+len(raw)>MAX_BATCH:
            raise ValueError('Maximal 500 MB Eingangsdaten pro Stapel')
        self.close_current()
        self.key = key
        self.records[key] = {'id':key,'name':safe_name(name),'status':'geladen','input_bytes':len(raw),'output_bytes':0,'pages':0,'ocr_pages':0,'preserved_pages':0,'no_text_pages':[],'error':''}
        try:
            self.doc = open_pdf(raw)
        except Exception as e:
            self.records[key].update(status='Fehler',error=str(e))
            raise
        self.records[key]['pages'] = len(self.doc)
        return {'pages':len(self.doc)}

    def prepare(self, mode, marks, reviewed, edits=None):
        edits = {} if edits is None else edits
        if self.edit_validator:
            self.edit_validator(self.doc,edits)
        if self.doc is None or mode not in ('analyse','export'):
            raise ValueError('Keine Stapeldatei geöffnet oder ungültiger Modus')
        if not isinstance(marks,dict) or any(k not in {str(i) for i in range(len(self.doc))} or not isinstance(rs,list) or any(not isinstance(r,list) or len(r)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in r) or r[0]>=r[2] or r[1]>=r[3] for r in rs) for k,rs in marks.items()):
            raise ValueError('Ungültige Stapelmarkierungen')
        if mode == 'export' and any(rs and int(k) not in reviewed for state in (marks,edits) for k,rs in state.items()):
            raise ValueError('Schwärzungen zuerst seitenweise prüfen und für den Stapel freigeben')
        self.mode,self.marks,self.edits,self.next_page = mode,marks,edits,0
        self.out = fitz.open() if mode == 'export' else None
        self.records[self.key].update(status='Verarbeitung',output_bytes=0,ocr_pages=0,preserved_pages=0,no_text_pages=[],error='',profile=self.options['profile'],dpi=self.options['dpi'])

    def step(self):
        if self.doc is None or not hasattr(self,'next_page') or self.next_page>=len(self.doc):
            raise ValueError('Keine ausstehende Seite')
        n, page = self.next_page, self.doc[self.next_page]
        record = self.records[self.key]
        native = has_text(page)
        hits, suggestions = [], []
        try:
            if self.mode == 'analyse':
                textpage = None
                if not native:
                    rotation = page.rotation
                    dpi = self.options['dpi']
                    area = page.rect.width*page.rect.height*(dpi/72)**2
                    dpi = min(dpi,int(dpi*math.sqrt(12_000_000/max(1,area))))
                    if dpi < 72:
                        raise ValueError('Seite zu groß für OCR')
                    try:
                        page.set_rotation(0)
                        with self.directory(Path(__file__).parent) as models:
                            textpage = page.get_textpage_ocr(language='deu+eng',dpi=dpi,full=True,tessdata=models)
                    finally:
                        page.set_rotation(rotation)
                for term in self.options['terms']:
                    for rect in page.search_for(term,textpage=textpage):
                        value = normalized(rect,page)
                        if value not in hits:
                            hits.append(value)
                words = page.get_text('words',textpage=textpage)
                suggestions = sensitive_suggestions([{'text':w[4],'rect':normalized(w[:4],page)} for w in words])
                record['ocr_pages' if textpage is not None else 'preserved_pages'] += 1
                characters = len(page.get_text(textpage=textpage).strip())
            else:
                marks = self.marks.get(str(n),[])
                edits = self.edits.get(str(n),[])
                if self.options['skip_existing'] and not marks and not edits and preserve_text(page):
                    self.out.insert_pdf(self.doc,from_page=n,to_page=n,annots=False,links=False)
                    record['preserved_pages'] += 1
                else:
                    with fitz.open() as one:
                        one.insert_pdf(self.doc,from_page=n,to_page=n)
                        stats = {}
                        raw = self.exporter(one,{'0':marks},True,self.options['profile'],edits={'0':edits},ocr_dpi=self.options['dpi'],stats=stats)
                    with fitz.open(stream=raw,filetype='pdf') as result:
                        self.out.insert_pdf(result)
                    record['ocr_pages'] += stats.get('ocr_pages',0)
                    record['preserved_pages'] += stats.get('preserved_pages',0)
                characters = len(self.out[-1].get_text().strip())
            if characters == 0:
                record['no_text_pages'].append(n+1)
            self.next_page += 1
            return {'page':n,'pages':len(self.doc),'native_text':native,'characters':characters,'marks':hits,'suggestions':suggestions}
        except Exception as e:
            record.update(status='Fehler',error=f'Seite {n+1}: {e}')
            self.close_current()
            raise ValueError(record['error']) from e

    def finish(self):
        if self.doc is None or self.next_page!=len(self.doc):
            raise ValueError('Datei noch nicht vollständig verarbeitet')
        record = self.records[self.key]
        if self.mode == 'export':
            target = self.root/(self.key+'.pdf')
            self.out.save(target,garbage=4,deflate=True)
            record['output_bytes'] = target.stat().st_size
            record['status'] = 'Fertig'
        else:
            record['status'] = 'Vorbereitet'
        self.close_current()
        return dict(record)

    def archive(self):
        archive = self.root/'Ergebnisse.zip'
        used = set()
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for key,record in self.records.items():
                if record['status']!='Fertig':
                    continue
                stem = Path(record['name']).stem
                name = stem+'-ocr.pdf'
                number = 2
                while name.casefold() in used:
                    name = f'{stem}-{number}-ocr.pdf'
                    number += 1
                used.add(name.casefold())
                z.write(self.root/(key+'.pdf'),name)
            records = list(self.records.values())
            z.writestr('Ergebnisbericht.json',json.dumps(records,ensure_ascii=False,indent=2))
            report = io.StringIO()
            writer = csv.writer(report,delimiter=';')
            writer.writerow(['Datei','Status','Seiten','OCR-Seiten','Textseiten erhalten','Seiten ohne Text','Original Bytes','Ausgabe Bytes','Profil','OCR dpi','Fehler'])
            for r in records:
                safe = lambda s: "'"+str(s) if str(s).startswith(('=','+','-','@','\t','\r')) else str(s)
                writer.writerow([safe(r['name']),r['status'],r['pages'],r['ocr_pages'],r['preserved_pages'],','.join(map(str,r['no_text_pages'])),r['input_bytes'],r['output_bytes'],r.get('profile',''),r.get('dpi',''),safe(r['error'])])
            z.writestr('Ergebnisbericht.csv','\ufeff'+report.getvalue())
        return archive
