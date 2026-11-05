-- reservierung_udf.sql — ein benutzerdefiniertes Feld der Reservierung lesen
-- Bindvariablen: :bill_no, :resort, :folio_no
--
-- Fuer die Versand-Mailadresse (property.udf_mail_reservierung): Was der
-- Empfang in der Reservierungsmaske als Rechnungsadresse eintraegt, geht vor
-- der automatischen Auswahl — aber nach dem Mailfeld am Profil.
--
-- Wie profil_udf.sql eine Vorlage: Der SPALTENNAME wird in app/opera.py
-- eingesetzt, nicht gebunden, und nur UDFC01..UDFC40 kommen durch.
-- Gelesen wird die Reservierung, auf der die Rechnung beruht (RESV_NAME_ID des
-- Belegs), ueber das Folio des Belegs (siehe invoice_folio.sql).

SELECT TRIM(r.@SPALTE@) AS wert
  FROM @SCHEMA@.folio$_tax f
  JOIN @SCHEMA@.reservation_name r
    ON r.resv_name_id = f.resv_name_id
 WHERE f.bill_no  = :bill_no
   AND f.resort   = :resort
   AND f.folio_no = :folio_no
