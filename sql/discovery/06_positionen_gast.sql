-- 06_positionen_gast.sql — Gegenprobe zur Darstellung der Positionen (B / C)
-- Nur lesend. Fuer die Session mit dem lesenden DB-Zugang.
-- DEFINE OPERA_OWNER = OPERA
-- DEFINE RESORT = <Ihr Resortkuerzel>
-- DEFINE TAGE = 30
--
-- Die Anwendung ordnet eine Buchung dem Gast ueber
--     NVL(ORIGINAL_RESV_NAME_ID, RESV_NAME_ID)  und  NVL(ORIGINAL_ROOM, ROOM)
-- zu (sql/opera/invoice_lines.sql). Annahme: Bei umgeleiteten Buchungen
-- (Routing auf ein Masterkonto) zeigen RESV_NAME_ID/ROOM auf das Masterkonto
-- und ORIGINAL_* auf das Gastzimmer, aus dem die Buchung stammt. Diese Annahme
-- ist aus dem Data Dictionary abgeleitet, NICHT an Daten gesehen. Die vier
-- Abfragen unten sollen sie bestaetigen oder widerlegen. Mitgezaehlt wird
-- FROM_RESV_ID: Wird eine Umbuchung nur dort vermerkt, fehlt sie der Zuordnung.
--
-- Zielmenge wie in der Anwendung: INVOICE / OK, Erloeszeilen (GROSS_AMOUNT NOT NULL).

PROMPT == 1. Wie oft weichen ORIGINAL_* von RESV_NAME_ID/ROOM ab? ==
SELECT COUNT(*)                                                         AS zeilen,
       SUM(CASE WHEN ft.original_resv_name_id IS NULL THEN 1 ELSE 0 END) AS original_leer,
       SUM(CASE WHEN ft.original_resv_name_id = ft.resv_name_id THEN 1 ELSE 0 END) AS original_gleich,
       SUM(CASE WHEN ft.original_resv_name_id <> ft.resv_name_id THEN 1 ELSE 0 END) AS original_anders,
       SUM(CASE WHEN ft.room IS NULL THEN 1 ELSE 0 END)                 AS room_leer,
       SUM(CASE WHEN NVL(ft.original_room, ft.room) IS NULL THEN 1 ELSE 0 END) AS gast_zimmer_leer,
       SUM(CASE WHEN ft.routing_instrn_id IS NOT NULL THEN 1 ELSE 0 END) AS mit_routing,
       -- FROM_RESV_ID: moeglicher zweiter Traeger des Ursprungs, etwa bei
       -- manuellen Umbuchungen. Ist er gefuellt, ORIGINAL_RESV_NAME_ID aber
       -- nicht, landet die Buchung unter C beim Masterkonto.
       SUM(CASE WHEN ft.from_resv_id IS NOT NULL THEN 1 ELSE 0 END)     AS from_resv_gefuellt,
       SUM(CASE WHEN ft.from_resv_id IS NOT NULL AND ft.original_resv_name_id IS NULL
                THEN 1 ELSE 0 END)                                      AS nur_from_resv,
       SUM(CASE WHEN ft.from_resv_id IS NOT NULL
                 AND ft.from_resv_id <> NVL(ft.original_resv_name_id, ft.resv_name_id)
                THEN 1 ELSE 0 END)                                      AS from_resv_anders
  FROM &&OPERA_OWNER..financial_transactions ft
  JOIN &&OPERA_OWNER..folio$_tax f ON f.bill_no = ft.bill_no AND f.resort = ft.resort
 WHERE f.resort = '&&RESORT'
   AND f.document_type = 'INVOICE' AND f.status = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - &&TAGE
   AND ft.gross_amount IS NOT NULL;

