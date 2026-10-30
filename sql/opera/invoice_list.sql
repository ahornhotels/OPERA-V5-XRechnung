-- invoice_list.sql — Kandidatenliste fuer die Arbeitsliste und die Automatik
-- Bindvariablen: :days, :resort, :leitweg_typ, :erechnung_typ, :hoechstens,
--                :nur_firmen ('J' = nur Belege mit Firmenbezug)
--
-- WICHTIG: Der Firmenfilter steht IN der Abfrage, nicht erst danach im Code.
-- Sonst greift die Obergrenze auf alle Rechnungen des Hauses — bei rund 82 am
-- Tag deckten 500 Zeilen nur sechs Tage ab, und ein 30-Tage-Fenster lieferte
-- stillschweigend nur die letzte Woche. Genau das ist beim ersten echten Lauf
-- passiert: 86 Belege aus acht Tagen statt aus dreissig.
--
-- Jeder gueltige Beleg ist eine Rechnung (docs/16_OPERA_OHNE_DOCUMENT_TYPE.md):
-- Schluss-, Voraus- und Zwischenrechnungen mit STATUS 'OK', dazu die
-- Anzahlungsbelege (:anzahlung_status, Typ 380 mit Vermerk Anzahlungsrechnung). Die Belegart
-- entscheidet nicht mehr — im gemessenen Haus enthaelt jede Buchung genau
-- einen Beleg, Voraus- und Schlussrechnung rechnen verschiedene Buchungen ab.
-- Draussen bleiben VOID und ZERO (Status), interne Umbuchungen (FOLIO_TYPE)
-- und 'COPY OF INVOICE', bis das Haus geklaert hat, was dieser Belegtyp ist.
-- Ob ein Beleg TSE-signiert ist (FISCAL_BILL_NO), prueft app/ablauf.py: Ein
-- Haus ohne TSE haette sonst eine leere Liste.
--
-- FIRMENBEZUG — die zentrale Unterscheidung:
--   'EMPFAENGER'   Der Rechnungsempfaenger selbst ist eine Firma: Firmenprofil,
--                  Debitorenkonto oder ausdrueckliche Kennzeichnung. Verlaesslich,
--                  darf automatisch laufen.
--   'RESERVIERUNG' An der Buchung haengt eine Firma, bezahlt hat aber eine
--                  Privatperson (COMPANY_NAME beschreibt die Reservierung, nicht
--                  den Empfaenger). Aufnehmen — aber nur nach Sichtpruefung
--                  versenden. Im geprueften Bestand rund jede zehnte Rechnung.
--   '-'            kein Anhaltspunkt.

