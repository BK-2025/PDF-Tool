# PDF-Schwärzer

Unter Windows: `Start.bat` doppelklicken. Python 3.11 oder neuer muss installiert sein. Das Skript erstellt eine lokale virtuelle Umgebung, installiert die Abhängigkeiten und öffnet das Tool im Browser. Das Terminal geöffnet lassen; zum Beenden Strg+C drücken. Unter Windows wird der Python-Launcher `py` oder ersatzweise `python` verwendet.

Start: `sh Start.command` im Projektordner ausführen (Python 3.11 oder neuer). Unter macOS lässt sich `Start.command` auch doppelklicken. Beim ersten Start werden die Python-Abhängigkeiten installiert.

Ohne automatisches Browserfenster: `sh Start.command --no-browser --port 8765`. Die Anwendung bindet ausschließlich an die lokale Loopback-Adresse. Nur für eine Person und ein geöffnetes Dokument pro Prozess vorgesehen. In einer Cloud-Umgebung läuft die Verarbeitung auf der Cloud-Maschine; die Aussage „auf deinem Rechner“ gilt für den lokalen Start.

1. PDF öffnen (bis 150 MB, ohne Passwort).
2. Rechtecke aufziehen, Seiten mit den Pfeilen wechseln. Markierungen anklicken oder den letzten Schritt zurücknehmen.
3. Bei Scans zuerst „Scan-Texterkennung (OCR)“ ausführen. Dann Text suchen: alle gefundenen Vorkommen werden markiert. Keine automatische Erkennung personenbezogener Daten; fehlende Treffer und abweichende Schreibweisen manuell prüfen.
4. PDF speichern. Die heruntergeladene Datei erneut öffnen und alle Seiten vor Weitergabe kontrollieren.
5. Dokument schließen; zum Beenden im Terminal Strg+C drücken.

Die Verarbeitung läuft ausschließlich auf 127.0.0.1 auf deinem Rechner. Keine externen Skripte, Schriften, Telemetrie oder Cloud-APIs. Dokumente und Vorschauen werden durch das Werkzeug nicht auf Platte gespeichert. Der Browser speichert den Export im Download-Ordner. Betriebssystem und Browser können Arbeitsspeicher auslagern; keine Garantie gegen lokale Forensik.

Export: jede Seite wird je nach Profil mit 100, 150 oder 200 dpi gerendert (für die OCR-Erkennung mindestens 200 dpi), markierte Pixel schwarz überschrieben und als neues Bild in eine neue PDF geschrieben. Originalobjekte, Textschichten, Anhänge, Lesezeichen, Links, Formularfelder und Original-Metadaten werden nicht kopiert. Das Original bleibt unverändert. Standardmäßig erkennt OCR danach ausschließlich die geschwärzten Bilder erneut und ergänzt eine durchsuchbare, kopierbare Textschicht. Alternativ ist eine Bild-PDF ohne Textschicht auswählbar. Beide Varianten können größer werden und verlieren digitale Signaturen sowie die ursprüngliche Barrierefreiheitsstruktur. Sichtbare Angaben außerhalb der Markierungen bleiben erhalten.

