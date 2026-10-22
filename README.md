# PDF-Tool

Lokales Werkzeug für OCR, Schwärzungen, Textkorrekturen, Seitenverwaltung und Stapelverarbeitung. Die Originaldateien werden nicht überschrieben.

## Starten

- **Windows:** ZIP vollständig entpacken, `Start.bat` doppelklicken. Python 3.11 oder neuer muss installiert sein.
- **macOS / Linux aus Quellcode:** `sh Start.command`. Python 3.11 oder neuer ist erforderlich.
- **macOS als App:** Der Workflow „macOS DMG“ baut eine eigenständige App für Apple Silicon und Intel. Erfolgreiche Builds werden als Vorschau-Release unter GitHub → Releases bereitgestellt. DMG öffnen, App nach Programme ziehen und dort starten. Python und OCR-Modelle sind enthalten. Die App ist ad-hoc signiert, nicht von Apple notarisiert; macOS kann eine manuelle Freigabe unter Datenschutz & Sicherheit verlangen.

Beim ersten Quellcode-Start werden die Abhängigkeiten installiert. Danach öffnet sich die Oberfläche im Browser. Terminal geöffnet lassen oder „Programm beenden“ in der Oberfläche wählen. Ohne automatisches Browserfenster: `.venv/bin/python app.py --no-browser --port 8765`. Unter Windows lautet der Python-Pfad `.venv\Scripts\python.exe`.

Die Anwendung bindet ausschließlich an `127.0.0.1`, verwendet keine externen Skripte, Schriften, Telemetrie oder Cloud-APIs und ist für eine Person pro Prozess vorgesehen. In einer Cloud-Entwicklungsumgebung läuft sie auf der Cloud-Maschine; für private lokale Verarbeitung auf dem eigenen Rechner starten.

## Einzeldatei bearbeiten

1. Eine PDF öffnen oder hineinziehen (maximal 150 MB, ohne Passwort).
2. Bei Scans OCR ausführen. Sprache Deutsch + Englisch; 150, 200 oder 300 dpi und aktuelle / alle Seiten wählbar. „Unveränderte Textseiten erhalten“ überspringt vorhandenen brauchbaren Text. Bei gemischten Seiten mit nur teilweise vorhandenem Text diese Option deaktivieren.
3. Rechtecke zum Schwärzen ziehen oder im Wortmodus ein Wort anklicken, um alle gleichen Wörter dokumentweit zu markieren. Groß-/Kleinschreibung und übliche Satzzeichen werden im Wortmodus ignoriert.
4. Im Suchfeld einen Begriff oder eine Wortgruppe pro Zeile eingeben. Gelbe Treffer sind Vorschau; „Alle Treffer schwärzen“ oder Strg+Enter / Cmd+Enter übernimmt sie. Trefferliste und Zoom helfen beim Prüfen.
5. Geänderte Seiten in der Prüfansicht mit „Diese Seite geprüft“ freigeben. Weitere Änderungen heben die jeweilige Freigabe auf. Mit „Nächste ungeprüfte Änderung“ durchgehen. Für Einzeldateien lässt sich die Freigabepflicht ausdrücklich deaktivieren; für markierte Stapeldateien ist sie erforderlich.
6. Ausgabeformat und Größenprofil auswählen, „PDF speichern“. Die gespeicherte Datei vor Weitergabe kontrollieren.

„Letzten Schritt zurück“ nimmt Schwärzungen, Textkorrekturen und die letzten fünf Seitenplanänderungen zurück. Dokument schließen, Server beenden oder eine andere Datei öffnen verwirft nicht gespeicherte Änderungen. Mehrere Browser-Tabs teilen denselben Serverzustand.

## Text bearbeiten

