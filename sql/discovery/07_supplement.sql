-- 07_supplement.sql — Wo steht der Text aus dem Feld "Supplement"?
-- Nur lesend. Fuer die Session mit dem lesenden DB-Zugang.
-- DEFINE OPERA_OWNER = OPERA
-- DEFINE RESORT = <Ihr Resortkuerzel>
-- DEFINE TAGE = 30
--
-- ==================== BEANTWORTET AN EINER INSTALLATION ======================
-- DAS SUPPLEMENT-FELD IST FINANCIAL_TRANSACTIONS.REMARK.
--     Bewiesen an Beleg 1400001 (bill_no; invoice_no 129795), den das Haus
--     genannt hat: vier Buchungen trx_code 2920 "Conference Center technical
--     equipment", je 230,00 brutto, und in REMARK steht
--         trx_no 19000001  "Beamer Raum Lissabon / Muster Pharma GmbH"
--         trx_no 19000002  "Beamer Raum Lissabon / Muster Technik AG"
--         trx_no 19000003  "Beamer Raum Lissabon / Reisedienst Nord"
--         trx_no 19000004  "Beamer Raum Lissabon / Beispiel Chemie GmbH"
--     REFERENCE traegt dort nur "CHECK# 1000001 [1]", O_TRX_DESC ist leer.
--     Eine Suche ueber ALLE Textspalten nach dem WERT trifft genau REMARK.
--     Die Anwendung liest REMARK als Vorgabe — der Text steht damit als
--     Bemerkung an der Position (BT-127) auf der XRechnung.
-- ZUR STICHPROBE: REMARK wirkte in 30 Tagen Firmenrechnungen mit 3,6 %
--     Fuellung wie eine interne Notiz. Die Grundgesamtheit war falsch — das
--     sind fast nur Uebernachtungen. Bei Konferenzcodes: 2904 63,1 %,
--     2910 59,4 %, 2920 53,9 %, 2900 44,5 %, 2905 41,4 %. Inhalte: Genf,
--     Berlin, Beamer, Flipchart, Raummiete, Tagungspauschale.
-- OFFEN: nur noch die Bestaetigung, dass die OPERA-MASKE dieses Feld
--     "Supplement" nennt. Dass die Spalte den Text traegt, ist bewiesen.
--
-- Was auf dem Weg dorthin ebenfalls geklaert wurde:
-- Was dabei sicher geklaert wurde (gilt weiter):
--   * Eine Spalte SUPPLEMENT gibt es im ganzen Schema nur in Druck-, Vorschau-
--     und Export-Objekten (FOLIO_DETAIL, WORK_DOC_FOLIO_DETAIL,
--     GUI_INVOICE_VIEW, EXP_EFOLIO_TRANS_DETAIL). FINANCIAL_TRANSACTIONS
--     hat sie nicht.
--   * FOLIO_DETAIL ist eine View auf FOLIO_DETAIL_E, und die Tabelle hat
--     NULL Zeilen. Sie wird beim Drucken gefuellt und wieder geleert.
--   * EXP_FINANCIAL_TRANSACTIONS.TRX_SUPPLEMENT ist kein Zugang zur Buchung,
--     sondern eine Projektion auf REPORT_TABLE ueber SYS_CONTEXT(...EXPORT_ID);
--     ohne laufenden Export leer.
-- BELEGUNG der drei Kandidaten (30.600 Erloeszeilen, 30 Tage):
--     REMARK 3,6 % (interne Kurznotizen) | REFERENCE 91,8 % (94,6 % Systemtext)
--     O_TRX_DESC 63,8 % (urspruengliche Buchungsbezeichnung)
-- WARNUNG: 14,9 % der belegten REFERENCE-Werte enthalten
--     "Routed From <Name> Of Room <Nr>" — Name und Zimmer eines FREMDEN
--     Gastes. Betroffen waeren 77 von 956 Firmenrechnungen (jede zwoelfte).
--     Die Anwendung entfernt das (opera._ohne_fremden_gast) und haelt den
--     Versand an, falls es doch durchkommt. Die Vorgabe ist seither KEIN Feld.
-- WO ER WIRKLICH LEBT (Programmtext RESERVATION_NAME_JRNL_TRIG Z. 202:
--     in_supplement => v_fixed_charges.supplement): an der DAUERBUCHUNG bzw.
--     am TELEFONAT, nicht an der erzeugten Einzelbuchung.
--     FIXED_CHARGES 29.076 Zeilen / 35,8 % mit Supplement
--     IFC_CALL_HIST 1.257.228 Zeilen / 98,1 % mit Supplement
--     FOLIO_DETAIL_E, WORK_DOC_FOLIO_DETAIL, BILL_ITEM_TEMP: je 0 Zeilen
--     Fuer alle uebrigen Buchungsarten gibt es kein gespeichertes Supplement.
-- ENTSCHIEDEN AM 16.09.2026: Aus FIXED_CHARGES wird NICHT gelesen. Der Text
--     gehoert zur Dauerbuchung, nicht zu der Leistung auf der Rechnung — er
--     waere fuer diese Position die falsche Aussage. Keine Abfrage unter
--     sql/opera/ ruehrt FIXED_CHARGES oder IFC_CALL_HIST an.
-- ZWEITE WARNUNG — RUFNUMMERN: Fuer Telefonbuchungen baut OPERA das Supplement
--     als `ft.reference AS supplement` (View FT_HBCALLS_VIEW). In
--     IFC_CALL_HIST tragen 49.967 von 50.000 geprueften Zeilen eine
--     Ziffernfolge ab 5 Stellen — die gewaehlte Nummer. Die Anwendung laesst
--     eine Bemerkung mit so einer Ziffernfolge deshalb ganz wegfallen.
-- OFFEN: nur noch die Kuer unten — schreibt OPERA den Text bei einer normalen
--     Buchung doch in ein anderes Feld? Dafuer braucht es eine Buchung mit
--     bekanntem Text. Solange die aussteht, lautet die Antwort: nein.
-- ==============================================================================
--