PROMPT == 2. Beispiele fuer abweichende Zuordnung: wer steht dort jeweils? ==
SELECT * FROM (
SELECT ft.bill_no, ft.trx_no, ft.trx_code, ft.gross_amount,
       ft.resv_name_id, ft.room,
       (SELECT TRIM(n."LAST" || ', ' || n."FIRST") FROM &&OPERA_OWNER..reservation_name r
          JOIN &&OPERA_OWNER..name n ON n.name_id = r.name_id
         WHERE r.resv_name_id = ft.resv_name_id)          AS name_resv,
       ft.original_resv_name_id, ft.original_room, ft.from_resv_id,
       (SELECT TRIM(n."LAST" || ', ' || n."FIRST") FROM &&OPERA_OWNER..reservation_name r
          JOIN &&OPERA_OWNER..name n ON n.name_id = r.name_id
         WHERE r.resv_name_id = ft.original_resv_name_id) AS name_original
  FROM &&OPERA_OWNER..financial_transactions ft
  JOIN &&OPERA_OWNER..folio$_tax f ON f.bill_no = ft.bill_no AND f.resort = ft.resort
 WHERE f.resort = '&&RESORT'
   AND f.document_type = 'INVOICE' AND f.status = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - &&TAGE
   AND ft.gross_amount IS NOT NULL
   AND (ft.original_resv_name_id <> ft.resv_name_id
        OR (ft.from_resv_id IS NOT NULL AND ft.original_resv_name_id IS NULL))
 ORDER BY ft.bill_no DESC, ft.trx_no)
 WHERE ROWNUM <= 40;

PROMPT == 3. Wie viele Gaeste je Rechnung, und wie viele Zeilen B und C ergeben ==
-- B: je Umsatzcode, Satz (hier nur ueber TAX_ELEMENTS angenaehert) und Bruttopreis
-- C: zusaetzlich je Gast
SELECT * FROM (
SELECT ft.bill_no,
       COUNT(*)                                                           AS zeilen_a,
       COUNT(DISTINCT NVL(ft.original_resv_name_id, ft.resv_name_id))     AS gaeste,
       COUNT(DISTINCT ft.trx_code || '|' || ft.tax_elements || '|' ||
             ROUND(ft.gross_amount / NULLIF(NVL(ft.quantity, 1), 0), 2))  AS zeilen_b,
       COUNT(DISTINCT NVL(ft.original_resv_name_id, ft.resv_name_id) || '|' ||
             ft.trx_code || '|' || ft.tax_elements || '|' ||
             ROUND(ft.gross_amount / NULLIF(NVL(ft.quantity, 1), 0), 2))  AS zeilen_c
  FROM &&OPERA_OWNER..financial_transactions ft
  JOIN &&OPERA_OWNER..folio$_tax f ON f.bill_no = ft.bill_no AND f.resort = ft.resort
 WHERE f.resort = '&&RESORT'
   AND f.document_type = 'INVOICE' AND f.status = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - &&TAGE
   AND ft.gross_amount IS NOT NULL
 GROUP BY ft.bill_no
 ORDER BY gaeste DESC, zeilen_a DESC)
 WHERE ROWNUM <= 30;

PROMPT == 4. Menge 0 und Preis je Einheit: Sonderfaelle fuer die Buendelung ==
SELECT COUNT(*)                                                             AS zeilen,
       SUM(CASE WHEN NVL(ft.quantity, 1) = 0 THEN 1 ELSE 0 END)              AS menge_null,
       SUM(CASE WHEN NVL(ft.quantity, 1) < 0 THEN 1 ELSE 0 END)              AS menge_negativ,
       SUM(CASE WHEN ft.price_per_unit IS NULL THEN 1 ELSE 0 END)            AS preis_leer,
       SUM(CASE WHEN ft.price_per_unit IS NOT NULL
                 AND ABS(ft.price_per_unit - ft.gross_amount / NULLIF(NVL(ft.quantity, 1), 0)) > 0.005
                THEN 1 ELSE 0 END)                                           AS preis_weicht_ab
  FROM &&OPERA_OWNER..financial_transactions ft
  JOIN &&OPERA_OWNER..folio$_tax f ON f.bill_no = ft.bill_no AND f.resort = ft.resort
 WHERE f.resort = '&&RESORT'
   AND f.document_type = 'INVOICE' AND f.status = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - &&TAGE
   AND ft.gross_amount IS NOT NULL;