SELECT * FROM (
SELECT f.bill_no,
       f.invoice_no,
       TO_CHAR(f.bill_generation_date, 'YYYY-MM-DD') AS issuedate,
       f.total_net,
       f.total_gross,
       f.account_code,
       -- Die Profilnummer, damit sich Belege desselben Kunden buendeln lassen.
       -- Ueber den NAMEN geht das nicht: Belege ohne Kundennamen landeten sonst
       -- alle in einem Topf, 28 Stueck von verschiedenen Kunden.
       NVL(f.payee_name_id, f.name_id)               AS name_id,
       f.company_name,
       -- Fuer die Spalte "Kunde" der Arbeitsliste. Fehlte, dann blieb bei
       -- Belegen ohne Firmennamen die Spalte leer.
       f.payee_name,
       f.status                                      AS beleg_status,
       f.document_type,
       f.fiscal_bill_no,
       -- Platzhalter fuer das benutzerdefinierte Kennzeichen an der
       -- Firmenkartei. app/opera.py ersetzt "NULL AS erechnung_kennzeichen"
       -- durch die konfigurierte Spalte (nur UDFC01..UDFC40 zugelassen) —
       -- Oracle laesst Spaltennamen nicht als Bindvariable zu. Steht in der
       -- Konfiguration nichts, bleibt es NULL und die Stufe faellt weg.
       NULL AS erechnung_kennzeichen,
       NVL(f.clpay, 0)                               AS city_ledger,
       n.name_type                                   AS empfaenger_typ,
       -- Als Unterabfrage, nicht als Join: Sie laeuft erst fuer die
       -- Ergebniszeilen. Der Join las NAME_ADDRESS vollstaendig (619.000
       -- Zeilen, gemessen 30.10.2026), bevor die Obergrenze griff.
       (SELECT MAX(adr.country)
          FROM @SCHEMA@.name_address adr
         WHERE adr.name_id    = NVL(f.payee_name_id, f.name_id)
           AND adr.primary_yn = 'Y')                 AS empfaenger_land,
       -- Kennzeichnungen am Profil
       (SELECT MAX(m.membership_card_no)
          FROM @SCHEMA@.memberships m
         WHERE m.name_id         = NVL(f.payee_name_id, f.name_id)
           AND m.membership_type = :leitweg_typ
           AND (m.inactive_date   IS NULL OR m.inactive_date   > SYSDATE)
           AND (m.expiration_date IS NULL OR m.expiration_date > SYSDATE)) AS leitweg_id,
       (SELECT COUNT(*)
          FROM @SCHEMA@.memberships m
         WHERE m.name_id         = NVL(f.payee_name_id, f.name_id)
           AND m.membership_type IN (:leitweg_typ, :erechnung_typ)
           AND (m.inactive_date   IS NULL OR m.inactive_date   > SYSDATE)
           AND (m.expiration_date IS NULL OR m.expiration_date > SYSDATE)) AS kennzeichen,
       -- Woraus sich der Firmenbezug ergibt
       CASE
         WHEN f.account_code IS NOT NULL
           OR n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') /*FIRMENPROFILE*/
           OR EXISTS (SELECT 1 FROM @SCHEMA@.memberships m
                       WHERE m.name_id = NVL(f.payee_name_id, f.name_id)
                         AND m.membership_type IN (:leitweg_typ, :erechnung_typ)
                         AND (m.inactive_date   IS NULL OR m.inactive_date   > SYSDATE)
                         AND (m.expiration_date IS NULL OR m.expiration_date > SYSDATE))
              THEN 'EMPFAENGER'
         WHEN f.company_name IS NOT NULL
              THEN 'RESERVIERUNG'
         ELSE '-'
       END                                           AS firmenbezug,
       -- Haengt am selben Folio ein Anzahlungsbeleg (STATUS = 'DEPOSIT')?
       -- Nur ein Hinweis, kein Ausschluss. Er entscheidet aber darueber, ob
       -- eine Schlussrechnung mit Kopfbetrag 0,00 in die Sichtpruefung geht
       -- oder als Nullbeleg zurueckgelegt wird — deshalb muss er stimmen.
       CASE WHEN EXISTS (SELECT 1 FROM @SCHEMA@.folio$_tax d
                           WHERE d.resort = f.resort
                             AND d.bill_no IN (SELECT fo.bill_no
                                                 FROM @SCHEMA@.folios fo
                                                WHERE fo.folio_no = f.folio_no)
                             AND d.bill_no <> f.bill_no
                             AND d.status   = :anzahlung_status) /*ODER_CODES*/
            THEN 'N' ELSE 'J' END                    AS ohne_anzahlung
  FROM @SCHEMA@.folio$_tax f
  LEFT JOIN @SCHEMA@.name n
    ON n.name_id = NVL(f.payee_name_id, f.name_id)
 WHERE f.resort          = :resort
   AND (f.status = 'OK' OR f.status = :anzahlung_status)
   AND NVL(f.document_type, '-') <> 'COPY OF INVOICE'
   -- Interne Umbuchungen zwischen Folios sind keine Rechnungen an Gaeste. Sie
   -- verwenden obendrein Belegnummern echter Rechnungen wieder (invoice_folio.sql).
   AND NVL(f.folio_type, '-') <> 'INTERNAL'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - :days
)
 WHERE :nur_firmen = 'N' OR firmenbezug <> '-'
 ORDER BY issuedate DESC, bill_no DESC
 FETCH FIRST :hoechstens ROWS ONLY