Auf einem anderen Rechner: Python 3.11 oder neuer installieren und `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, `.venv/bin/python app.py` im Ordner ausführen. Nur die Installation benötigt Internet. PyMuPDF unterliegt AGPL bzw. kommerzieller Lizenz; bei Weiterverteilung oder Integration Lizenzbedingungen prüfen.

## Lokale OCR für gescannte PDFs

Nach dem Öffnen auf „Scan-Texterkennung (OCR)“ klicken. Das Werkzeug erkennt die gewählten Seiten mit einstellbaren 150, 200 oder 300 dpi auf Deutsch und Englisch und zeigt den Fortschritt pro Seite an. Danach findet die normale Suche auch Text in gescannten Seiten und markiert dessen Positionen. Vorhandene Markierungen bleiben bei OCR erhalten. Erkennungsergebnisse werden nur im Arbeitsspeicher für das aktuelle Dokument gehalten und beim Schließen oder Öffnen einer anderen PDF gelöscht. Für den durchsuchbaren Export wird eine neue Textschicht aus den bereits geschwärzten Bildern erstellt; die Erkennungsergebnisse des Originals werden nicht übernommen.

OCR ist keine verlässliche Vollständigkeitsprüfung. Besonders Handschrift, schiefe Scans, schlechte Bildqualität und ähnliche Zeichen (0/O, 1/I) können zu fehlenden oder falschen Treffern führen. Prüfe jede Seite visuell. Die Erkennung kann pro Seite einige Sekunden dauern.

Mitgelieferte Sprachmodelle: tesseract-ocr/tessdata_fast, deu.traineddata und eng.traineddata (Apache-2.0), Quelle https://github.com/tesseract-ocr/tessdata_fast . Keine Dokumentinhalte werden an diesen Anbieter übertragen. Die Modelle sind bereits lokal vorhanden; OCR benötigt keine Internetverbindung.

## Entwicklung und Prüfung

Installation: `python3 -m venv .venv` und `.venv/bin/python -m pip install -r requirements.txt`.

Tests: `.venv/bin/python -m unittest discover -s tests -v`. Die Tests erzeugen PDFs im Arbeitsspeicher und prüfen HTTP-Zugriffsschutz, Suche, OCR, gedrehte Seiten und den Rasterexport einschließlich Entfernung von Textschicht, Anhängen und Autorenmetadaten.

Die Ergebnisse und Grenzen der Prüfung stehen in `PRUEFBERICHT.md`.

## Drag-and-drop, Live-Suche und Wortauswahl

Eine PDF ins Fenster ziehen oder „PDF öffnen“ wählen. Für Scans zuerst OCR ausführen. Beim Tippen im Suchfeld werden Treffer nach kurzer Pause dokumentweit gesucht und auf der aktuellen Seite gelb angezeigt. „Alle Treffer schwärzen“ oder Strg+Enter (macOS: Cmd+Enter) übernimmt sie als Schwärzungen. Gelbe Vorschauen allein werden nicht exportiert; bei sichtbaren Vorschautreffern verlangt der Export die Übernahme oder das Leeren des Suchfelds.

Im Werkzeug „Wort anklicken → alle Vorkommen“ ein erkanntes Wort direkt auf der PDF anklicken. Alle gleichen Wörter auf allen Seiten werden markiert. Groß-/Kleinschreibung und übliche umgebende Satzzeichen werden ignoriert; Teilwörter werden im Wortmodus nicht erfasst. Die Eingabesuche unterstützt weiterhin Teiltexte und mehrere Wörter. Ohne PDF-Text oder OCR ist keine Wortauswahl möglich. Jede Übernahme lässt sich mit „Letzte Markierung zurück“ rückgängig machen. Im Rechteckmodus können einzelne Markierungen durch Anklicken entfernt werden.

## Mehrere Suchbegriffe, Fundstellen und Zoom

Im Suchfeld steht ein Suchbegriff oder eine Wortgruppe pro Zeile. Enter fügt eine neue Zeile hinzu; Strg+Enter / Cmd+Enter übernimmt alle Treffer. Mehrfach gefundene identische Rechtecke werden nur einmal übernommen. Die Suche umfasst alle Seiten und vorhandene OCR-Ergebnisse.

Unter „Fundstellen“ springt jeder Eintrag zur entsprechenden Seite und hebt die Stelle mit einem orangefarbenen Rahmen hervor. Die Liste bleibt nach der Übernahme verfügbar. Gelb bedeutet Suchvorschau, Schwarz bedeutet übernommene Schwärzung.

Mit − und + lässt sich zwischen 50 und 300 Prozent zoomen. „Breite anpassen“ setzt die Darstellung auf die verfügbare Standardbreite zurück. Die Vorschau wird für den Zoom neu gerendert (maximal 4000 Pixel pro Kante); der Export richtet sich unabhängig davon nach dem gewählten Größenprofil.

### Browsertest

Optional mit installiertem Node.js, Playwright und Chromium: Anwendung separat mit `.venv/bin/python app.py --no-browser --port 8766` starten, dann `node tests/browser.cjs http://127.0.0.1:8766` ausführen. Der Test erzeugt seine eigene PDF und ersetzt das Dokument im Testserver; deshalb einen separaten Prozess verwenden. Chromium wird standardmäßig unter `/usr/bin/chromium` gesucht; mit `CHROMIUM_PATH` lässt sich der Pfad anpassen. Eine eigene passende Test-PDF kann als zweites Argument übergeben werden.

## OCR dauert lange oder bleibt auf einer Seite

Standard ist jetzt 200 dpi; für einen schnellen Test „Schnell · 150 dpi“ und „Nur aktuelle Seite“ wählen. 300 dpi kann kleine Schrift besser erkennen, benötigt aber mehr Rechenzeit und Speicher. Sehr große Seiten werden für OCR auf etwa 12 Millionen Rasterpixel begrenzt; das ist keine feste Grenze für den gesamten Prozessspeicher. Die Anzeige zählt die verstrichenen Sekunden pro Seite, auch solange noch kein Ergebnis vorliegt. Sie misst keinen Erkennungsfortschritt. Fehler nennen die betroffene Seite. Bereits erkannte Seiten bleiben bei einem Fehler erhalten. Die native OCR einer einzelnen Seite lässt sich weiterhin nicht über die Oberfläche abbrechen; bei Bedarf den Server im Terminal mit Strg+C beenden. Dadurch gehen das geöffnete Dokument und ungespeicherte Markierungen verloren.

### Tesseract language initialisation failed

Die Meldung bedeutet, dass die OCR-Sprachmodelle nicht initialisiert werden konnten. Sie belegt keinen Fehler in der Seitenzahl. Im Unterordner `tessdata` müssen `deu.traineddata` und `eng.traineddata` vollständig vorhanden sein. Unter Windows können native Bibliotheken Probleme mit absoluten Pfaden mit Sonderzeichen haben. Das Tool lädt die Modelle deshalb über einen relativen Pfad. Als Diagnose den vollständigen entpackten Projektordner außerhalb von OneDrive in einen einfachen lokalen Pfad wie `C:\PDF-Tool` kopieren und dort starten. Die Windows-Ursache ist in der Linux-Testumgebung nicht abschließend nachstellbar.