PROMPT == 1. Eine bekannte Buchung: welche Spalte traegt den Text? ==
-- BEKANNTER FALL aus dem Haus (16.09.2026): Rechnung 1400001 traegt Buchungen
-- "Conference Center technische Ausstattung intern" mit dem Supplement-Text
-- "Beamer Raum Lissabon". Damit laesst sich die Spalte ueber den WERT finden:
--     SELECT * FROM opera.financial_transactions WHERE bill_no = 1400001;
-- und nachsehen, in welcher Spalte "Beamer Raum Lissabon" steht. Liefert das
-- nichts, ist 1400001 die INVOICE_NO — dann erst ueber folio$_tax die
-- bill_no holen.
-- DEFINE TRX = <TRX_NO der Buchung mit bekanntem Supplement-Text>
SELECT ft.trx_no, ft.bill_no, ft.trx_code,
       ft.remark,
       ft.reference,
       ft.o_trx_desc
  FROM &&OPERA_OWNER..financial_transactions ft
 WHERE ft.trx_no = &&TRX;

PROMPT == 2. Wie gut sind die drei Felder ueberhaupt gefuellt? ==
SELECT COUNT(*)                                                          AS zeilen,
       SUM(CASE WHEN TRIM(ft.remark)     IS NOT NULL THEN 1 ELSE 0 END)  AS mit_remark,
       SUM(CASE WHEN TRIM(ft.reference)  IS NOT NULL THEN 1 ELSE 0 END)  AS mit_reference,
       SUM(CASE WHEN TRIM(ft.o_trx_desc) IS NOT NULL THEN 1 ELSE 0 END)  AS mit_o_trx_desc
  FROM &&OPERA_OWNER..financial_transactions ft
  JOIN &&OPERA_OWNER..folio$_tax f ON f.bill_no = ft.bill_no AND f.resort = ft.resort
 WHERE f.resort = '&&RESORT'
   AND f.document_type = 'INVOICE' AND f.status = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - &&TAGE
   AND ft.gross_amount IS NOT NULL;

PROMPT == 3. Ein Blick auf die Inhalte — geht das an einen Kunden? ==
-- Was hier steht, wuerde als Bemerkung auf der Rechnung landen. Ein Vermerk
-- wie "Kulanz nach Ruecksprache GM" gehoert dort nicht hin; das ist eine
-- fachliche Entscheidung des Hauses, keine technische.
SELECT * FROM (
SELECT ft.trx_code, ft.remark, ft.reference, COUNT(*) AS wie_oft
  FROM &&OPERA_OWNER..financial_transactions ft
  JOIN &&OPERA_OWNER..folio$_tax f ON f.bill_no = ft.bill_no AND f.resort = ft.resort
 WHERE f.resort = '&&RESORT'
   AND f.document_type = 'INVOICE' AND f.status = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - &&TAGE
   AND ft.gross_amount IS NOT NULL
   AND (TRIM(ft.remark) IS NOT NULL OR TRIM(ft.reference) IS NOT NULL)
 GROUP BY ft.trx_code, ft.remark, ft.reference
 ORDER BY wie_oft DESC)
 WHERE ROWNUM <= 40;

PROMPT == 4. Gibt es die Druckvorschau-Tabelle ueberhaupt mit Inhalt? ==
-- Wenn FOLIO_DETAIL dauerhaft gefuellt waere, kaeme sie als Quelle in Frage.
-- Erwartung: leer oder nur der Beleg, den gerade jemand am Bildschirm hat.
SELECT COUNT(*) AS zeilen,
       SUM(CASE WHEN TRIM(d.supplement) IS NOT NULL THEN 1 ELSE 0 END) AS mit_supplement
  FROM &&OPERA_OWNER..folio_detail d;