Werkzeug „Text bearbeiten“ wählen, ein Wort anklicken oder einen Bereich aufziehen. Ersatztext und Schriftgröße (4–72 pt) eingeben und übernehmen. Leerer Text entfernt den Bereich. Der Hintergrund wird weiß; schwarze Standardschrift wird eingesetzt. Unicode, Klartext-Markup und mehrere Zeilen werden unterstützt, sofern sie in den Bereich passen. Andernfalls Bereich vergrößern oder Schrift verkleinern. Überlappende Textänderungen sind nicht erlaubt.

Das ist ein Editor für einzelne Stellen, kein Textverarbeitungsprogramm: Originalschrift, Hintergrundgestaltung und Layoutfluss werden nicht automatisch rekonstruiert. Änderungen erscheinen in Vorschau, Suche und Export; ersetzte Originalstellen werden nicht weiter als Treffer angeboten. Schwärzungen haben Vorrang vor Ersatztext. Nicht übernommene Textänderungen blockieren den Export.

## OCR-PDF und Dateigröße

| Profil | Verhalten |
| --- | --- |
| **Verlustfrei** | Vorhandene Bilder und Vektorlogos werden ohne Neuberechnung übernommen; PDF-Objekte werden optimiert. Keine garantierte Größenersparnis. |
| Standard | Seitenbilder mit 200 dpi / PNG; neue bereinigte Ausgabe. |
| Kompakt | Seitenbilder mit 150 dpi / JPEG-Qualität 80; Qualitätsverlust möglich. |
| Klein | Seitenbilder mit 100 dpi / Graustufen / JPEG-Qualität 60; feine Schrift und Farben können verloren gehen. |

Verlustfrei entfernt markierte Text-, Bild- und Grafikanteile mit nativen PDF-Schwärzungen und bereinigt ungenutzte Objekte. Nicht betroffene Bilder werden nicht neu komprimiert; Vektorgrafiken bleiben Vektoren. Grafikobjekte, die einen bearbeiteten Bereich schneiden, können als ganzes Objekt entfernt werden. PDFs mit Anmerkungen oder Formularfeldern werden in diesem Profil ausdrücklich abgewiesen; hierfür ist eine bereinigte Ausgabe mit einem Rasterprofil nötig. Es wird niemals stillschweigend auf eine verlustbehaftete Ausgabe gewechselt.

Bei „Durchsuchbare PDF“ wird bei Rasterprofilen ausschließlich der bereits bearbeitete und geschwärzte Stand erkannt. Die OCR-Auflösung beträgt mindestens die gewählte Erkennungsauflösung bzw. Bildauflösung; kleinere gespeicherte Bilder behalten ihre neue Textschicht. Im verlustfreien Profil wird fehlender Text ergänzt, ohne Originalbilder auszutauschen. Wenn Überspringen deaktiviert ist, werden auch gemischte Seiten erkannt; vorhandene native Wörter werden nicht als doppelte OCR-Kopien eingefügt. Unter „Originaltext erhalten · ohne zusätzliche OCR“ bleiben im verlustfreien Profil vorhandene Textschichten bestehen. Eine echte Bild-PDF ohne Textschicht benötigt ein Rasterprofil.

Schwärzungen kopieren weder den ursprünglichen OCR-Suchcache noch wiederherstellbare Zeichen im markierten Bereich. PDF-Dokumentmetadaten und Dokumentanhänge werden nicht übernommen. Das verlustfreie Profil erhält außerhalb bearbeiteter Stellen ursprüngliche PDF-Objekte und Bilddaten einschließlich möglicher Bild-Metadaten. Für eine vollständige rasterbasierte Neuerstellung Standard / Kompakt / Klein wählen. Rasterprofile verlieren digitale Signaturen, Formulare, Links und die ursprüngliche Barrierefreiheitsstruktur; auch native Änderungen machen vorhandene Signaturen ungültig.

Nach dem Download zeigt die Oberfläche Dateigröße und Änderung gegenüber dem Original. Eine bereits optimal komprimierte oder rein vektorbasierte PDF kann kleiner als der Export sein. Es gibt keine garantierte Zielgröße.

## Stapel mit 10–20 PDFs