## Geschwärzte PDF mit OCR speichern

Unter „PDF-Ausgabe“ ist „Durchsuchbare PDF · OCR nach Schwärzung“ vorausgewählt. Nach dem Markieren auf „PDF speichern“ klicken. Die Datei endet auf `-geschwaerzt-ocr.pdf`. Ihre sichtbaren Texte sind entsprechend der OCR-Erkennungsqualität suchbar und kopierbar. Ein vorheriger OCR-Lauf für die Suche ist für den Export nicht erforderlich.

Der Export rastert zuerst alle Seiten mit 200 dpi und überschreibt markierte Pixel schwarz. Nur diese geschwärzten Bilder werden danach mit Deutsch/Englisch erkannt; weder Originaltext noch OCR-Suchcache werden kopiert. Seitendrehungen werden für die Erkennung rückgängig gemacht und anschließend für die Ausgabe wiederhergestellt. Der OCR-Export benötigt mehr Zeit und funktionierende Sprachmodelle. Bei OCR-Fehlern wird keine vermeintlich durchsuchbare Datei ausgeliefert, sondern die betroffene Seite gemeldet. Der Modus „Bild-PDF · ohne Textschicht“ funktioniert weiterhin ohne OCR. Die neue OCR-Schicht kann Erkennungsfehler enthalten; die gespeicherte Datei vor Weitergabe prüfen.

## PDF verkleinern

Unter „Dateigröße / Qualität“ stehen drei Profile bereit:

| Profil | Gespeichertes Seitenbild | Verwendung |
| --- | --- | --- |
| Standard | 200 dpi, Farbe, verlustfreie PNG-Kompression | Lesbarkeit und unveränderte Rasterqualität |
| Kompakt | 150 dpi, Farbe, JPEG-Qualität 80 | Kleinere Dateien bei mäßigem Qualitätsverlust |
| Klein | 100 dpi, Graustufen, JPEG-Qualität 60 | Stärkere Reduktion; feine Schrift und Farben können verloren gehen |

Die Seitengröße auf Papier bleibt erhalten. Zum reinen Verkleinern können Schwärzungen und Textänderungen leer bleiben. „PDF speichern“ zeigt danach die erzeugte Dateigröße und die prozentuale Änderung zum Original. Eine bereits gut komprimierte oder rein vektorbasierte Originaldatei kann trotzdem kleiner als der Export sein; es gibt keine garantierte Zielgröße. Für durchsuchbare Ausgaben erkennt OCR zuerst das bereits bearbeitete und geschwärzte Bild mit 200 dpi. Danach wird das sichtbare Seitenbild entsprechend dem Profil reduziert; die neue Textschicht bleibt erhalten.

## Text bearbeiten

1. Im Werkzeug „Text bearbeiten · Wort / Bereich auswählen“ wählen.
2. Ein Wort anklicken oder einen rechteckigen Bereich aufziehen. Bei Scans ist für einen Wortklick zuerst OCR nötig; die Bereichsauswahl funktioniert auch ohne OCR.
3. Ersatztext und Schriftgröße zwischen 4 und 72 pt eingeben. Mehrere Zeilen sind möglich. Leerer Ersatztext entfernt den Inhalt.
4. „Text übernehmen“ anklicken. Die Vorschau zeigt die tatsächliche Ersetzung. Reicht der Bereich nicht aus, eine kleinere Schrift oder einen größeren Bereich wählen.
5. Änderungen sind in einer Liste mit Seitensprung und „Entfernen“ verfügbar. „Letzten Schritt zurück“ nimmt Textänderungen und Schwärzungen zurück.

Der gewählte Bereich erhält einen weißen Hintergrund und schwarze Standardschrift; Originalschrift, Layoutfluss und Hintergrundfarben werden nicht automatisch rekonstruiert. Bereiche dürfen sich nicht überschneiden; eine vorherige Änderung gegebenenfalls zuerst entfernen. Textänderungen gelten für den gewählten Bereich, nicht automatisch für alle gleichen Wörter. Das ist eine Korrekturfunktion für einzelne Stellen, kein Textverarbeitungsprogramm mit automatischem Seitenumbruch.

Die Originaldatei bleibt unverändert. Bei der Ausgabe wird die bearbeitete Seite gerastert; ursprüngliche Zeichen innerhalb ersetzter Bereiche werden nicht in die Ausgabe kopiert. Schwärzungen werden anschließend angewendet und haben Vorrang vor Ersatztext. Im OCR-Export wird ausschließlich der bereits bearbeitete und geschwärzte Stand neu erkannt. Nach dem Übernehmen durchsuchen Textsuche und Wortmodus die Ersatztexte; ersetzte Originalwörter werden ausgeblendet. Noch nicht übernommene Änderungen blockieren den Export. Dokument schließen, Server beenden oder eine andere PDF öffnen verwirft ungespeicherte Änderungen.
