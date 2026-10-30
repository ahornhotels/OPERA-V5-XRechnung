-- invoice_nachpruefung.sql — Wie steht ein bereits VERSENDETER Beleg heute in OPERA?
-- Bindvariablen: :bill_no, :folio_no, :resort
--
-- Laeuft einmal am Tag nach dem Tagesabschluss fuer die Belege, die die
-- Anwendung in den letzten Tagen versendet hat (app/ablauf.py, nachpruefen).
-- Gemessen am 30.10.2026 (docs/06_BEFUNDE_LIVE_DB.md): An einer ausgegebenen,
-- gueltigen Rechnung aendert OPERA weder Betraege noch Positionen. Nachtraeglich
-- aendert sich nur zweierlei:
--   - Der Beleg wird storniert: STATUS 'VOID', Betrag 0, TSE-Nummer weg, und
--     meist sofort ein Ersatzbeleg mit neuer Nummer am selben Folio. Spaetestens
--     am Tag nach dem Buchungstag.
--   - Der Profil- oder Zahlerbezug wechselt (NAME_ID, PAYEE_NAME_ID), selten,
--     bis knapp zwei Tage nach der Ausgabe.
--
-- spaetere_belege: gueltige Belege am selben Folio mit hoeherer Nummer, als
-- "Nummer:Betrag" durch Komma getrennt — die Kandidaten fuer den Ersatzbeleg.
-- Ein Verweis vom Ersatz auf das Original gibt es in OPERA nicht.
-- Gueltig heisst OK oder Anzahlungsbeleg (eine stornierte Anzahlung wird als
-- neuer Anzahlungsbeleg ersetzt); interne Umbuchungen nicht, sie verwenden
-- Nummern echter Rechnungen anderer Folios wieder. Nur hoehere Nummern: Ein
-- aelterer gueltiger Beleg am Folio ist kein Ersatz, sondern etwa die
-- Schlussrechnung vor einer stornierten Vorausrechnung (5 von 658 Faellen).
--
-- Der Weg ueber FOLIOS ist Absicht, siehe invoice_deposits.sql. Ein VOID-Beleg
-- selbst hat dort keine Zeile mehr; seine Nachfolger schon.

SELECT f.status                                        AS beleg_status,
       f.fiscal_bill_no,
       f.total_gross,
       NVL(f.payee_name_id, f.name_id)                 AS name_id,
       (SELECT LISTAGG(e.bill_no || ':' || TO_CHAR(e.total_gross, 'FM9999999990.00'), ',')
                 WITHIN GROUP (ORDER BY e.bill_no)
          FROM @SCHEMA@.folio$_tax e
         WHERE e.resort = f.resort
           AND e.bill_no IN (SELECT fo.bill_no
                               FROM @SCHEMA@.folios fo
                              WHERE fo.folio_no = :folio_no)
           AND e.folio_no = :folio_no
           AND e.bill_no > f.bill_no
           AND (e.status = 'OK' OR e.status = :anzahlung_status)
           AND NVL(e.folio_type, '-') <> 'INTERNAL')   AS spaetere_belege
  FROM @SCHEMA@.folio$_tax f
 WHERE f.resort   = :resort
   AND f.bill_no  = :bill_no
   AND f.folio_no = :folio_no
