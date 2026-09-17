# Alle Einstellungen

Vollständige Übersicht über `config/app.json`. Die Vorlage
`config/app.example.json` erklärt die heiklen Einträge noch ausführlicher; was
dort fehlt, wird beim Start aus ihr ergänzt.

**Zum Lesen:** Die meisten Einstellungen sind unauffällig. Die Spalte
*Bemerkung* sagt, wo es darauf ankommt — und **fett** steht, was in einem
zweiten Haus anders sein wird als hier.

---

## `server` — Erreichbarkeit

| Einstellung | Bedeutung |
|---|---|
| `host` | Adresse, auf der gelauscht wird. `0.0.0.0` heißt: im ganzen Hausnetz erreichbar |
| `port` | Vorgabe 8022 |
| `erlaubte_netze` | **Positivliste in CIDR-Schreibweise.** Anfragen von außerhalb werden abgewiesen, bevor die Anmeldung greift. Eine leere Liste lässt alles zu — die Anwendung weigert sich, sich selbst auszusperren |

## `datenbank` — der lesende Zugang zu OPERA

| Einstellung | Bedeutung |
|---|---|
| `host`, `port`, `service_name` | Oracle-Verbindung |
| `benutzer`, `passwort` | **Eigener Benutzer mit `SELECT`-Recht.** Kein Schema-Eigner, keine Schreibrechte. Das Passwort wird beim ersten Start verschlüsselt |
| `schema` | **Das Schema, in dem die OPERA-Tabellen liegen.** Fast immer `OPERA`; leer bedeutet `OPERA`. Der Name geht in jede Abfrage und wird vorher geprüft |
| `thick_mode` | Auf `true`, wenn die Datenbank ein altes Passwortverfahren nutzt (`DPY-3015`). Braucht dann den Oracle-Client |
| `oracle_client_pfad` | Pfad zum Instant Client, nur bei `thick_mode` |

## `property` — das Haus und was OPERA nicht liefert

| Einstellung | Bedeutung |
|---|---|
| `resort` | **Das Resortkürzel.** In einer Datenbank liegen oft mehrere Properties; Reservierungszentrale und Demo-Mandanten müssen draußen bleiben |
| `haus` | Name für die Kopfzeile der Oberfläche |
| `ust_id` | **USt-IdNr. des Hauses (BT-31).** OPERA führt sie nicht — weder `RESORT.VAT_ID` noch `PROPERTY_TAX_NO` sind gefüllt |
| `kontakt_name`, `kontakt_telefon`, `kontakt_email` | BT-41/42/43. **Telefon und E-Mail sind Pflicht** (BR-DE-6/7); fehlen sie, lehnt der Validator ab |
| `iban`, `bic`, `kontoinhaber` | Bankverbindung für BG-17 |
| `zahlungsziel_tage` | Fälligkeit, gerechnet ab Rechnungsdatum |
| `gastzeile` | BT-22: die Zeile, die sagt, wer im Haus war. Platzhalter `{gast} {zimmer} {anreise} {abreise}`. Leer schaltet sie ab |
| `positionen` | Wie die Positionen stehen: `automatisch`, `A` (jede Buchung einzeln), `B` (zusammengefasst), `C` (je Gast). Siehe [14_POSITIONEN.md](14_POSITIONEN.md) |
| `positionsbemerkung` | **Welche Felder der Buchung als Bemerkung an der Position stehen (BT-127).** Vorgabe `remark` — das ist das Feld, das OPERA in der Buchungsmaske „Supplement" nennt. `reference` **nicht** einschalten: Systemprotokoll mit fremden Gastnamen und Rufnummern |
| `gastzuordnung_bestaetigt` | Solange `false`, verschickt die Automatik keine Rechnung in der Darstellung je Gast. Der Rückweg, falls `sql/discovery/06_positionen_gast.sql` im eigenen Haus ein anderes Bild zeigt |
| `buyerreference_vorlage` | BT-10 ist Pflicht (BR-DE-15), aber nur Behörden haben eine Leitweg-ID. Diese Vorlage greift, wenn nichts anderes etwas hergibt |
| `buyerreference_ersatz` | Letzter Rückfall: `reservierungsnummer`, `rechnungsnummer`, `debitornummer` oder `kundenname` |
| `kundenreferenz_als_buyerreference` | `CUSTOM_REFERENCE` der Reservierung als BT-10 verwenden. **Vorgabe aus** — dort stehen meist Buchungsnummern aus dem Channel Manager, und eine solche Nummer sieht nach einer echten Bestellnummer aus, ohne eine zu sein |
| `mitgliedschaftstyp_leitweg` | **Mitgliedschaftstyp am Profil, der die Leitweg-ID trägt** |
| `mitgliedschaftstyp_erechnung` | Kennzeichnet übrige Firmenkunden, die eine E-Rechnung bekommen sollen |
| `udf_leitweg` | **Benutzerdefiniertes Feld der FIRMENkartei mit der Leitweg-ID** (`UDFC01`–`UDFC40`). Mitgliedschaften taugen dafür nicht: OPERA bietet sie nur an der Individualkartei an. Leer schaltet die Stufe ab |
| `udf_erechnung` | Benutzerdefiniertes Feld als E-Rechnungs-Kennzeichen. Leer schaltet ab |
| `udf_erechnung_bedeutung` | Was ein Eintrag dort bedeutet: `schliesst_aus` (Vorgabe) nimmt gekennzeichnete Karteien heraus, `erlaubt` nimmt nur gekennzeichnete auf. `erlaubt` ist erst praktikabel, wenn jemand die Karteien gepflegt hat — sonst geht gar nichts hinaus |

