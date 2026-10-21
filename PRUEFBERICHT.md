# Prüfung und Nachbau

Grundlage: bereitgestellte Datei PDF-Schwaerzer(1).zip. Quellcode und deutsche/englische OCR-Modelle wurden übernommen; macOS-Metadaten und kompilierter Python-Cache wurden ausgelassen.

## Änderungen

- Rechnerabhängigen Python-Pfad durch eine projektlokale virtuelle Umgebung ersetzt; Startskript für POSIX-Shells.
- Headless-Start mit --no-browser ergänzt.
- Ungültige Seitenzahlen und negative Inhaltslängen werden abgewiesen.
- Export prüft sämtliche Markierungen vor Verarbeitung. Markierungen für nicht vorhandene Seiten werden nicht mehr stillschweigend ignoriert.
- Automatisierte Integrationstests und Git-Ausschlüsse ergänzt.

## Verifiziert

Python 3.12, PyMuPDF 1.26.7, Pillow 13.0.0. Zehn erfolgreiche Integrationstests mit mehreren Unterfällen: HTTP-Token, Vorschau, Textsuche und Rasterexport bei 0/90/180/270 Grad, OCR bei 0/90 Grad, Dokument schließen und OCR-Cache leeren, ungültige Anfragen. Der Bild-PDF-Export enthält keine extrahierbare Textschicht, keinen Test-Anhang und keine ursprüngliche Autorenangabe. Eine Pixelprobe im markierten Bereich ist schwarz. pip check meldet keine defekten Abhängigkeiten.

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
