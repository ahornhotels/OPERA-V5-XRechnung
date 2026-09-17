# Netzzugriff und Anmeldung

**Anforderung:** Die Oberfläche muss von jedem PC im lokalen Netz erreichbar
sein, geschützt durch Benutzername und Passwort.

Das ist eine Abweichung von der Suite8-Vorlage: die bindet bewusst auf
`127.0.0.1` und hat **gar keine Anmeldung** — wer am Server sitzt, darf alles.
Sobald die Oberfläche im Netz steht, ist das nicht mehr tragbar: sie zeigt
Rechnungsdaten, Kundenstammdaten und die Konfiguration inklusive
Datenbank-Zugangsdaten.

## Entwurf

**Bindung.** `0.0.0.0:8022` statt `127.0.0.1`, dazu eine Positivliste erlaubter
Netze in der Konfiguration (z. B. `10.0.0.0/8`) — Anfragen von außerhalb
werden abgewiesen, bevor die Anmeldung überhaupt greift. Zusätzlich die
Windows-Firewall auf das Hausnetz beschränken.

**Anmeldung.** Eigene, kleine Logik — kein Fremdsystem, keine Abhängigkeit:

- Benutzer in `config/users.json`, Passwort als **Argon2id**- oder
  **bcrypt**-Hash (nie im Klartext, nie umkehrbar verschlüsselt).
- Anmeldung setzt ein Sitzungs-Cookie: `HttpOnly`, `SameSite=Strict`,
  `Secure` sobald HTTPS steht. Sitzungsschlüssel zufällig aus `secrets.token_urlsafe`.
- Sitzungen serverseitig in einer Datei bzw. SQLite, mit Ablauf (z. B. 8 Stunden)
  und Abmeldung.
- **Bremse gegen Rateversuche:** nach 5 Fehlversuchen je Benutzer/IP eine
  Minute Sperre, danach exponentiell. Fehlversuche ins Audit-Log.
- Zwei Rollen genügen: **Ansehen** (Status, Rechnungen, Fehler) und
  **Verwalten** (Konfiguration, Kundenstamm, Nachlauf auslösen).
- Jede schreibende Aktion mit Benutzername ins bestehende Audit-JSONL.

**Transport.** Ohne HTTPS wandert das Passwort im Klartext durchs Hausnetz.
Zwei Wege:

1. **Selbstsigniertes Zertifikat** direkt im Dienst (uvicorn kann das), Zertifikat
   einmalig auf den Arbeitsplätzen als vertrauenswürdig hinterlegen. Schlank,
   aber Zertifikatspflege am Client.
2. **Interne CA / vorhandener Reverse Proxy**, falls im Haus vorhanden — sauberer,
   wenn die IT das ohnehin betreibt.

Bis HTTPS steht: Anmeldung trotzdem aktiv, aber im Klartextbetrieb nur im
Hausnetz und mit dem Wissen, dass ein Mitschnitt das Passwort zeigt.

**Was nicht schützenswert erscheint, es aber ist.** In der Konfiguration steht
das (verschlüsselte) Datenbank-Passwort. Die Oberfläche darf es **nie**
zurückliefern — nur „gesetzt/nicht gesetzt" anzeigen und überschreiben lassen.
Das gilt auch für den Update-Token.

## Aufwand

Überschaubar: Die Vorlage ist FastAPI. Anmeldung, Sitzungen und Rollen sind eine
Middleware plus zwei Endpunkte plus eine Anmeldeseite — ein überschaubarer
Baustein, aber einer, der von Anfang an dazugehört und nicht nachgerüstet wird.

## Offen

- Sollen die Anmeldedaten eigenständig sein, oder soll später gegen das
  Active Directory geprüft werden? (LDAP wäre nachrüstbar, die eigene Logik
  bleibt als Rückfall.)
- Wer bekommt „Verwalten" — nur die Buchhaltung, oder auch die IT?
