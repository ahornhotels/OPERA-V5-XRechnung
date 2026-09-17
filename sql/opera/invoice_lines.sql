-- invoice_lines.sql — Rechnungspositionen nach Datenvertrag
-- Bindvariablen: :bill_no, :resort
--
-- Erloeszeile := GROSS_AMOUNT IS NOT NULL. Steuerzeilen (eigene Buchungen,
-- Codes 71xx) tragen kein Brutto; Package- und Zahlungszeilen tragen gar keine
-- Betraege. Belegt an 353 von 353 City-Ledger-Rechnungen — siehe
-- docs/06_BEFUNDE_LIVE_DB.md.
--
-- VORAUSSETZUNG: die Rechnung darf keine Anzahlungs-Umbuchung enthalten
-- (TRX_CODE 8990/8997/7106). Das prueft invoice_guard.sql; andernfalls sind die
-- Positionen je Steuer-Bucket zu bilden.
--
-- Steuersatz je Position: FT.TAX_ELEMENTS traegt ihn als Text (" 7%", " 19%",
-- " 0%") und ist die genaueste Quelle, weil sie an der einzelnen Buchung haengt.
-- Rueckfall ist die Generates-Konfiguration TRX_CLASS_RELATIONSHIPS
-- (TRX_CODE = erzeugter Steuercode, TRX_CODE_GENERATOR = ausloesender Erloescode).