Mehrere PDFs hineinziehen oder „PDFs zum Stapel hinzufügen“ nutzen. Maximal 20 Dateien, je 150 MB und zusammen 500 MB. Nur eine Quelle wird gleichzeitig verarbeitet. Der Stapel ist unabhängig von der aktuell geöffneten Einzeldatei.

**Nur OCR:** Qualität, Ausgabeprofil und Überspringen vorhandener Textseiten einstellen, „OCR-Stapel starten / fortsetzen“ wählen. Unveränderte geeignete Textseiten werden ohne erneute OCR und ohne Rasterung übernommen. Das Größenprofil gilt dort nicht als verlustbehaftete Neuberechnung. Bei teilweise erkannten gemischten Seiten Überspringen deaktivieren.

**Gemeinsame Schwärzungsliste:** Begriffe zeilenweise eingeben, „Treffer vorbereiten“ wählen. Jede Datei über „Prüfen / bearbeiten“ öffnen, Treffer und mögliche OCR-Lücken kontrollieren, geänderte Seiten freigeben und „Änderungen für Stapel übernehmen“ wählen. Zusätzliche Rechtecke, Textänderungen und Seitenpläne können übernommen werden. Erst danach den OCR-Stapel ausgeben. Die Suchliste allein ist keine Vollständigkeitsgarantie.

Fehlerhafte Dateien stoppen den Rest nicht. „Fehlgeschlagene wiederholen“ verarbeitet nur Fehler erneut. „Nach aktueller Datei stoppen“ beendet noch die laufende Datei; Start setzt die wartenden Dateien fort. „Alle neu verarbeiten“ wiederholt auch erfolgreiche Dateien. Eine laufende einzelne OCR-Seite wird nicht gewaltsam abgebrochen. Schließen / Neuladen des Browsers verwirft die browserseitige Dateiauswahl; dies ist kein dauerhaft gespeicherter Auftrag.

„Ergebnisse + Bericht als ZIP“ enthält erfolgreiche PDFs mit `-ocr.pdf`, eindeutige Namen bei Namenskollisionen sowie CSV-/JSON-Berichte. Berichte nennen Status, Fehler, Seiten, OCR-/erhaltene Seiten, Seiten ohne erkannten Text, Größen und Einstellungen. Eine Seite ohne erkannten Text ist ein Prüfhinsweis, nicht automatisch ein Programmfehler. Berichte enthalten keine gefundenen Namen oder Suchbegriffe.

Fertige Stapelausgaben werden vorübergehend in einem privaten lokalen Temp-Ordner gespeichert. „Stapel leeren“ und reguläres Programmende löschen sie. Nach Absturz / erzwungenem Beenden können temporäre Dateien verbleiben. Einzeldateien, Vorschauen und OCR-Suchcache bleiben ansonsten im Arbeitsspeicher; Browserdownloads werden im Download-Ordner gespeichert. Betriebssystem / Browser können RAM auslagern; keine Garantie gegen lokale Forensik.

## Seiten und Dokumente verwalten

- Im Seitenplan Seiten nach oben / unten verschieben, um 90° drehen und entfernen. Mindestens eine Seite behalten, dann „Seitenplan übernehmen“. Markierungen und Ersatztexte werden mitgedreht und neu zugeordnet; Freigaben werden zurückgesetzt. Der Server hält maximal fünf Strukturänderungen zum Rückgängigmachen.
- Im Stapel „Dateien in Listenreihenfolge zusammenführen“ öffnet eine gemeinsame PDF im Einzeldatei-Editor. Originale werden nicht überschrieben. Einzeldatei-Markierungen des Stapels werden beim Zusammenführen nicht automatisch übertragen; die gemeinsame Datei anschließend prüfen / bearbeiten.
- „PDF aufteilen“: Gruppen wie `1-3;4-6;7` oder `1,3;2,4` eingeben. Leer bedeutet jede Seite einzeln. Ausgabe als ZIP unter Beachtung von Schwärzungen, Textänderungen, OCR und Qualitätsprofil. Seiten dürfen nicht doppelt in Gruppen vorkommen.

