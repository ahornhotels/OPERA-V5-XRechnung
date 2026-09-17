-- profil_name.sql — der Name zu einer Profilnummer
-- Bindvariable: :name_id
--
-- Fuer die Pflegeliste. Auf dem Beleg steht COMPANY_NAME oft nicht, am Profil
-- aber sehr wohl — der Empfang soll nach einem Kunden suchen koennen und
-- nicht nach einer Nummer.
--
-- NAME hat keine Spalte NAME: bei Firmen steht der Name in COMPANY, bei
-- Personen in LAST/FIRST. Beide Spalten stehen in Anfuehrungszeichen, weil
-- LAST und FIRST in Oracle auch Schluesselwoerter sind.

SELECT COALESCE(n.company,
                n.legal_company,
                TRIM(TRIM(n."LAST") || CASE WHEN n."FIRST" IS NOT NULL
                                            THEN ', ' || n."FIRST" END))   AS name,
       n.name_type
  FROM @SCHEMA@.name n
 WHERE n.name_id = :name_id