SELECT z.trx_no,
       z.invoicedquantity,
       z.lineextensionamountnet,
       z.lineextensionamount,
       ROUND(z.lineextensionamountnet / NULLIF(z.invoicedquantity, 0), 2) AS priceamount,
       z.itemname,
       z.itemcode,
       z.pct                                                  AS classifiedtaxcategorypercent,
       CASE WHEN NVL(z.pct, 0) > 0 THEN 'S' ELSE 'Z' END      AS classifiedtaxcategoryid,
       'VAT'                                                  AS taxschemeid,
       z.tax_elements,
       z.tax_inclusive_yn,
       z.tc_group,
       z.tc_subgroup,
       z.trx_date,
       -- BT-127: Bemerkung an der BUCHUNG (nicht die der Reservierung). Sie
       -- steht in der Norm an der Position, nicht am Kopf, und ist dort
       -- optional und frei. Zusammengesetzt wird sie in app/opera.py aus den
       -- Feldern, die die Konfiguration nennt.
       z.bem_remark,
       z.bem_reference,
       -- Fuer die Buendelung (app/opera.py, positionen_buendeln): Einzelpreis
       -- BRUTTO auf den Cent. Er ist der Schluessel "gleicher Preis" — der
       -- Nettopreis ist in OPERA ungerundet und aus dem Brutto abgeleitet, zwei
       -- gleiche Bruttopreise haben also auch denselben Nettopreis.
       ROUND(z.lineextensionamount / NULLIF(z.invoicedquantity, 0), 2) AS bruttopreis,
       -- Wer die Leistung bekommen hat. Bei Gruppen- und Sammelrechnungen ist
       -- die Buchung vom Gastzimmer auf das Masterkonto umgeleitet (Routing);
       -- RESV_NAME_ID und ROOM zeigen dann auf das MASTERkonto, und die
       -- Rechnung nennte fuer jede Zeile die Gruppe statt des Gastes.
       -- ORIGINAL_RESV_NAME_ID und ORIGINAL_ROOM tragen den Ursprung.
       -- NOCH AN DER LIVE-DB GEGENZUPRUEFEN, siehe sql/discovery/06_positionen_gast.sql.
       -- Das Datum der Buchung: Zeitraum je Position unter C ist die Spanne der
       -- tatsaechlich berechneten Tage, nicht der ganze Aufenthalt der
       -- Reservierung (bei einem Masterkonto koennen das Monate sein).
       z.leistungsdatum,
       z.gast_resv_name_id,
       z.gast_zimmer,
       z.gast_name,
       z.gast_beginn,
       z.gast_ende,
       z.resv_name_id,
       z.room
  FROM (SELECT ft.trx_no,
               NVL(ft.quantity, 1)              AS invoicedquantity,
               ft.net_amount                    AS lineextensionamountnet,
               ft.gross_amount                  AS lineextensionamount,
               NVL(tc.description, ft.trx_code) AS itemname,
               ft.trx_code                      AS itemcode,
               ft.tax_elements,
               ft.tax_inclusive_yn,
               ft.trx_date,
               -- Kandidaten fuer BT-127. WELCHE davon in die Rechnung gehen,
               -- entscheidet die Konfiguration (property.positionsbemerkung) —
               -- verschiedene Haeuser fuellen verschiedene Felder, und was
               -- hier hereinkommt, geht an den Kunden.
               --   REMARK     handgetippte Buchungsbemerkung, hier 2,7 %
               --   REFERENCE  bei POS-Buchungen die Check-Nummer (zu pruefen)
               --   O_TRX_DESC BEWUSST NICHT: dort steht die Systemherkunft,
               --              "RATE HEADER" und "RESV" — bei 47,9 % der
               --              Buchungen. Das saehe nach dem besseren Feld aus
               --              und stuende dann auf jeder zweiten Position.
               TRIM(ft.remark)                  AS bem_remark,
               TRIM(ft.reference)               AS bem_reference,
               COALESCE(
                 -- 1. Satz aus der Buchung selbst (" 7%" -> 7)
                 CASE WHEN REGEXP_LIKE(NVL(ft.tax_elements, 'x'), '^ *[0-9]+([.,][0-9]+)? *% *$')
                      THEN TO_NUMBER(TRIM(REPLACE(REPLACE(ft.tax_elements, '%', ''), ',', '.')),
                                     '9999D9999', 'NLS_NUMERIC_CHARACTERS=''.,''')
                 END,
                 -- 2. Rueckfall: Generates-Konfiguration des Umsatzcodes
                 (SELECT MAX(rel.percentage)
                    FROM @SCHEMA@.trx_class_relationships rel
                   WHERE rel.resort             = ft.resort
                     AND rel.trx_code_generator = ft.trx_code),
                 -- 3. Durchlaufende Posten: tc_group PAIDOUTS erzeugt keine
                 -- Steuer und traegt keinen Satz in der Generates-Konfiguration.
                 -- NON_TAXABLE_YN steht dort irrefuehrend auf 'N'.
                 CASE WHEN tc.tc_group = 'PAIDOUTS' THEN 0 END
               ) AS pct,
               tc.tc_group,
               tc.tc_subgroup,
               TO_CHAR(ft.trx_date, 'YYYY-MM-DD')             AS leistungsdatum,
               NVL(ft.original_resv_name_id, ft.resv_name_id) AS gast_resv_name_id,
               NVL(ft.original_room, ft.room)                 AS gast_zimmer,
               -- Wie im Rechnungskopf: Nachname, Vorname — und OHNE Rueckfall
               -- auf die Firma, dort stehen bei Gruppen Kuerzel wie GRO020926.
               TRIM(TRIM(g."LAST") || CASE WHEN g."FIRST" IS NOT NULL
                                           THEN ', ' || g."FIRST" END) AS gast_name,
               TO_CHAR(rn.begin_date, 'YYYY-MM-DD')           AS gast_beginn,
               TO_CHAR(rn.end_date,   'YYYY-MM-DD')           AS gast_ende,
               ft.resv_name_id,
               ft.room
          FROM @SCHEMA@.financial_transactions ft
          LEFT JOIN @SCHEMA@.trx$_codes tc
            ON tc.trx_code = ft.trx_code AND tc.resort = ft.resort
          LEFT JOIN @SCHEMA@.reservation_name rn
            ON rn.resv_name_id = NVL(ft.original_resv_name_id, ft.resv_name_id)
          LEFT JOIN @SCHEMA@.name g
            ON g.name_id = rn.name_id
         WHERE ft.bill_no      = :bill_no
           AND ft.resort       = :resort
           AND ft.gross_amount IS NOT NULL) z
 ORDER BY z.trx_no
