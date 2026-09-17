-- anzahlungscodes.sql — Welche Umsatzcodes benutzt DIESES Haus fuer Anzahlungen?
-- Bindvariablen: :resort, :anzahlung_status, :tage
--
-- Zum Nachsehen, nicht zum Entscheiden. Die Anwendung erkennt eine Anzahlung
-- am Belegstatus (STATUS = 'DEPOSIT' am selben FOLIO_NO) und braucht dafuer
-- keine Codes. Diese Abfrage beantwortet die andere Frage: Wie sieht das im
-- eigenen Haus konkret aus, und stimmt die Annahme?
--
-- WARUM NICHT DARAUS EINE LISTE MACHEN: Eine fest eingetragene Codeliste war
-- der vorherige Weg. Sie hatte zwei Fehler, die beide erst an Daten auffielen.
--
--   1. Sie war unvollstaendig. Ueber ein Jahr gemessen fehlten ausgerechnet
--      die drei haeufigsten Codes. Eine Schlussrechnung,
--      die nur darueber angezahlt war, galt als Nullbeleg.
--   2. Sie vermischte zwei Dinge: die Umbuchung der Anzahlung und die
--      ZAHLUNGSART, mit der angezahlt wurde (Karte, Ueberweisung, PayPal).
--      Das Zweite gehoert nicht dazu; deshalb liefert diese Abfrage die
--      Gruppe mit, damit man es unterscheiden kann.
--
-- Es gibt keine Spalte, an der OPERA einen Anzahlungscode kennzeichnet. Das
-- ist geprueft: DEPOSIT_TYPE ist unbenutzt, IND_DEPOSIT_YN markiert die
-- zulaessigen Zahlungsarten, TRX$_GROUPS existiert nicht, und "Deposit" in
-- der Beschreibung ist sprachabhaengig. Die Codes lassen sich nur an den
-- DATEN ablesen — und genau das tut diese Abfrage.

SELECT ft.trx_code,
       MAX(c.description)              AS bezeichnung,
       MAX(c.tc_group)                 AS gruppe,
       MAX(c.tc_subgroup)              AS untergruppe,
       COUNT(*)                        AS buchungen,
       -- 'J' heisst: sieht nach Zahlungsart aus, nicht nach Anzahlungsbuchung.
       -- Solche Zeilen gehoeren nicht in eine Anzahlungsliste.
       CASE WHEN UPPER(MAX(c.tc_group)) IN ('PAY', 'PAYMENT')
            THEN 'J' ELSE 'N' END      AS zahlungsart
  FROM @SCHEMA@.financial_transactions ft
  JOIN @SCHEMA@.folio$_tax f ON f.bill_no = ft.bill_no AND f.resort = ft.resort
  LEFT JOIN @SCHEMA@.trx$_codes c ON c.trx_code = ft.trx_code
 WHERE f.resort = :resort
   AND f.status = :anzahlung_status
   AND f.bill_generation_date >= TRUNC(SYSDATE) - :tage
 GROUP BY ft.trx_code
 ORDER BY buchungen DESC
