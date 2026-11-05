-- reservierung_gast_mails.sql — Mailadressen des Gastes an der Reservierung
-- Bindvariablen: :bill_no, :resort, :folio_no
--
-- NUR FUER DIE AUSWAHL VON HAND auf der Detailseite. invoice_recipients.sql
-- laesst den Gast bewusst weg, sobald ein anderer Zahler da ist: Eine
-- Firmenrechnung gehoert nicht in sein privates Postfach. Wer in der
-- Sichtpruefung entscheidet, soll aber alle Adressen sehen, die es an der
-- Reservierung gibt — gekennzeichnet als die des Gastes.

SELECT 'Gast an der Reservierung'      AS quelle,
       'Gast'                          AS rolle,
       ph.name_id                      AS name_id,
       ph.phone_number                 AS email,
       ph.phone_type                   AS typ,
       NVL(ph.primary_yn, 'N')         AS primaer
  FROM @SCHEMA@.folio$_tax f
  JOIN @SCHEMA@.reservation_name r
    ON r.resv_name_id = f.resv_name_id
  JOIN @SCHEMA@.name_phone ph
    ON ph.name_id = r.name_id
 WHERE f.bill_no  = :bill_no
   AND f.resort   = :resort
   AND f.folio_no = :folio_no
   AND ph.phone_role = 'EMAIL'
   AND ph.phone_number IS NOT NULL
   AND (ph.inactive_date IS NULL OR ph.inactive_date > SYSDATE)
 ORDER BY NVL(ph.primary_yn, 'N') DESC, ph.phone_number
