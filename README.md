# OPERA V5 XRechnung

**Macht aus einer abgeschlossenen OPERA-Rechnung eine XRechnung und verschickt
sie.** Für Oracle OPERA V5 on premise, Standard XRechnung 3.0.2 (EN 16931 /
UBL 2.1), mit Weboberfläche und Automatikbetrieb.

**Sie ändert nichts in OPERA.** Der Datenbankzugriff ist ausschließlich lesend.

---

## Wozu

Seit 2025 müssen Rechnungen zwischen Unternehmen in Deutschland elektronisch
sein — ein PDF genügt nicht mehr. OPERA V5 kann das nicht. Diese Anwendung
schließt die Lücke, ohne dass am PMS etwas geändert wird.

## Was sie tut

1. **Liest** abgeschlossene Rechnungen mit Firmenbezug aus OPERA
2. **Baut** daraus die XRechnung — mit Anzahlungen, Steuergruppen, Abschlägen
   und zusammengefassten Positionen
3. **Prüft** zweifach: rechnerisch gegen die EN-16931-Regeln und mit dem
   offiziellen **KoSIT-Validator**. Was nicht durchgeht, geht nicht hinaus
4. **Verschickt** sie an den Empfänger, mit Blindkopie und Protokoll

Dazwischen liegt das, was solche Anwendungen üblicherweise nicht haben: eine
**Sichtprüfung**. Ist unklar, ob die Rechnung wirklich der Firma gehört oder
dem Gast, der sie selbst bezahlt hat, wird sie nicht automatisch versendet,
sondern vorgelegt.

## Was sie besonders macht

| | |
|---|---|
| **Positionen wahlweise** | einzeln, nach Leistung und Preis zusammengefasst, oder **je Gast mit Zimmer und Zeitraum** — Letzteres für Gruppen- und Reiseveranstalterrechnungen, die der Empfänger auf seine Reisenden aufteilen können muss |
| **Anzahlungen** | über die Folio-Klammer erkannt, nicht über eine gepflegte Codeliste: Anzahlungen sind eigene Belege am selben Folio. Das gilt in jedem Haus |
| **Supplement-Feld** | was in der Buchungsmaske als Zusatztext steht, erscheint an der Position (BT-127) — vollständig, wie auf der gedruckten Rechnung |
| **Kein Doppelversand** | Statussperre im Server; ein Versand mit unklarem Ausgang wird als solcher gemeldet, statt stillschweigend zu gelten |
| **Aktualisierung** | jeder Stand in eigenem Verzeichnis, Umschalten in einem Schritt, Zurückgehen auf Knopfdruck. Standzeit: eine Sekunde |
| **Selbsttest** | rund 760 Prüfungen, **ohne Datenbank**. Zu jeder gehört die Frage, ob sie überhaupt rot werden kann |

## Voraussetzungen

| | |
|---|---|
| Datenbank | Oracle OPERA V5, lesender Zugang (eigener Benutzer, nur `SELECT`) |
| Server | Rocky Linux 9/10 oder Windows Server, Python 3.11+ |
| Validator | KoSIT-Validator; der Installer lädt ihn, JRE 17+ genügt |

## Einrichtung

```sh
sudo ./install/installieren.sh          # Linux
install\INSTALLIEREN.cmd                # Windows, als Administrator
```

Danach `config/app.json` ausfüllen — die Vorlage erklärt jeden Eintrag im
Klartext. Schritt für Schritt: **[INSTALLATION.md](INSTALLATION.md)**, für die
tägliche Arbeit **[HANDBUCH.md](HANDBUCH.md)**.

**Vor dem ersten Lauf** gehören ein paar Werte geprüft, die vom eigenen Haus
abhängen: Schema, Resortkürzel, welche Profiltypen als Firma gelten, in
welchem Feld die Leitweg-ID steht. Die Skripte unter `sql/discovery/`
beantworten das an den eigenen Daten — rein lesend.

---

## Ehrlich zum Stand

Diese Anwendung läuft produktiv in **einem** Haus, und alles hier ist gegen
**eine** OPERA-Installation geprüft. Wo eine Annahme nur dort belegt ist,
steht es im Quelltext dabei — und sie ist einstellbar, damit ein zweites Haus
sie ändern kann, statt den Code anzufassen. Rückmeldungen aus anderen
Installationen sind willkommen.

Nicht enthalten: Gutschriften und Rechnungen mit negativem Betrag. Sie werden
erkannt und zurückgelegt, nicht falsch verschickt.

## Herkunft und Lizenz

Folgt dem Bauplan von **XRechnung_Slim** (Oracle Suite8, GPLv3) desselben
Autors; übernommen sind vor allem die gegen den KoSIT-Validator erarbeiteten
Normalisierungsregeln, im Quelltext als solche gekennzeichnet. Neu ist alles,
was mit OPERA zu tun hat.

**GNU General Public License v3.0** — siehe [LICENSE](LICENSE). Benutzen,
ändern und weitergeben ist erlaubt, auch gewerblich; wer eine geänderte
Fassung weitergibt, gibt den Quelltext mit. **Keine Gewährleistung** — für die
Richtigkeit der erzeugten Rechnungen ist der Betreiber verantwortlich.

Copyright (C) 2026 AHORN Hotels
