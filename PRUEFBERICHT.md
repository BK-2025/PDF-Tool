# Prüfung und Nachbau

Grundlage: bereitgestellte Datei PDF-Schwaerzer(1).zip. Quellcode und deutsche/englische OCR-Modelle wurden übernommen; macOS-Metadaten und kompilierter Python-Cache wurden ausgelassen.

## Änderungen

- Rechnerabhängigen Python-Pfad durch eine projektlokale virtuelle Umgebung ersetzt; Startskript für POSIX-Shells.
- Headless-Start mit --no-browser ergänzt.
- Ungültige Seitenzahlen und negative Inhaltslängen werden abgewiesen.
- Export prüft sämtliche Markierungen vor Verarbeitung. Markierungen für nicht vorhandene Seiten werden nicht mehr stillschweigend ignoriert.
- Automatisierte Integrationstests und Git-Ausschlüsse ergänzt.

## Verifiziert

Python 3.12, PyMuPDF 1.26.7, Pillow 13.0.0. Vierzehn erfolgreiche Integrationstests mit mehreren Unterfällen: HTTP-Token, Vorschau, Textsuche und Rasterexport bei 0/90/180/270 Grad, OCR bei 0/90 Grad, Dokument schließen und OCR-Cache leeren, ungültige Anfragen. Der Bild-PDF-Export enthält keine extrahierbare Textschicht, keinen Test-Anhang und keine ursprüngliche Autorenangabe. Eine Pixelprobe im markierten Bereich ist schwarz. pip check meldet keine defekten Abhängigkeiten.

## Grenzen

Keine unabhängige Sicherheitszertifizierung. Manuelles Zeichnen und Entfernen einzelner Rechtecke sowie unterschiedliche reale Scanqualitäten sind ergänzend zu prüfen. OCR kann Treffer übersehen; jede Seite muss vor Weitergabe visuell kontrolliert werden. Sehr große oder bösartige PDFs können viel Arbeitsspeicher und Rechenzeit beanspruchen; die 150-MB-Eingabegrenze ist keine Grenze für den entpackten Inhalt. Der synchrone Server kann während OCR/Export keine weiteren Anfragen bearbeiten. Eine globale Dokumentinstanz bedeutet: nur eine Person pro Prozess; mehrere Tabs teilen dasselbe Dokument. Nicht als öffentlicher Mehrbenutzerdienst betreiben.

Der Rasterexport entfernt außerdem Suchbarkeit, interaktive Elemente, digitale Signaturen und Barrierefreiheit. Sichtbare Inhalte außerhalb der markierten Rechtecke bleiben erhalten. Lizenzhinweise zu PyMuPDF und den OCR-Modellen aus der ursprünglichen README sind weiterhin zu beachten.

## Erweiterte Bedienung

Ergänzt: Drag-and-drop einer einzelnen PDF mit Größenprüfung, Live-Suche mit 300 ms Verzögerung und Verwerfen veralteter Antworten, gelbe Vorschau, dokumentweite Übernahme mit Rückgängig und Werkzeugwahl für anklickbare Wörter. Wortpositionen stammen aus PDF-Text sowie OCR und werden in die gedrehte Seitendarstellung umgerechnet. Zwei zusätzliche Integrationstests prüfen ganze Wörter über vier Seiten mit verschiedenen Drehungen und anklickbare OCR-Wortpositionen. JavaScript-Syntaxprüfung bestanden; zusätzliche Browserprüfung siehe unten.

Weitere sinnvolle Verbesserungen: OCR-Abbruch und Wiederaufnahme sowie Prüfregeln für E-Mail-Adressen und IBANs. Diese Erweiterungen sind noch nicht umgesetzt. Automatische Erkennung personenbezogener Daten benötigt eine eigene Trefferkontrolle; OCR allein erkennt Text, nicht dessen Vertraulichkeit.

## Zoom, Trefferliste und mehrere Suchbegriffe

Umgesetzt und mit Chromium/Playwright geprüft: mehrzeilige Suche mit gemeinsamer Trefferliste, Deduplizierung identischer Treffer, Seitensprung zur Fundstelle, Zoom mit erhöhter Rasterauflösung, Zurücksetzen auf Standardbreite, Übernahme aller Treffer und Rückgängig. Der Browser prüft außerdem Wortklick, Exportblockade bei offenen Vorschautreffern, PDF-Download, Dokument schließen und Drag-and-drop. Keine JavaScript-Laufzeitfehler im Test. Ein weiterer Python-Test prüft Zoomauflösung und Ablehnung ungültiger Zoomwerte. Ausstehende Suchen blockieren den Export, damit noch nicht angezeigte Treffer nicht versehentlich übergangen werden.

## Durchsuchbarer OCR-Export

Standardausgabe der Oberfläche ist jetzt eine geschwärzte PDF mit neu erzeugter OCR-Textschicht. Der Endpunkt akzeptiert `searchable: true`; ohne Angabe bleibt für bestehende API-Nutzer der Bildexport erhalten. Ausgangspunkt der Erkennung sind ausschließlich bereits geschwärzte Rasterbilder. Originaltextschichten, ursprüngliche OCR-Caches und Anhänge werden nicht übernommen. Fehler der OCR verhindern die Ausgabe und nennen die Seite.

Zusätzlicher Integrationstest mit Text-PDFs und Scans bei 0/90/180/270 Grad: Der ursprüngliche OCR-Cache enthält den geheimen Testbegriff, die exportierte Textschicht enthält ihn nach Schwärzung nicht. Sichtbare Wörter auf einer separaten Textzeile bleiben durchsuchbar, Pixelproben in den Schwärzungen sind schwarz. Anhänge und Autorenmetadaten fehlen weiterhin. Ein zweiter Test prüft den expliziten Fehlerfall. Der Chromium-Test lädt beide Exportvarianten herunter und prüft deren extrahierbaren Text. Zehn Integrationstests und Browsertest erfolgreich. Die OCR-Genauigkeit bei benachbarten Schwärzungen, kleinen Schriften und realen Scans bleibt qualitätsabhängig; der Test ist keine Vollständigkeitsgarantie.

