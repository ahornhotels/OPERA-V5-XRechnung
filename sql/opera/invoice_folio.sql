-- invoice_folio.sql — zu welchem Folio gehoert diese Rechnungsnummer?
-- Bindvariablen: :bill_no, :resort
--
-- BILL_NO ist je Resort NICHT eindeutig. Gemessen am 29.10.2026 in einem Haus:
-- 258 Nummern auf mehr als einem Folio, 107 davon mit mehr als einer Zeile
-- STATUS 'OK' und DOCUMENT_TYPE 'INVOICE', im Abstand von 0 bis 494 Tagen.
-- Das Muster: je Nummer genau eine echte Rechnung mit FOLIO_TYPE 'TSE_FOLIO'
-- und daneben Zeilen mit FOLIO_TYPE 'INTERNAL' — Umbuchungen zwischen Folios,
-- die einen bereits verbrauchten Nummernbereich wiederverwenden und sich
-- paarweise auf den Cent aufheben. Mit 'TSE_FOLIO' war die Nummer in allen
-- Jahren eindeutig (95.355 Nummern, keine doppelt).
--
-- Bisher suchten alle Abfragen je Beleg nur ueber (RESORT, BILL_NO). Bei einer
-- doppelten Nummer brach dann die Kopfabfrage ab (die Unterabfrage nach dem
-- Folio lieferte zwei Zeilen), und die Positionen zweier Aufenthalte wurden
-- zusammengezaehlt.
--
-- Bevorzugt wird deshalb die Kassenrechnung, dann jede andere Art, zuletzt eine
-- interne Umbuchung; innerhalb dessen ein abgeschlossener Beleg mit Dokumenttyp
-- und der juengste. 'TSE_FOLIO' wird nicht VERLANGT: Belege vor Einfuehrung der
-- TSE und Haeuser ohne sie tragen FOLIO_TYPE NULL.
--
-- Der Index FOLIO_TAX_BILLNO_I geht ueber (RESORT, BILL_NO) — die Abfrage
-- liest nur die Zeilen dieser einen Nummer.

SELECT f.folio_no,
       f.folio_type
  FROM @SCHEMA@.folio$_tax f
 WHERE f.resort  = :resort
   AND f.bill_no = :bill_no
 ORDER BY CASE f.folio_type WHEN 'TSE_FOLIO' THEN 0 WHEN 'INTERNAL' THEN 2 ELSE 1 END,
          CASE WHEN f.status = 'OK' AND f.document_type IS NOT NULL THEN 0 ELSE 1 END,
          f.bill_generation_date DESC,
          f.folio_no DESC
 FETCH FIRST 1 ROW ONLY