## `xrechnung` — die Fassung des Standards

| Einstellung | Bedeutung |
|---|---|
| `version` | Welche Fassung erzeugt wird. Heute ist nur `3.0.2` möglich. Die Einstellung wählt Vorlage, `CustomizationID` (BT-24) und das Regelwerk des Validators zusammen — ein Umstellen an nur einer dieser Stellen ergäbe ein Dokument, das sich selbst widerspricht |

## `mail` — Versand

| Einstellung | Bedeutung |
|---|---|
| `aktiv` | Schaltet den Versand ab, ohne die Zugangsdaten zu verlieren |
| `smtp_host`, `smtp_port`, `verschluesselung` | `starttls`, `ssl` oder `keine`. **Ohne Verschlüsselung wird nicht angemeldet** — das Zertifikat wird geprüft |
| `benutzer`, `passwort` | Anmeldung am Mailserver; das Passwort wird verschlüsselt |
| `absender`, `absender_name` | Absender der Rechnungsmail |
| `bcc` | **Blindkopie bei jeder verschickten Rechnung.** Der Nachweis, dass sie hinausging |
| `bcc_city_ledger` | Zweite Blindkopie nur für Rechnungen über das Debitorenkonto — die gehen die Debitorenbuchhaltung an |
| `erlaubte_empfaenger` | **Sicherheitsnetz: Solange hier etwas steht, geht keine Mail an eine andere Adresse.** Zu Beginn die eigenen Domains, erst leeren, wenn wirklich an Kunden versendet wird |
| `betreff`, `text` | Vorlagen mit `{bill_no}`, `{issuedate}`, `{absender_name}`. Der Absatz zu § 14c UStG sollte stehen bleiben |
| `pdf_ordner`, `pdf_muster` | Wo die Folio-PDFs liegen, falls OPERA sie ablegt. Leer heißt: nur das XML geht mit |

## `auswahl` — welche Rechnungen überhaupt in Frage kommen

| Einstellung | Bedeutung |
|---|---|
| `zeitraum_tage` | Wie weit zurück eingelesen wird |
| `hoechstens` | Obergrenze je Lauf, wirkt auf die Belege **mit** Firmenbezug |
| `firmenprofile` | **Welche Profiltypen als Firma gelten** (`COMPANY`, `TRAVEL_AGENT`, …). In jedem Haus anders benannt |
| `reservierungsfirma_aufnehmen` | Rechnungen aufnehmen, bei denen die Firma nur an der Reservierung hängt |
| `reservierungsfirma_pruefen` | Und sie zur Sichtprüfung vorlegen, statt automatisch zu versenden. **Dringend anlassen:** Dort zahlt oft eine Privatperson |
| `nur_inland` | Ausländische Empfänger auslassen |
| `inlandskennzeichen` | Welches Länderkennzeichen als Inland gilt |
| `mindestbetrag_brutto` | Kleinbeträge auslassen |
| `anzahlung_status` | **Wie OPERA einen Anzahlungsbeleg kennzeichnet.** `FOLIO$_TAX.STATUS` kennt nur `OK`, `DEPOSIT`, `VOID`, `ZERO` — englisch auch in deutschen Installationen. Davon hängt ab, ob eine Schlussrechnung mit Kopfbetrag 0,00 als gedeckt erkannt oder als Nullbeleg zurückgelegt wird |
| `anzahlungscodes` | **Zusätzliche** Umsatzcodes, leer ist der Normalfall. Nur nötig, wenn ein Haus Anzahlungen als Umbuchung *innerhalb* desselben Belegs führt statt als eigenen Beleg. Welche Codes vorkommen, zeigt die Konfigurationsseite auf Knopfdruck |