## Vorschläge und gespeicherte Abläufe

E-Mail-Adressen, IBANs bekannter Länder mit gültiger Mod-97-Prüfsumme und mögliche deutsche Telefonnummern werden als auswählbare Vorschläge angeboten. Sie werden **nicht automatisch übernommen**. Telefonnummern können Fehlalarme sein; OCR-Fehler und abweichende Schreibweisen können Treffer verhindern. Für Scans vorher OCR bzw. im Stapel „Treffer vorbereiten“ ausführen. Erst ausgewählte Vorschläge übernehmen, dann Seiten prüfen.

Unter „Gespeicherte Abläufe / Suchlisten“ gibt es mitgelieferte und eigene Vorlagen. Einstellungen werden lokal gespeichert, nicht in der PDF oder im Repository. Suchbegriffe werden nur mit aktivierter Option „Suchbegriffe mit speichern“ abgelegt. Eigene Vorlagen lassen sich löschen.

Speicherort: Windows `%LOCALAPPDATA%\PDF-Tool\settings.json`, macOS `~/Library/Application Support/PDF-Tool/settings.json`, Linux `$XDG_CONFIG_HOME/PDF-Tool/settings.json` bzw. `~/.config/PDF-Tool/settings.json`. Für isolierte Tests ist `PDF_TOOL_SETTINGS` überschreibbar.

## OCR-Probleme

Die Anzeige zählt die Zeit pro Seite, nicht den internen Erkennungsfortschritt. Tesseract kann bei komplexen Scans lange benötigen. Für einen Test 150 dpi / nur aktuelle Seite wählen. Große Erkennungsraster werden begrenzt; extrem große Seiten werden abgewiesen.

`Tesseract language initialisation failed` bedeutet, dass die Sprachmodelle nicht geladen werden konnten. `tessdata/deu.traineddata` und `tessdata/eng.traineddata` müssen vollständig vorhanden sein. Das Tool nutzt relative Modellpfade, um Windows-Probleme mit Umlauten zu vermeiden. Gegebenenfalls außerhalb von OneDrive in einem lokalen Ordner wie `C:\PDF-Tool` entpacken. OCR benötigt keine externe Tesseract-Installation.

## Entwicklung und Tests

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Browserprüfungen benötigen separat Node.js, Playwright und Chromium. Einen **separaten Testserver** mit `PDF_TOOL_SETTINGS=/tmp/pdf-tool-test-settings.json .venv/bin/python app.py --no-browser --port 8793` starten. Dann nacheinander `node tests/browser.cjs http://127.0.0.1:8793` und `node tests/browser-workflows.cjs http://127.0.0.1:8793` ausführen. Tests erzeugen eigene Dateien und ersetzen Serverzustände. Mit `CHROMIUM_PATH` lässt sich der Standardpfad `/usr/bin/chromium` anpassen.

Mac-Build auf macOS: `python3 -m pip install -r requirements.txt pyinstaller==6.17.0`, `bash packaging/build-macos.sh`, dann `python3 packaging/smoke-macos.py`. GitHub Actions baut native ARM64- und x86_64-Versionen und erstellt einen commitbezogenen Vorschau-Release nur nach erfolgreichen Tests der gepackten Apps. Keine Apple-Zertifikate oder Notarisierungszugänge sind enthalten.

## Lizenzen

PyMuPDF unterliegt AGPL bzw. kommerzieller Lizenz. Vor Weiterverteilung oder Integration müssen die entsprechenden Lizenzbedingungen erfüllt werden. Pillow und weitere gebündelte Komponenten haben eigene Lizenzbedingungen.

Sprachmodelle: tesseract-ocr/tessdata_fast, `deu.traineddata` und `eng.traineddata`, Apache-2.0; Quelle https://github.com/tesseract-ocr/tessdata_fast . Die Modelle werden lokal mitgeliefert; Dokumentinhalte werden nicht an diesen Anbieter übertragen.