## Verkleinerung und Textänderungen

Drei Ausgabeprofile: Standard (200 dpi/PNG), Kompakt (150 dpi/JPEG 80) und Klein (100 dpi/Graustufen/JPEG 60). Bei OCR-Ausgaben erfolgt die Erkennung vor Verkleinerung mit mindestens 200 dpi. Die vom OCR-Modul erzeugten Bildobjekte werden durch transparente Platzhalter ersetzt; nur dessen neue Textschicht wird zusätzlich zum komprimierten Seitenbild übernommen. Tests prüfen JPEG-Bildobjekte auch im OCR-Export, tatsächliche Größenreduktion auf einer bildreichen Testseite und unveränderte physische Seitengröße. Einsparungen sind vorlagenabhängig.

Das Textmodul ersetzt ausgewählte Bereiche durch weißen Hintergrund und schwarzen Ersatztext. Vorschau und Export verwenden dieselbe Satzfunktion. Die endgültige Ausgabe rastert die Änderungen; darunterliegende Originalobjekte werden nicht kopiert. Schwärzungen erfolgen nach Textänderungen. Suche und Wortauswahl beachten Ersatztexte und blenden ersetzte Originalstellen aus. Text wird als Klartext escaped; Markup kann nicht eingeschleust werden. Ungültige Bereiche, Seiten, Schriftgrößen, Überlappungen und nicht passende Texte werden abgewiesen.

Vierzehn erfolgreiche Integrationstests: zusätzlich Kompression, neue/entfernte Wörter, Unicode und wörtliches Markup, leere Ersetzungen, Suchkonsistenz, gültige/ungültige Änderungen und Schwärzungen über Ersatztext in sämtlichen Profilen. Der Chromium-Test prüft Bereichsauswahl, fehlerhafte Schriftgröße ohne Übernahme, Vorschau, Suche nach Ersatztext, komprimierten OCR-Download und Rückgängig. Dieser Test läuft unter Linux; Windows-Bedienung und OCR-Qualität bei echten Dokumenten sind damit nicht abschließend geprüft. Kein vollständiger PDF-Layouteditor: feste Bereiche, weiße Hintergründe, Standardschrift, kein automatischer Umbruch auf Folgeseiten.

## Stapel, Dokumentverwaltung und verlustfreies Profil

Ergänzt: unabhängige sequenzielle Stapelsitzung für maximal 20 PDFs / 500 MB, ein geöffnetes Quelldokument pro Job, temporäre fertige Ausgaben, ZIP mit eindeutigen sicheren Dateinamen und CSV-/JSON-Berichten. Fehler, Wiederholung, Stopp nach laufender Datei, Fortsetzen und Neulauf sind im Browser bedienbar. Unveränderte geeignete Textseiten können ohne neue OCR erhalten bleiben. Gemischte Seiten lassen sich vollständig erkennen. Ergebnisse zählen tatsächliche OCR-Aufrufe / erhaltene Textseiten und melden Seiten ohne Text.

Gemeinsame Suchlisten werden zuerst analysiert und erfordern anschließend seitenweise Freigaben der veränderten Dateien. Der Einzeldatei-Editor erhält Seitendrehung, Sortierung, Löschen und fünf Struktur-Rückgängigkeiten. Markierungen und Textrahmen werden mittransformiert. Zusammenführen und Aufteilen mit Bereichsgruppen sind enthalten. Ausgewählte Vorschläge für E-Mail, validierte IBAN und mögliche Telefonnummern sind sowohl einzeln als auch im Stapel übernehmbar; kein automatischer Vollständigkeitsanspruch. Vorlagen bleiben in lokalen Benutzereinstellungen, Suchbegriffe nur bei expliziter Speicheroption.

Das verlustfreie Profil kopiert Originalbilddaten und Vektoren ohne Neuberechnung. Native Schwärzungen entfernen markierte Text-/Bild-/Grafikanteile; nicht betroffene JPEG-Bildstreams und Vektorzeichnungen werden im Test identisch erhalten. Scans können eine zusätzliche OCR-Schicht erhalten, ohne dass ihr Originalbild ausgetauscht wird. Bei gemischten Seiten ergänzt ein erzwungener Lauf fehlenden Scantext und vermeidet OCR-Dubletten bereits vorhandener nativer Wörter. Formulare / Anmerkungen werden in diesem Profil abgewiesen; es gibt keine stille Rasterung. Getroffene Grafikobjekte können ganz entfernt werden. Originalobjekte außerhalb bearbeiteter Bereiche einschließlich möglicher Bild-Metadaten bleiben erhalten; dieses Profil ersetzt keine vollständige rasterbasierte Neuerstellung.

24 Python-Integrationstests bestanden, einschließlich eines 20-Dateien-Stapels, Fehlerfortsetzung und Wiederholung, gemischter Seiten, verlustfreier Bild-/Vektorerhaltung, Freigabeprüfung, Vorschlägen, gespeicherten Einstellungen, Merge/Split und Seitenplan/Rückgängig. Der bisherige Chromium-Test und ein eigener Workflow-Browsertest prüfen echte Downloads, Fehlersimulation, Stoppen/Fortsetzen, gemeinsame Treffer mit Prüfung, Vorlagen, Dokumentfunktionen und bestehende Editorfunktionen. Die genaue plattformspezifische Mac-Buildvalidierung wird separat im GitHub-Workflow nach dem Packen ausgeführt.