## `automatik` — der unbeaufsichtigte Betrieb

| Einstellung | Bedeutung |
|---|---|
| `aktiv` | Schaltet den Takt ein |
| `poll_minuten` | Abstand zwischen zwei Durchläufen |
| `wartezeit_minuten` | **Wie lange eine Rechnung liegen bleibt, bevor sie versendet wird.** Die Gelegenheit, einen Fehler in OPERA noch zu korrigieren |
| `nur_mit_firmenbezug` | Nur Rechnungen mit Firmenbezug einlesen |
| `city_ledger_versenden` | **Vorgabe aus.** Debitorenrechnungen sind nicht bezahlt, sondern stehen offen — sie ohne Blick hinausgehen zu lassen ist etwas anderes als bei einer bezahlten Gastrechnung |
| `empfaenger_automatisch` | Die bestgeeignete Adresse selbst wählen |
| `max_pro_lauf` | Obergrenze für Versände je Durchlauf |
| `testlauf` | **Erzeugt und prüft, verschickt aber nichts.** Beim Einrichten eine Woche anlassen |

## `ablage` — wo die Rechnungen liegen

| Einstellung | Bedeutung |
|---|---|
| `xml_ordner` | Die erzeugten XRechnungen |
| `archiv_ordner` | Die versendeten. **Aufbewahrungspflichtig** — relative Pfade gelten gegenüber der Installation, nicht dem Programm |

## `validierung` — die Prüfung mit dem KoSIT-Validator

| Einstellung | Bedeutung |
|---|---|
| `aktiv` | Prüfen überhaupt |
| `pflicht` | **Ohne bestandene Prüfung kein Versand.** Lässt sich nicht einschalten, solange `aktiv` aus ist |
| `kosit_jar`, `kosit_szenarien`, `java` | Pfade; der Installer setzt sie |
| `daemon` | Der Validator braucht rund zwölf Sekunden zum Start, die Prüfung danach unter einer Sekunde. Im Daemon-Betrieb läuft er einmal und hält die Regeln geladen — bei einem vollen Durchlauf der Unterschied zwischen Stunden und Minuten. Er lauscht nur auf `127.0.0.1` |

## `update` — Aktualisierung

| Einstellung | Bedeutung |
|---|---|
| `aktiv` | Schaltet die Selbstaktualisierung ab |
| `repo`, `zweig` | **Von wo die Aktualisierungen kommen**, in der Form `Konto/Name`. Wer die Anwendung abzweigt, trägt sein eigenes Repository ein |
| `token` | Nur bei einem privaten Repository nötig, mit Leserecht auf Inhalte |
| `automatisch_pruefen` | Alle sechs Stunden nachsehen und es Verwaltern melden. **Eingespielt wird nie von selbst** — das bleibt ein Knopfdruck |

---

## Nicht in dieser Datei: das Erscheinungsbild

Farben und Schriften des eigenen Hauses gehören in den **Bestand**, nicht in
die Konfiguration und nicht ins Programm:

```
branding/stil.css            wird nach der mitgelieferten Datei geladen
branding/schriften/*.woff2   erreichbar unter /branding/schriften/...
```

Meist genügen drei Variablen:

```css
:root{--akzent:#445566;--akzent-hell:#8899aa;--kopf:#1a1a1a}
```

Der Ort ist mit Absicht gewählt: Dort überlebt das Erscheinungsbild jede
Aktualisierung. Die Statusfarben folgen bewusst keinem Markenton — sie sind
Bedeutung, keine Gestaltung.
