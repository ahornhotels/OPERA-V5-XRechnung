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
-- Nur Endrechnungen. VOID, DEPOSIT, COPY, INTERIM und leerer Dokumenttyp
-- fallen raus.
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
       -- Platzhalter fuer das benutzerdefinierte Kennzeichen an der
       -- Firmenkartei. app/opera.py ersetzt "NULL AS erechnung_kennzeichen"
       -- durch die konfigurierte Spalte (nur UDFC01..UDFC40 zugelassen) —
       -- Oracle laesst Spaltennamen nicht als Bindvariable zu. Steht in der
       -- Konfiguration nichts, bleibt es NULL und die Stufe faellt weg.
       NULL AS erechnung_kennzeichen,
       NVL(f.clpay, 0)                               AS city_ledger,
       n.name_type                                   AS empfaenger_typ,
       adr.country                                   AS empfaenger_land,
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
  LEFT JOIN @SCHEMA@.name_address adr
    ON adr.name_id = n.name_id AND adr.primary_yn = 'Y'
 WHERE f.resort          = :resort
   AND f.document_type   = 'INVOICE'
   AND f.status          = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - :days
)
 WHERE :nur_firmen = 'N' OR firmenbezug <> '-'
 ORDER BY issuedate DESC, bill_no DESC
 FETCH FIRST :hoechstens ROWS ONLY
